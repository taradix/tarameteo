#!/bin/sh

# Exit on any error
set -eu

# Configuration
LE_DIR="/etc/letsencrypt"
LIVE_DIR="${LE_DIR}/live/${SERVER_HOSTNAME}"
ARCHIVE_DIR="${LE_DIR}/archive/${SERVER_HOSTNAME}"
RENEWAL_DIR="${LE_DIR}/renewal"

if [ -e "${LIVE_DIR}/fullchain.pem" ] && [ -e "${LIVE_DIR}/privkey" ]; then
  echo "Reusing existing certificate for ${SERVER_HOSTNAME}!"
  exit 0
fi

mkdir -p "${LIVE_DIR}" "${ARCHIVE_DIR}" "${RENEWAL_DIR}"

# Generate private key and signed certificate
cat <<EOF > "$ARCHIVE_DIR/san.cnf"
[ req ]
distinguished_name = dn
req_extensions = req_ext
prompt = no

[ dn ]
CN = $SERVER_HOSTNAME

[ req_ext ]
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = $SERVER_HOSTNAME
IP.1  = $IPV4_NETWORK.2
IP.2  = $IPV4_NETWORK.3
IP.3  = $IPV4_NETWORK.4
IP.4  = $IPV4_NETWORK.5
IP.5  = $IPV4_NETWORK.6
EOF

openssl ecparam -name prime256v1 -genkey -noout -out "${ARCHIVE_DIR}/privkey1.pem"

SERIAL_HEX="0x$(openssl rand -hex 16)"
openssl req -new \
  -key "$ARCHIVE_DIR/privkey1.pem" \
  -config "$ARCHIVE_DIR/san.cnf" \
| openssl x509 -req \
  -CA /ca/ca.pem \
  -CAkey /ca/ca.key \
  -set_serial "$SERIAL_HEX" \
  -out "$ARCHIVE_DIR/cert1.pem" \
  -days 365 \
  -sha256 \
  -extfile "$ARCHIVE_DIR/san.cnf" \
  -extensions req_ext

# Create chain.pem (self-signed so chain = cert) and fullchain.pem (cert + chain)
cp "${ARCHIVE_DIR}/cert1.pem" "${ARCHIVE_DIR}/chain1.pem"
cat "${ARCHIVE_DIR}/cert1.pem" "${ARCHIVE_DIR}/chain1.pem" > "${ARCHIVE_DIR}/fullchain1.pem"

# Create symlinks in live directory
ln -sf "../../archive/${SERVER_HOSTNAME}/cert1.pem" "${LIVE_DIR}/cert.pem"
ln -sf "../../archive/${SERVER_HOSTNAME}/chain1.pem" "${LIVE_DIR}/chain.pem"
ln -sf "../../archive/${SERVER_HOSTNAME}/fullchain1.pem" "${LIVE_DIR}/fullchain.pem"
ln -sf "../../archive/${SERVER_HOSTNAME}/privkey1.pem" "${LIVE_DIR}/privkey.pem"

# Create a mock renewal config
cat <<EOF > "${RENEWAL_DIR}/${SERVER_HOSTNAME}.conf"
# Mock renewal configuration
version = 1.0.0
archive_dir = ${ARCHIVE_DIR}
cert = ${LIVE_DIR}/cert.pem
privkey = ${LIVE_DIR}/privkey.pem
chain = ${LIVE_DIR}/chain.pem
fullchain = ${LIVE_DIR}/fullchain.pem
EOF

echo "Generated self-signed certificate for ${SERVER_HOSTNAME}!"
