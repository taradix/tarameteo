"""MQTT module with mTLS support."""

import json
import logging
import os
import ssl
import threading
from collections.abc import Callable
from typing import Any, ClassVar, Self

import paho.mqtt.client as mqtt
from attrs import define, field

logger = logging.getLogger(__name__)

MQTTMessageHandler = Callable[["MQTTMessage"], None]


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

    clean_session: ClassVar[bool] = True
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
            clean_session=self.clean_session,
            protocol=mqtt.MQTTProtocolVersion.MQTTv311,
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
            self._post_connect()
        else:
            logger.error("Connection failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self._connected.clear()
        logger.info("Disconnected (rc=%s)", reason_code)

    def _post_connect(self):
        """Hook for subclasses to act after CONNACK; must mark the client ready."""
        self._connected.set()

    def wait_connected(self, timeout: float = 5.0) -> bool:
        """Block until the client is ready. Returns True on success.

        Ready means CONNACK received, plus SUBACK for consumers.
        """
        return self._connected.wait(timeout=timeout)

    def connect(self):
        """Build the client, connect, and start background networking."""
        if self._client is None:
            self._client = self._build_client()
            self._client.connect(self.host, self.port, self.keepalive)
        else:
            self._client.reconnect()
        self._client.loop_start()
        self._running = True

    def disconnect(self):
        """Stop networking loop and disconnect."""
        self._running = False
        self._connected.clear()
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


@define
class MQTTConsumer(MQTTBase):
    """MQTT subscriber that delivers messages to a single callback.

    The session is persistent, so the broker keeps the subscription and
    queues messages while the consumer is offline (an API restart, for
    example). That needs a stable ``client_id``.
    """

    clean_session: ClassVar[bool] = False
    topic: str = field(kw_only=True)
    on_message: MQTTMessageHandler = field(kw_only=True)
    qos: int = field(default=1, kw_only=True)

    def _build_client(self) -> mqtt.Client:
        client = super()._build_client()
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        return client

    def _post_connect(self):
        if self._client is not None:
            self._client.subscribe(self.topic, qos=self.qos)

    def _on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        if any(rc.is_failure for rc in reason_code_list):
            logger.error("Subscribe to %s failed: %s", self.topic, reason_code_list)
            return
        logger.info("Subscribed to %s (qos=%d)", self.topic, self.qos)
        self._connected.set()

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        # An exception escaping a paho callback kills its network thread.
        try:
            message = MQTTMessage.from_msg(msg)
        except ValueError:
            logger.warning("Invalid JSON payload on topic %s: %r", msg.topic, msg.payload[:100])
            return
        try:
            self.on_message(message)
        except Exception:
            logger.exception("Error in message callback for topic %s", msg.topic)

