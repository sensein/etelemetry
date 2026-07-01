#!/bin/sh
# Renew the Let's Encrypt cert for rig.mit.edu (certbot webroot) and, ONLY when the cert
# actually changed, re-import it into the ACM cert the ALB serves. Uses the EC2 instance
# IAM role for ACM. Safe to run daily: `certbot renew` is a no-op until ~30 days before
# expiry, and the ACM import only fires on an actual renewal.
set -eu

DOMAIN=rig.mit.edu
CERT_ARN=arn:aws:acm:us-east-2:278212569472:certificate/c34a3938-a305-405c-a4ae-7bda5413b1f3
REGION=us-east-2
SRC=/home/ec2-user/src
LIVE="$SRC/certbot/conf/live/$DOMAIN"
LOG=/home/ec2-user/out/logs/cert-renew.log

echo "=== $(date -u) renew check ===" >> "$LOG"

fp() { sudo openssl x509 -in "$LIVE/cert.pem" -noout -fingerprint -sha256 2>/dev/null || echo none; }
before=$(fp)

# Renew via the certbot container (webroot HTTP-01; ALB forwards the ACME path to nginx).
sudo docker run --rm \
  -v "$SRC/certbot/conf:/etc/letsencrypt" \
  -v "$SRC/certbot/www:/var/www/certbot" \
  certbot/certbot renew --non-interactive >> "$LOG" 2>&1 || \
  echo "certbot renew returned non-zero" >> "$LOG"

after=$(fp)

if [ "$before" = "$after" ]; then
  echo "no change; ACM import skipped" >> "$LOG"
  exit 0
fi

echo "cert changed ($before -> $after); importing to ACM" >> "$LOG"
sudo aws acm import-certificate --region "$REGION" \
  --certificate-arn "$CERT_ARN" \
  --certificate       "fileb://$LIVE/cert.pem" \
  --private-key       "fileb://$LIVE/privkey.pem" \
  --certificate-chain "fileb://$LIVE/chain.pem" >> "$LOG" 2>&1

NOTAFTER=$(sudo aws acm describe-certificate --region "$REGION" --certificate-arn "$CERT_ARN" \
  --query 'Certificate.NotAfter' --output text 2>>"$LOG")
echo "=== $(date -u) imported; ACM NotAfter=$NOTAFTER ===" >> "$LOG"
