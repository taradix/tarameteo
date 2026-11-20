#!/bin/sh

set -eu

CA_DIR="${CA_DIR:-/ca}"
CA_SUBJECT="${CA_SUBJECT:-/C=CA/ST=QC/L=Taram/O=TaramMeteo/OU=PKI/CN=TaramMeteo Root CA}"
# RFC 5280 "no well-defined expiration date": the root must outlive every board it signed.
CA_NOT_AFTER="${CA_NOT_AFTER:-99991231235959Z}"

mkdir -p "$CA_DIR"

umask 077

CA_KEY="$CA_DIR/ca.key"
CA_CERT="$CA_DIR/ca.pem"
if [ ! -s "$CA_KEY" ] || [ ! -s "$CA_CERT" ]; then
  echo "Generating CA into $CA_DIR"

  openssl genrsa -out "$CA_KEY" 4096

  openssl req -x509 -new -nodes \
    -key "$CA_KEY" \
    -sha256 -not_after "$CA_NOT_AFTER" \
    -out "$CA_CERT" \
    -subj "$CA_SUBJECT"
  chmod 644 "$CA_CERT"
else
  echo "Existing CA found in $CA_DIR"
fi
