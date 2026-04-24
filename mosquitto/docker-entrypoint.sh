#!/bin/sh

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
install -o root -g root -m 644 /dev/null "$MOSQUITTO_PASSWD"
mosquitto_passwd -b "$MOSQUITTO_PASSWD" "$MQTT_USERNAME" "$MQTT_PASSWORD"

# Sensor ACL — cert CN is the username; a sensor may only publish to its own topic.
MOSQUITTO_SENSOR_ACL=$MOSQUITTO_CONFIG_DIR/acl_sensor.conf
install -o mosquitto -g mosquitto -m 600 /dev/null "$MOSQUITTO_SENSOR_ACL"
cat <<EOF > "$MOSQUITTO_SENSOR_ACL"
pattern write weather/%u/#
pattern write status/%u
EOF

# Consumer ACL — password-authenticated backend service; may read all sensor events.
MOSQUITTO_CONSUMER_ACL=$MOSQUITTO_CONFIG_DIR/acl_consumer.conf
install -o mosquitto -g mosquitto -m 600 /dev/null "$MOSQUITTO_CONSUMER_ACL"
cat <<EOF > "$MOSQUITTO_CONSUMER_ACL"
user ${MQTT_USERNAME}
topic read weather/+/event
EOF

exec "$@"
