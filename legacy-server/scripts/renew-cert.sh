#!/bin/sh
# Renew the Let's Encrypt cert for rig.mit.edu (certbot webroot) and re-import it into
# the ACM certificate that the ALB serves. Uses the EC2 instance IAM role for ACM.
# certbot 'renew' is a no-op until ~30 days before expiry, so this is safe to run daily.
# NOTE: paths below are set from the live-server inspection and may be adjusted.
set -eu

DOMAIN=rig.mit.edu
CERT_ARN=arn:aws:acm:us-east-2:278212569472:certificate/c34a3938-a305-405c-a4ae-7bda5413b1f3
REGION=us-east-2
COMPOSE_DIR=/home/ec2-user/src
CONF="$COMPOSE_DIR/certbot/conf"
WWW="$COMPOSE_DIR/certbot/www"
LIVE="$CONF/live/$DOMAIN"
LOG=/home/ec2-user/out/logs/cert-renew.log

echo "=== $(date -u) renew start ===" >> "$LOG"

# 1) Renew via the certbot container (webroot HTTP-01; ALB forwards the ACME path to nginx).
sudo docker run --rm \
  -v "$CONF:/etc/letsencrypt" \
  -v "$WWW:/var/www/certbot" \
  certbot/certbot renew --webroot -w /var/www/certbot --non-interactive >> "$LOG" 2>&1 || \
  echo "certbot renew returned non-zero (may be 'not yet due')" >> "$LOG"

# 2) Re-import the current live cert into the ACM ARN (idempotent; ALB uses the same ARN).
#    files are root-owned under certbot/conf, so read them via sudo into the import.
sudo aws acm import-certificate --region "$REGION" \
  --certificate-arn "$CERT_ARN" \
  --certificate       "fileb://$LIVE/cert.pem" \
  --private-key       "fileb://$LIVE/privkey.pem" \
  --certificate-chain "fileb://$LIVE/chain.pem" >> "$LOG" 2>&1

NOTAFTER=$(sudo aws acm describe-certificate --region "$REGION" --certificate-arn "$CERT_ARN" \
  --query 'Certificate.NotAfter' --output text 2>>"$LOG")
echo "=== $(date -u) done; ACM NotAfter=$NOTAFTER ===" >> "$LOG"
