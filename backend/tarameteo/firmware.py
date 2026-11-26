"""Firmware images the stations update to, with one manifest per board."""

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Self

import paho.mqtt.publish
from attrs import define
from pydantic import BaseModel, Field

from tarameteo.fs import atomic_write

# The size of an app slot in firmware/partitions.csv.
MAX_SIZE = 0x1E0000
# First byte of an ESP image header (esp_image_header_t.magic).
ESP_IMAGE_MAGIC = 0xE9
# Board and version name path segments, so no dots first (no "..").
NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$"


class FirmwareManifest(BaseModel):
    """The latest image of a board, which the boards parse (firmware/lib/OtaUpdater)."""

    version: str = Field(..., description="Release version, from the firmware-v<version> tag")
    sha256: str = Field(..., description="SHA-256 of the image, in lowercase hex")
    size: int = Field(..., description="Size of the image in bytes")
    url: str = Field(..., description="Where the boards download the image")


@define
class FirmwareStore:
    """The images under root/<board>/<version>.bin, each board's latest in root/<board>/manifest.json."""

    root: Path
    base_url: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Self:
        return cls(Path(env["FIRMWARE_DIR"]), env["FIRMWARE_BASE_URL"].rstrip("/"))

    def manifest(self, board: str) -> FirmwareManifest | None:
        try:
            return FirmwareManifest.model_validate_json((self.root / board / "manifest.json").read_text())
        except FileNotFoundError:
            return None

    def image(self, board: str, version: str) -> Path | None:
        path = self.root / board / f"{version}.bin"
        return path if path.is_file() else None

    def add(self, board: str, version: str, data: bytes) -> FirmwareManifest:
        """Store the image and make it the board's latest. Return its manifest."""
        manifest = FirmwareManifest(
            version=version,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
            url=f"{self.base_url}/api/firmware/{board}/{version}.bin",
        )
        directory = self.root / board
        atomic_write([
            (directory / f"{version}.bin", data, 0o644),
            (directory / "manifest.json", manifest.model_dump_json().encode(), 0o644),
        ])
        return manifest


def publish_manifest(board: str, manifest: FirmwareManifest, env: Mapping[str, str] = os.environ) -> None:
    """Publish the manifest retained on firmware/<board>, which the boards read each time they wake."""
    paho.mqtt.publish.single(
        f"firmware/{board}",
        manifest.model_dump_json(),
        qos=1,
        retain=True,
        hostname=env.get("MQTT_BROKER_HOST", "mqtt"),
        port=int(env.get("MQTT_BROKER_PORT", "8883")),
        auth={"username": env["MQTT_USERNAME"], "password": env.get("MQTT_PASSWORD")},
        tls={"ca_certs": env["MQTT_CA_PATH"]},
    )
