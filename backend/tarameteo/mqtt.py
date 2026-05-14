"""MQTT module with mTLS support."""

import json
import logging
import os
import ssl
import threading
from collections import deque
from collections.abc import Callable
from typing import Any, Self

import paho.mqtt.client as mqtt
from attrs import define, field

logger = logging.getLogger(__name__)

MQTTMessageHandler = Callable[["MQTTMessage"], None]


class MQTTPublisherQueueFull(Exception):
    """Raised when the MQTT publisher pre-connect queue is full."""


@define(frozen=True)
class MQTTMessage:

    topic: str
    data: Any
    qos: int
    retain: bool

    @classmethod
    def from_msg(cls, msg) -> "MQTTMessage":
        return cls(
            topic=msg.topic,
            data=json.loads(msg.payload),
            qos=msg.qos,
            retain=msg.retain,
        )


@define
class MQTTBase:
    """Base class providing mTLS connection lifecycle."""

    host: str
    cafile: str = field(kw_only=True)
    certfile: str | None = field(default=None, kw_only=True)
    keyfile: str | None = field(default=None, kw_only=True)
    username: str | None = field(default=None, kw_only=True)
    password: str | None = field(default=None, kw_only=True)
    client_id: str = field(kw_only=True)
    port: int = field(default=8883, kw_only=True)
    keepalive: int = field(default=60, kw_only=True)
    _client: mqtt.Client | None = field(init=False, default=None)
    _connected: threading.Event = field(init=False, factory=threading.Event)
    _running: bool = field(init=False, default=False)

    @classmethod
    def from_env(cls, env=os.environ, **kwargs) -> Self:
        return cls(
            host=env.get("MQTT_BROKER_HOST", "mqtt"),
            port=int(env.get("MQTT_BROKER_PORT", "8883")),
            cafile=env["MQTT_CA_PATH"],
            certfile=env.get("MQTT_CERT_PATH"),
            keyfile=env.get("MQTT_KEY_PATH"),
            username=env.get("MQTT_USERNAME"),
            password=env.get("MQTT_PASSWORD"),
            **kwargs,
        )

    @property
    def running(self) -> bool:
        return self._running

    def _build_client(self) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
        )
        client.tls_set(
            ca_certs=self.cafile,
            certfile=self.certfile,
            keyfile=self.keyfile,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        if self.username is not None:
            client.username_pw_set(self.username, self.password)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        return client

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to %s:%s", self.host, self.port)
            self._connected.set()
            self._post_connect()
        else:
            logger.error("Connection failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self._connected.clear()
        logger.info("Disconnected (rc=%s)", reason_code)

    def _post_connect(self):
        """Hook for subclasses to act after connection is established."""

    def wait_connected(self, timeout: float = 5.0) -> bool:
        """Block until the MQTT CONNACK is received. Returns True on success."""
        return self._connected.wait(timeout=timeout)

    def connect(self):
        """Build the client, connect, and start background networking."""
        self._client = self._build_client()
        self._client.connect(self.host, self.port, self.keepalive)
        self._client.loop_start()
        self._running = True

    def disconnect(self):
        """Stop networking loop and disconnect."""
        self._running = False
        self._connected.clear()
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


@define
class MQTTConsumer(MQTTBase):
    """MQTT subscriber that delivers messages to a single callback."""

    topic: str = field(kw_only=True)
    on_message: MQTTMessageHandler = field(kw_only=True)
    qos: int = field(default=1, kw_only=True)

    def _build_client(self) -> mqtt.Client:
        client = super()._build_client()
        client.on_message = self._on_message
        return client

    def _post_connect(self):
        if self._client is not None:
            self._client.subscribe(self.topic, qos=self.qos)
            logger.info("Subscribed to %s (qos=%d)", self.topic, self.qos)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        message = MQTTMessage.from_msg(msg)
        try:
            self.on_message(message)
        except Exception:
            logger.exception("Error in message callback for topic %s", msg.topic)


@define
class MQTTPublisher(MQTTBase):
    """MQTT publisher with pre-connect queuing and bounded backlog."""

    qos: int = field(default=0, kw_only=True)
    retain: bool = field(default=False, kw_only=True)
    max_pending: int = field(default=1000, kw_only=True)
    _pending: deque = field(init=False, factory=deque)
    _pending_lock: threading.Lock = field(init=False, factory=threading.Lock)

    def _post_connect(self):
        """Drain any messages that were enqueued before connection."""
        with self._pending_lock:
            count = len(self._pending)
            while self._pending:
                topic, payload, qos, retain = self._pending.popleft()
                self._client.publish(
                    topic=topic, payload=payload, qos=qos, retain=retain,
                )
            if count:
                logger.info("Drained %d pending publish(es)", count)

    def publish(self, topic: str, payload: Any, *,
                qos: int | None = None,
                retain: bool | None = None) -> mqtt.MQTTMessageInfo | None:
        """Publish a message.

        Non-bytes payloads are encoded: str → UTF-8, anything else → JSON.
        If the client is not yet connected, the message is enqueued (bounded
        by ``max_pending``); ``MQTTPublisherQueueFull`` is raised if full.
        Returns ``None`` for enqueued messages.
        """
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            payload = json.dumps(payload).encode("utf-8")

        resolved_qos = qos if qos is not None else self.qos
        resolved_retain = retain if retain is not None else self.retain

        with self._pending_lock:
            if not self._connected.is_set():
                if len(self._pending) >= self.max_pending:
                    raise MQTTPublisherQueueFull(
                        f"MQTT queue is full (max: {self.max_pending})"
                    )
                self._pending.append(
                    (topic, payload, resolved_qos, resolved_retain),
                )
                logger.debug("Enqueued publish to %s (not yet connected)", topic)
                return None

        return self._client.publish(
            topic=topic, payload=payload,
            qos=resolved_qos, retain=resolved_retain,
        )
