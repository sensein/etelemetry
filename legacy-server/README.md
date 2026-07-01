# Legacy etelemetry server (rig.mit.edu) — canonical operations reference

This directory is the **single entrypoint for the old, manually-deployed etelemetry
server** that runs at `https://rig.mit.edu`. If you ever have to come back to that
deployment — restore it, debug it, or hand it off — start here.

> This is the **legacy** stack (Sanic + MongoDB, hand-deployed with docker-compose on a
> single EC2 instance). The rewrite that replaces it lives in [`../server`](../server),
> [`../deploy`](../deploy), and [`../infra`](../infra). Nothing here is managed by the
> `infra/` Terraform — the old server is 100% manual.

---

## 1. What it is

etelemetry records, per project, which client versions are being used in the wild
(the `etelemetry` client pings `GET /projects/<owner>/<repo>` on import). The server
returns the latest release + known-bad versions and logs the request (with geo-IP) to
MongoDB.

- Public URL: `https://rig.mit.edu`
- Main endpoints: `GET /projects/<owner>/<repo>` (record + return version),
  `GET /stats/<owner>/<repo>`, `GET /` (health).
- Live data (as of 2026-07-01): **~81.7M** request docs in the `et.requests` collection.

## 2. Architecture

```
client ──HTTPS──▶ ALB (etelemetry-ec2-load-balancer)
                    :443 HTTPS  ── ACM cert (rig.mit.edu) ── forward ─┐
                    :80  HTTP   ── redirect to :443                   │
                                                                      ▼
                                        EC2 instance i-01c6158d37a85dd50 (t3a.medium)
                                        target group -> instance :80
                                                                      │
                                        docker-compose (/home/ec2-user/src):
                                          nginx-proxy  :80  ──▶ et-server :80 (Sanic)
                                                                     │
                                                                     ▼
                                                              mongo :27017 (mongo:4.1.13)
```

- **TLS terminates at the ALB**, not on the box. nginx listens on `:80` only.
- The ACME HTTP-01 challenge still works because the ALB `:80`→`:443` redirect is
  followed by Let's Encrypt, and `:443` forwards `/.well-known/acme-challenge/` to nginx,
  which serves it from the certbot webroot.

### AWS identifiers (account `278212569472`, region `us-east-2`)

