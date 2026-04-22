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

log_dest file ${MOSQUITTO_DATA_DIR}/mosquitto.log
log_dest stdout
log_type all
log_timestamp true
log_timestamp_format %Y-%m-%dT%H:%M:%S

# =============================================================================
# Network Listeners
# =============================================================================

listener 1883
protocol mqtt

listener 8883
protocol mqtt

cafile /etc/mosquitto/pki/ca.pem
certfile /tls/mosquitto.pem
keyfile /tls/mosquitto.key

# =============================================================================
# Security
# =============================================================================

require_certificate true
use_identity_as_username true

allow_anonymous false
acl_file ${MOSQUITTO_CONFIG_DIR}/acl.conf

# =============================================================================
# Performance & Limits
# =============================================================================

# Maximum number of concurrent connections
max_connections 1000

# Maximum number of queued messages per client
max_queued_messages 1000

# Maximum QoS level (0=fire-and-forget, 1=at-least-once, 2=exactly-once)
max_qos 1

# Max packet size (in bytes)
max_packet_size 8192

# =============================================================================
# MQTT Protocol Settings
# =============================================================================

# Retain messages across restarts
retained_persistence true

# Maximum number of inflight messages per client
max_inflight_messages 20

# =============================================================================
# System Topics
# =============================================================================

# Publish system information to $SYS topics
# Set to false to disable system topic publishing
sys_interval 10
