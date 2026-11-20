"""Unit tests for the MQTT module."""

import paho.mqtt.client as mqtt
from hamcrest import (
    assert_that,
    empty,
    has_item,
    has_properties,
)

from tarameteo.mqtt import MQTTConsumer


def test_mqtt_consumer_skips_invalid_json(logger_handler):
    """A malformed payload should be logged, not raised into paho's network thread."""
    messages = []
    consumer = MQTTConsumer(
        host="localhost",
        cafile="ca.pem",
        client_id="test",
        topic="weather/+/event",
        on_message=messages.append,
    )
    msg = mqtt.MQTTMessage(topic=b"weather/test/event")
    msg.payload = b"not json"

    consumer._on_message(None, None, msg)

    assert_that(messages, empty())
    assert_that(logger_handler.records, has_item(has_properties(levelname="WARNING")))