| Thing | Value |
|---|---|
| EC2 instance | `i-01c6158d37a85dd50` (t3a.medium, EBS root `vol-03c54cace842bbb1b`, gp3 16 GiB) |
| Public IP | `3.145.158.28` (SSH: `ssh ec2-user@3.145.158.28`) |
| ALB | `etelemetry-ec2-load-balancer` (`arn:...:loadbalancer/app/etelemetry-ec2-load-balancer/355129b48a966e00`) |
| Target group | `etelemetry-ec2-target-group` → instance `:80`, health check `/` |
| ACM cert (rig.mit.edu) | `arn:aws:acm:us-east-2:278212569472:certificate/c34a3938-a305-405c-a4ae-7bda5413b1f3` (IMPORTED, Let's Encrypt) |
| Backup bucket | `s3://etelemetry-backup/` |
| Instance IAM role | `etelemetry-old-server` (least-priv: S3 backup write + ACM import) |

## 3. On-instance layout (`/home/ec2-user`)

```
src/                     # docker-compose project (compose "src"); THIS dir's files live here
  docker-compose.yml
  .env                   # DB_DATA_DIR, DB_LOG_DIR, IPSTACK_API_KEY  (secrets; not in git)
  nginx/conf/*.conf
  certbot/{conf,www}     # letsencrypt config + webroot
  config/                # et.cfg
  backup-mongo.sh  prune-etelemetry-logs.sh  renew-cert.sh   # maintenance scripts
etelemetry-server/       # the Sanic app source (separate git repo), bind-mounted into et-server
mongo-scratch/data/      # MongoDB data files (~4.2G) — bind mount, on the EBS root volume
out/cache/               # project version cache (json per owner--repo)
out/logs/                # app console.log / access.log (+ rotations) and maintenance logs
out/backup/              # local mongodump archives (last 2 kept)
```

## 4. The 2026-05-12 outage and 2026-07-01 recovery

**What happened:** `out/logs` grew unbounded (the app rotates `console.log`/`access.log`
weekly but never deletes old rotations — they reached ~5.7G, some files 800 MB). The 16G
root disk hit 100%. On **2026-05-12** MongoDB's WiredTiger checkpoint thread aborted
(exit 14) on the full disk and, with `restart: no`, **never came back**. For ~7 weeks
nginx/et-server stayed up (so `GET /` returned 200) but every telemetry write failed
(`mongo:27017: Name does not resolve` — the mongo container was simply down). Separately,
the ALB's Let's Encrypt cert **expired 2026-06-20** because renewal/re-import was never
scheduled.

**Recovery performed (2026-07-01):**
1. Reclaimed disk (dnf cache, journal vacuum, docker prune, deleted log rotations >2 weeks,
   removed `old-logs/`): 137M → 7.3G free.
2. Cold backup of the crashed data files → `s3://etelemetry-backup/cold-backups/` before
   touching mongo.
3. Restarted mongo (clean WiredTiger recovery); deleted 11 **empty** cache files that the
   disk-full event had zeroed (they caused `500`s via `json.loads("")`).
4. Set `restart: unless-stopped` on all containers.
5. Attached least-priv IAM role; removed the stale/invalid static AWS keys so the box uses
   the instance role via IMDS.
6. Renewed the cert (webroot) and re-imported to the ACM ARN → HTTPS valid again.
7. Installed maintenance scripts + systemd timers (below).
8. **Disabled a runaway `rngd`** (rng-tools bug) that was pegging a CPU core and starving
   sshd — see Gotchas.

## 5. Ongoing maintenance (systemd timers)

Units are in [`systemd/`](systemd); install them with [`scripts/setup-timers.sh`](scripts/setup-timers.sh).
They run as **root** (so the scripts' `sudo`/AWS-role calls work without a tty).

| Timer | Schedule (UTC) | Runs | Purpose |
|---|---|---|---|
| `etelemetry-log-prune.timer` | daily 03:30 | `prune-etelemetry-logs.sh` | delete `out/logs` rotations older than 21 days (prevents the disk-full recurrence) |
| `etelemetry-backup-base.timer` | Sun 02:00 | `backup-mongo.sh base` | weekly FULL `mongodump` → S3; records the requests `_id` watermark |
| `etelemetry-backup-incr.timer` | daily 02:30 | `backup-mongo.sh incr` | INCREMENTAL: dumps only `requests` inserted since the watermark (fast/small) |
| `etelemetry-cert-renew.timer` | daily 04:00 | `renew-cert.sh` | certbot renew + re-import to ACM (import only on actual change) |

Check them: `systemctl list-timers 'etelemetry-*'`.

## 6. Backups & restore

Backups live in `s3://etelemetry-backup/`. The `requests` collection is **append-only**,
so backups are incremental by `_id` (each backup writes only new docs, not the whole 81M-row
DB):

- **Incremental** (`incremental/et.base.<ts>.gz` + `incremental/et.incr.<ts>.gz`) — a weekly
  FULL **base** dump of the `et` DB plus daily **increments** containing only `requests`
  inserted since the last `_id` watermark (`incremental/requests.watermark`). Base captures
  the small collections (`v1`, `geo`). This is the primary, ongoing backup.
- **Cold** (`cold-backups/mongo-data-*.tar.gz`) — a tar of the raw `mongo-scratch/data`
  dir, taken while mongo was stopped during the 2026-07-01 recovery (disaster fallback).
- **Legacy** (`et.archive.*.gz` at the bucket root) — old full `mongodump` archives
  (through Aug 2025), kept for history.

**Restore (incremental):** restore the latest base, then replay every newer increment in
timestamp order (increments are non-overlapping inserts, so order-of-`_id` == order-of-time):
```sh
aws s3 cp s3://etelemetry-backup/incremental/et.base.<latest>.gz - \
  | sudo docker exec -i mongo sh -c 'mongorestore --gzip --archive --drop -d et'
for f in $(aws s3 ls s3://etelemetry-backup/incremental/ | awk '/et.incr\./{print $4}' | sort); do
  aws s3 cp "s3://etelemetry-backup/incremental/$f" - \
    | sudo docker exec -i mongo sh -c 'mongorestore --gzip --archive -d et'   # no --drop
done
```
**Restore from a cold backup** (mongo stopped): extract the tar into
`/home/ec2-user/mongo-scratch/` (replacing `data/`), then `docker start mongo`.

> Trade-off (by design): incremental restore replays multiple files, but each backup run
> writes only new `requests` instead of re-dumping all 81M docs — turning a ~30-min full
> dump into a seconds-long delta.

## 7. TLS / certificate renewal

certbot (webroot, in a container) obtains/renews the Let's Encrypt cert for `rig.mit.edu`
into `src/certbot/conf/live/rig.mit.edu/`. Because TLS is at the ALB, the renewed cert must
be **re-imported into the same ACM ARN** — the ALB then serves it automatically.
[`scripts/renew-cert.sh`](scripts/renew-cert.sh) does both (renew, then
`aws acm import-certificate --certificate-arn <ARN>`), driven daily by the timer.
The instance role grants `acm:ImportCertificate` on that one ARN only.

## 8. Space management

The disk-full outage root cause is now handled two ways:
1. **App logs** — `prune-etelemetry-logs.sh` (daily timer) deletes `out/logs` rotations >21d.
2. **Container logs** — [`docker/daemon.json`](docker/daemon.json) caps json-file logs
   (50m × 3). `docker-compose.yml` also sets per-service `logging` limits; a full
   `docker-compose up` (recreate) is required for those to apply to existing containers.

## 9. IAM (least privilege)

Role `etelemetry-old-server` (see [`iam/`](iam)) is attached to the instance and grants
**only**: `s3:PutObject`/`s3:ListBucket` on `etelemetry-backup`, and
`acm:ImportCertificate`/`acm:DescribeCertificate` on the rig.mit.edu cert ARN. No static
keys live on the box (the old invalid ones were moved to `*.stale-invalid.bak`).

## 10. Gotchas (read before you touch the box)

- **`rngd` runaway:** rng-tools can busy-loop at ~100% of a core on this AMI, which starves
  `sshd` (symptom: SSH "Connection timed out during banner exchange" while CPU is high but
  network is idle). It is stopped/disabled/masked. Do **not** re-enable it; the kernel CRNG
  provides entropy on Nitro. `dnf upgrade` may ship a fixed rng-tools — re-evaluate then.
- **No cron by default:** AL2023 has no `cronie`. Use the **systemd timers** here.
- **SSH under load:** heavy `mongodump`/recovery makes sshd slow to answer. Don't hammer
  reconnects (each timed-out attempt holds an sshd `MaxStartups` slot ~120s and compounds
  the problem). Prefer one patient connection, or drive the box via the EC2 API.
- **Reboots are safe for data:** `mongo-scratch/data` is on the persistent EBS root volume;
  containers are `unless-stopped` and auto-start. `aws ec2 reboot-instances` works even when
  SSH is wedged.
- **CPU credits:** t3a.medium is burstable in `unlimited` mode — fine, but sustained work
  (backup, upgrade) will still peak CPU.

## 11. Rebuild / come back to this deployment

1. Instance with docker + docker-compose (v1), EBS root ≥16G, IAM role `etelemetry-old-server`.
2. Recreate `/home/ec2-user/src` from this dir; add `.env` from `.env.example` (real
   `IPSTACK_API_KEY`); clone the app repo to `/home/ec2-user/etelemetry-server`.
3. Restore MongoDB (§6) into `/home/ec2-user/mongo-scratch/data`.
4. `cd ~/src && docker-compose up -d --build`.
5. Install `docker/daemon.json`, copy the three scripts into `~/src`, run
   `scripts/setup-timers.sh`.
6. Obtain/renew the cert (`renew-cert.sh`) and confirm the ALB target is healthy + HTTPS valid.

## Files in this directory

```
docker-compose.yml            hardened compose (restart + logging), secrets via .env
.env.example                  template for src/.env
nginx/conf/rig.mit.edu.conf   nginx :80 proxy + acme-challenge webroot
scripts/backup-mongo.sh       mongodump -> S3 (instance role), local retention 2
scripts/prune-etelemetry-logs.sh  delete out/logs rotations >21 days
scripts/renew-cert.sh         certbot renew (webroot) + re-import to ACM
scripts/setup-timers.sh       install/enable the systemd timers (replaces cron)
systemd/*.service, *.timer    the three maintenance units
docker/daemon.json            docker json-file log rotation defaults
iam/trust-policy.json         EC2 assume-role trust for etelemetry-old-server
iam/permissions-policy.json   least-priv S3 + ACM permissions
```
