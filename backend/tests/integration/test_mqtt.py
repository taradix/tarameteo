"""Integration tests for the MQTT module."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from hamcrest import (
    assert_that,
    contains_exactly,
    has_properties,
)
from pytest_xdocker.retry import retry

from tarameteo.mqtt import (
    MQTTConsumer,
    MQTTMessage,
    MQTTPublisher,
)


@pytest.fixture
def make_mqtt_consumer(mosquitto_service, make_certs):
    created: list[MQTTConsumer] = []

    def _make(topic: str, on_message):
        consumer = MQTTConsumer(
            host=mosquitto_service.ip,
            port=8883,
            client_id="weather-consumer",
            topic=topic,
            on_message=on_message,
            **make_certs("weather-consumer"),
        )
        consumer.connect()
        consumer.wait_connected()
        created.append(consumer)
        return consumer

    yield _make

    for c in created:
        c.disconnect()


@pytest.fixture
def mqtt_publisher(mosquitto_service, make_certs):
    with MQTTPublisher(
        host=mosquitto_service.ip,
        port=8883,
        client_id="test-device",
        **make_certs("test-device"),
    ) as publisher:
        yield publisher


@pytest.mark.asyncio
async def test_mqtt_receive_message(make_mqtt_consumer, mqtt_publisher):
    """Publishing a message should be received by the consumer."""
    received = asyncio.Event()
    messages = []

    def handler(message: MQTTMessage):
        received.set()
        messages.append(message)

    make_mqtt_consumer("weather/+/event", handler)
    mqtt_publisher.publish(topic="weather/test-device/event", payload="data")

    await asyncio.wait_for(received.wait(), timeout=10.0)

    assert_that(messages, contains_exactly(has_properties(
        topic="weather/test-device/event",
        data="data",
        qos=0,
        retain=False,
    )))


def test_mqtt_reload_certificates(make_certs, make_mqtt_consumer):
    """Updating certificates should call reload."""
    with patch.object(MQTTConsumer, "reload") as mock_reload:
        consumer = make_mqtt_consumer("weather/+/event", lambda _m: None)
        path = Path(consumer.cafile).parent
        make_certs("weather-consumer", path)

        retry(mock_reload.assert_called_once).catching(AssertionError)
