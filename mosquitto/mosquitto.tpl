# Mosquitto MQTT Broker Configuration for TaraMeteo
# Documentation: https://mosquitto.org/man/mosquitto-conf-5.html

# =============================================================================
# General Configuration
# =============================================================================

# Persistence
persistence true
persistence_location ${MOSQUITTO_DATA_DIR}
autosave_interval 60

# =============================================================================
# Logging
# =============================================================================

log_dest stdout
log_type all
log_timestamp true
log_timestamp_format %Y-%m-%dT%H:%M:%S

# =============================================================================
# Network Listeners
# =============================================================================

per_listener_settings true

# Sensor listener — mTLS only. Certificate CN becomes the MQTT username.
listener 8883
protocol mqtt
cafile /etc/mosquitto/pki/ca.pem
certfile /tls/mosquitto.pem
keyfile /tls/mosquitto.key
# TLS 1.3 dropped RSA key exchange; pin to 1.2 so the cipher list below works.
tls_version tlsv1.2
# RSA key exchange only — no ephemeral DH. The client encrypts the session key
# with the server's RSA public key, so no EC scalar multiplications are needed
# on the ESP32, cutting TLS handshake time from ~15s to ~1s.
ciphers AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256
require_certificate true
use_identity_as_username true
acl_file ${MOSQUITTO_CONFIG_DIR}/acl_sensor.conf

# Consumer listener — TLS + password only. Internal Docker network, not published
# on the host. Separate ACL file keeps the two username namespaces isolated.
listener 8884
protocol mqtt
cafile /etc/mosquitto/pki/ca.pem
certfile /tls/mosquitto.pem
keyfile /tls/mosquitto.key
allow_anonymous false
password_file ${MOSQUITTO_CONFIG_DIR}/passwd
acl_file ${MOSQUITTO_CONFIG_DIR}/acl_consumer.conf

# =============================================================================
# Performance & Limits
# =============================================================================

# NOTE: max_connections and max_qos are per-listener, so here they only apply
# to the 8884 consumer listener above, not to the sensor listener.

# Maximum number of concurrent connections
max_connections 1000

# Maximum number of queued messages per client
max_queued_messages 1000

# Sensors can only publish at QoS 0 (PubSubClient), so queue QoS 0 messages
# too, for persistent subscribers that are offline, like the API during a restart.
queue_qos0_messages true

# Maximum QoS level (0=fire-and-forget, 1=at-least-once, 2=exactly-once)
max_qos 1

# Max packet size (in bytes)
max_packet_size 8192

# =============================================================================
# MQTT Protocol Settings
# =============================================================================

# Maximum number of inflight messages per client
max_inflight_messages 20

# =============================================================================
# System Topics
# =============================================================================

# Seconds between $SYS topic updates; 0 disables them.
sys_interval 10
