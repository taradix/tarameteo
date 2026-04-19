"""MQTT module with mTLS support and automatic certificate rotation handling."""

import json
import logging
import os
import ssl
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, Self

import paho.mqtt.client as mqtt
from attrs import define, field
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

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


@define(eq=False)
class _CertWatchHandler(FileSystemEventHandler):
    """Watchdog handler that detects certificate file changes with debounce."""

    _cert_paths: set[str]
    _callback: Callable[[], None]
    _debounce_seconds: float = 2.0
    _timer: threading.Timer | None = field(init=False, default=None)
    _lock: threading.Lock = field(init=False, factory=threading.Lock)

    def __attrs_post_init__(self):
        super().__init__()

    def on_modified(self, event):
        self._handle(event)

    def on_moved(self, event):
        self._handle(event)

    def _handle(self, event):
        if event.is_directory:
            return

        # atomic_write renames a temp file → dest_path is the real cert path
        path = getattr(event, "dest_path", None) or event.src_path
        resolved = str(Path(path).resolve())
        if resolved not in self._cert_paths:
            return

        logger.debug("Certificate file changed: %s", resolved)
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_seconds, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        logger.info("Debounce expired, triggering certificate reload")
        try:
            self._callback()
        except Exception:
            logger.exception("Error in cert reload callback")


@define
class MQTTBase:
    """Base class providing mTLS connection lifecycle and cert watching."""

    host: str
    cafile: str = field(kw_only=True)
    certfile: str = field(kw_only=True)
    keyfile: str = field(kw_only=True)
    client_id: str = field(kw_only=True)
    port: int = field(default=8883, kw_only=True)
    keepalive: int = field(default=60, kw_only=True)
    watch_certs: bool = field(default=True, kw_only=True)
    _client: mqtt.Client | None = field(init=False, default=None)
    _connected: threading.Event = field(init=False, factory=threading.Event)
    _reinit_lock: threading.Lock = field(init=False, factory=threading.Lock)
    _observer: Observer | None = field(init=False, default=None)
    _running: bool = field(init=False, default=False)

    @classmethod
    def from_env(cls, env=os.environ, **kwargs) -> Self:
        return cls(
            host=env.get("MQTT_BROKER_HOST", "mqtt"),
            port=int(env.get("MQTT_BROKER_PORT", "8883")),
            cafile=env["MQTT_CA_PATH"],
            certfile=env["MQTT_CERT_PATH"],
            keyfile=env["MQTT_KEY_PATH"],
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
        if self.watch_certs:
            self._start_cert_watcher()
        self._running = True

    def disconnect(self):
        """Stop cert watcher, networking loop, and disconnect."""
        self._running = False
        self._connected.clear()
        self._stop_cert_watcher()
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def reload(self):
        """Tear down and rebuild the MQTT client with fresh TLS context."""
        with self._reinit_lock:
            if not self._running:
                return
            logger.info("Reinitializing MQTT connection due to cert change")
            self._connected.clear()
            try:
                if self._client is not None:
                    self._client.loop_stop()
                    self._client.disconnect()
                self._client = self._build_client()
                self._client.connect(self.host, self.port, self.keepalive)
                self._client.loop_start()
            except Exception:
                logger.exception("Failed to reinitialize MQTT connection")

    def _start_cert_watcher(self):
        cert_paths = set()
        watch_dirs = set()
        for path_str in (self.cafile, self.certfile, self.keyfile):
            resolved = str(Path(path_str).resolve())
            cert_paths.add(resolved)
            watch_dirs.add(os.path.dirname(resolved))

        handler = _CertWatchHandler(cert_paths, lambda: self.reload())
        self._observer = Observer()
        for d in watch_dirs:
            self._observer.schedule(handler, d, recursive=False)
        self._observer.daemon = True
        self._observer.start()
        logger.info("Certificate watcher started for %s", watch_dirs)

    def _stop_cert_watcher(self):
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

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
