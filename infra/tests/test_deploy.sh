#!/bin/bash
set -euo pipefail
DOMAIN="${1:-et.dandiproject.org}"

echo "=== Deploy Smoke Test ==="

# Health endpoint
echo -n "Health check... "
RESP=$(curl -sf "https://${DOMAIN}/" 2>&1) || { echo "FAIL: Health endpoint unreachable"; exit 1; }
echo "$RESP" | grep -q '"name"' || { echo "FAIL: Unexpected response shape"; exit 1; }
echo "PASS"

# TLS certificate
echo -n "TLS certificate... "
echo | openssl s_client -connect "${DOMAIN}:443" -servername "$DOMAIN" 2>/dev/null | \
  openssl x509 -noout -dates 2>/dev/null || { echo "FAIL: Invalid TLS cert"; exit 1; }
echo "PASS"

# No SSH port
echo -n "Port 22 closed... "
timeout 3 bash -c "echo >/dev/tcp/${DOMAIN}/22" 2>/dev/null && { echo "FAIL: Port 22 is open!"; exit 1; }
echo "PASS"

echo "=== All smoke tests passed ==="
