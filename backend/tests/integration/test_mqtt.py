"""Integration tests for the MQTT module."""

import asyncio
import json

import pytest
from hamcrest import (
    assert_that,
    contains_exactly,
    has_properties,
    none,
)

from tarameteo.firmware import FirmwareManifest, publish_manifest
from tarameteo.mqtt import (
    MQTTBase,
    MQTTConsumer,
    MQTTMessage,
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
    """A connected paho client, publishing as a device would."""
    with MQTTBase(
        host=mosquitto_service.ip,
        port=8883,
        client_id="test-device",
        **make_certs("test-device"),
    ) as base:
        assert base.wait_connected(), "publisher did not connect"
        yield base._client


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
    mqtt_publisher.publish(topic="weather/test-device/event", payload=json.dumps("data"))

    await asyncio.wait_for(received.wait(), timeout=10.0)

    assert_that(messages, contains_exactly(has_properties(
        topic="weather/test-device/event",
        data="data",
        qos=0,
        retain=False,
    )))


@pytest.mark.asyncio
async def test_mqtt_receive_message_published_while_offline(make_mqtt_consumer, mqtt_publisher):
    """A QoS 0 message published while the consumer is offline should arrive when it reconnects."""
    loop = asyncio.get_running_loop()
    received = asyncio.Event()
    messages = []

    def handler(message: MQTTMessage):
        messages.append(message)
        loop.call_soon_threadsafe(received.set)

    consumer = make_mqtt_consumer("weather/+/event", handler)
    consumer._client.loop_stop()
    mqtt_publisher.publish(topic="weather/test-device/event", payload=json.dumps("data")).wait_for_publish(timeout=5)
    consumer._client.loop_start()

    await asyncio.wait_for(received.wait(), timeout=10.0)

    assert_that(messages, contains_exactly(has_properties(data="data")))


@pytest.fixture
def make_device_consumer(mosquitto_service, make_certs, unique):
    """Subscribes as a board would: its own certificate, on the sensor listener."""
    created: list[MQTTConsumer] = []

    def _make(topic: str, on_message):
        name = unique("text")
        consumer = MQTTConsumer(
            host=mosquitto_service.ip,
            port=8883,
            client_id=name,
            topic=topic,
            on_message=on_message,
            **make_certs(name),
        )
        consumer.connect()
        assert consumer.wait_connected(), "device did not subscribe"
        created.append(consumer)
        return consumer

    yield _make

    for c in created:
        c.disconnect()


@pytest.fixture
def manifest():
    return FirmwareManifest(version="1.2.0", sha256="0" * 64, size=1024, url="https://example.test/1.2.0.bin")


async def _first_message(make_device_consumer, topic: str, timeout: float) -> MQTTMessage | None:
    """The first message a board subscribing to topic gets, or None within timeout."""
    loop = asyncio.get_running_loop()
    received: asyncio.Future[MQTTMessage] = loop.create_future()

    def handler(message: MQTTMessage):
        loop.call_soon_threadsafe(lambda: received.done() or received.set_result(message))

    make_device_consumer(topic, handler)
    try:
        return await asyncio.wait_for(received, timeout=timeout)
    except TimeoutError:
        return None


@pytest.mark.asyncio
async def test_publish_manifest_reaches_boards(mosquitto_service, make_certs, make_device_consumer, manifest, unique):
    """The backend's manifest should be retained, so a board subscribing later gets it."""
    board = unique("text")
    publish_manifest(board, manifest, {
        "MQTT_BROKER_HOST": mosquitto_service.ip,
        "MQTT_BROKER_PORT": "8884",
        "MQTT_USERNAME": "admin",
        "MQTT_PASSWORD": "test",
        "MQTT_CA_PATH": make_certs("weather-consumer")["cafile"],
    })

    message = await _first_message(make_device_consumer, f"firmware/{board}", timeout=10.0)

    assert_that(message, has_properties(topic=f"firmware/{board}", data=manifest.model_dump(), retain=True))


@pytest.mark.asyncio
async def test_boards_cannot_publish_manifests(mqtt_publisher, make_device_consumer, manifest, unique):
    """A board publishing a manifest should be refused, so one station can't make others install an image."""
    board = unique("text")
    mqtt_publisher.publish(f"firmware/{board}", manifest.model_dump_json(), qos=1, retain=True).wait_for_publish(timeout=5)

    # The broker drops a refused publish silently, so the test is that nothing is retained.
    assert_that(await _first_message(make_device_consumer, f"firmware/{board}", timeout=2.0), none())
