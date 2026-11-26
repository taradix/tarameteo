#!/bin/sh

set -eu

: "${MQTT_USERNAME:?}"
: "${MQTT_PASSWORD:?}"
: "${MOSQUITTO_TEMPLATE:?}"

MOSQUITTO_CONFIG_DIR=${MOSQUITTO_CONFIG_DIR:-/mosquitto/config}
MOSQUITTO_DATA_DIR=${MOSQUITTO_DATA_DIR:-/mosquitto/data}

# Create conf from template.
MOSQUITTO_CONF=$MOSQUITTO_CONFIG_DIR/mosquitto.conf
install -o mosquitto -g mosquitto -m 600 /dev/null "$MOSQUITTO_CONF"
export MOSQUITTO_CONFIG_DIR MOSQUITTO_DATA_DIR
envsubst < "$MOSQUITTO_TEMPLATE" > "$MOSQUITTO_CONF"

# Create password file for backend services (username/password auth).
MOSQUITTO_PASSWD=$MOSQUITTO_CONFIG_DIR/passwd
# mosquitto_passwd wants the file owned by its user (root), the broker by mosquitto.
install -m 600 /dev/null "$MOSQUITTO_PASSWD"
mosquitto_passwd -b "$MOSQUITTO_PASSWD" "$MQTT_USERNAME" "$MQTT_PASSWORD"
chown mosquitto:mosquitto "$MOSQUITTO_PASSWD"

# Sensor ACL — cert CN is the username; a sensor may only publish to its own topic,
# and reads the firmware manifests (firmware/<board>) to update itself.
MOSQUITTO_SENSOR_ACL=$MOSQUITTO_CONFIG_DIR/acl_sensor.conf
install -o mosquitto -g mosquitto -m 600 /dev/null "$MOSQUITTO_SENSOR_ACL"
cat <<EOF > "$MOSQUITTO_SENSOR_ACL"
pattern write weather/%u/#
pattern write status/%u
pattern read firmware/+
EOF

# Consumer ACL — password-authenticated backend service; may read all sensor events
# and publishes the firmware manifests.
MOSQUITTO_CONSUMER_ACL=$MOSQUITTO_CONFIG_DIR/acl_consumer.conf
install -o mosquitto -g mosquitto -m 600 /dev/null "$MOSQUITTO_CONSUMER_ACL"
cat <<EOF > "$MOSQUITTO_CONSUMER_ACL"
user ${MQTT_USERNAME}
topic read weather/+/event
topic write firmware/+
EOF

exec "$@"
