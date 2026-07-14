#!/bin/sh
# Local-dev-only self-signed TLS cert so `docker compose up` works out of the box.
# Staging/production mount real certificates (e.g. Let's Encrypt) into this same
# directory instead of running this script — hosting provider/ACME setup is
# deferred (ARCHITECTURE-SPINE.md#Deferred).
set -eu
cd "$(dirname "$0")"

if [ -f fullchain.pem ] && [ -f privkey.pem ]; then
    echo "Dev cert already present, skipping."
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout privkey.pem -out fullchain.pem \
    -subj "/CN=localhost"

echo "Generated self-signed dev cert: docker/certs/fullchain.pem, docker/certs/privkey.pem"
