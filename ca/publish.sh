#!/bin/sh

set -eu

CA_TLS_DIR="${CA_TLS_DIR:-/tls}"
CA_TRUST_DIR="${CA_TRUST_DIR:-/trust}"

mkdir -p "$CA_TRUST_DIR"

echo "Publishing CA cert to trust volume"
cp -f "$CA_TLS_DIR/ca.pem" "$CA_TRUST_DIR/ca.pem"
chmod 644 "$CA_TRUST_DIR/ca.pem" || true
