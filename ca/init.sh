#!/bin/sh

set -eu

CA_DIR="${CA_DIR:-/ca}"
CA_SUBJECT="${CA_SUBJECT:-/C=CA/ST=QC/L=Taram/O=TaramMeteo/OU=PKI/CN=TaramMeteo Root CA}"
CA_DAYS="${CA_DAYS:-3650}"

mkdir -p "$CA_DIR"

umask 077

CA_KEY="$CA_DIR/ca.key"
CA_CERT="$CA_DIR/ca.pem"
if [ ! -s "$CA_KEY" ] || [ ! -s "$CA_CERT" ]; then
  echo "Generating CA into $CA_DIR"

  openssl genrsa -out "$CA_KEY" 4096

  openssl req -x509 -new -nodes \
    -key "$CA_KEY" \
    -sha256 -days "$CA_DAYS" \
    -out "$CA_CERT" \
    -subj "$CA_SUBJECT"
  chmod 600 "$CA_KEY" || true
  chmod 644 "$CA_CERT" || true
else
  echo "Existing CA found in $CA_DIR"
fi
