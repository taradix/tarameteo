"""Integration tests for the MQTT module."""

import asyncio

import pytest
from hamcrest import (
    assert_that,
    contains_exactly,
    has_properties,
)

from tarameteo.mqtt import (
    MQTTConsumer,
    MQTTMessage,
    MQTTPublisher,
)


@pytest.fixture
def make_mqtt_consumer(mosquitto_service, make_certs, unique):
    created: list[MQTTConsumer] = []
    certs = make_certs("weather-consumer")

    def _make(topic: str, on_message):
        consumer = MQTTConsumer(
            host=mosquitto_service.ip,
            port=8884,
            client_id=unique("text"),
            topic=topic,
            on_message=on_message,
            username="admin",
            password="test",
            cafile=certs["cafile"],
        )
        consumer.connect()
        assert consumer.wait_connected(), "consumer did not subscribe"
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
    loop = asyncio.get_running_loop()
    received = asyncio.Event()
    messages = []

    def handler(message: MQTTMessage):
        messages.append(message)
        loop.call_soon_threadsafe(received.set)

    make_mqtt_consumer("weather/+/event", handler)
    mqtt_publisher.publish(topic="weather/test-device/event", payload="data")

    await asyncio.wait_for(received.wait(), timeout=10.0)

    assert_that(messages, contains_exactly(has_properties(
        topic="weather/test-device/event",
        data="data",
        qos=0,
        retain=False,
    )))


@pytest.mark.asyncio
async def test_mqtt_receive_message_published_while_offline(make_mqtt_consumer, mqtt_publisher):
    """A message published while the consumer is offline should arrive when it reconnects.

    Simulates network loss (unclean disconnect) rather than clean disconnect,
    since persistent sessions are designed for connection failures, not explicit
    disconnect/reconnect cycles.
    """
    loop = asyncio.get_running_loop()
    received = asyncio.Event()
    messages = []

    def handler(message: MQTTMessage):
        messages.append(message)
        loop.call_soon_threadsafe(received.set)

    consumer = make_mqtt_consumer("weather/+/event", handler)
    # Simulate network loss by stopping the loop without sending DISCONNECT
    consumer._client.loop_stop()
    mqtt_publisher.publish(topic="weather/test-device/event", payload="data", qos=1).wait_for_publish(timeout=5)
    # Reconnect by restarting the loop - the client auto-reconnects
    consumer._client.loop_start()

    await asyncio.wait_for(received.wait(), timeout=10.0)

    assert_that(messages, contains_exactly(has_properties(data="data")))
