"""Unit tests for the firmware endpoints."""

import hashlib

import pytest
from hamcrest import assert_that, equal_to, has_entries

from tarameteo.api import app, get_firmware_publisher, get_firmware_store
from tarameteo.firmware import MAX_SIZE, FirmwareStore

IMAGE = b"\xe9" + b"\x00" * 99


@pytest.fixture
def firmware_token(monkeypatch, unique):
    token = unique("text")
    monkeypatch.setenv("FIRMWARE_TOKEN", token)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def published():
    return []


@pytest.fixture
def firmware_app(api_app, tmp_path, published):
    app.dependency_overrides[get_firmware_store] = lambda: FirmwareStore(tmp_path, "https://example.test")
    app.dependency_overrides[get_firmware_publisher] = lambda: lambda board, manifest: published.append((board, manifest))
    try:
        yield api_app
    finally:
        app.dependency_overrides.pop(get_firmware_store, None)
        app.dependency_overrides.pop(get_firmware_publisher, None)


# What uploading IMAGE as esp32s3 1.2.0 to the firmware_app should make the latest.
MANIFEST = {
    "version": "1.2.0",
    "sha256": hashlib.sha256(IMAGE).hexdigest(),
    "size": len(IMAGE),
    "url": "https://example.test/api/firmware/esp32s3/1.2.0.bin",
}


def test_put_firmware(firmware_app, firmware_token, published):
    """Uploading an image should publish its manifest to the boards and return it."""
    response = firmware_app.put("/api/firmware/esp32s3/1.2.0.bin", content=IMAGE, headers=firmware_token)

    assert_that(response.status_code, equal_to(201))
    assert_that(response.json(), equal_to(MANIFEST))
    assert_that([(board, m.model_dump()) for board, m in published], equal_to([("esp32s3", MANIFEST)]))


def test_get_firmware(firmware_app, firmware_token):
    """Getting a board's firmware should return the manifest of its last upload."""
    firmware_app.put("/api/firmware/esp32s3/1.2.0.bin", content=IMAGE, headers=firmware_token)

    assert_that(firmware_app.get("/api/firmware/esp32s3").json(), equal_to(MANIFEST))


def test_get_firmware_image(firmware_app, firmware_token):
    """Getting an uploaded image should return its bytes, as the boards download them."""
    firmware_app.put("/api/firmware/esp32s3/1.2.0.bin", content=IMAGE, headers=firmware_token)

    assert_that(firmware_app.get("/api/firmware/esp32s3/1.2.0.bin").content, equal_to(IMAGE))


def test_put_firmware_replaces_latest(firmware_app, firmware_token):
    """A newer upload should become the latest, keeping the older image downloadable."""
    firmware_app.put("/api/firmware/esp32/1.0.0.bin", content=IMAGE, headers=firmware_token)
    firmware_app.put("/api/firmware/esp32/1.1.0.bin", content=IMAGE, headers=firmware_token)

    assert_that(firmware_app.get("/api/firmware/esp32").json(), has_entries(version="1.1.0"))
    assert_that(firmware_app.get("/api/firmware/esp32/1.0.0.bin").status_code, equal_to(200))


def test_put_firmware_without_token(firmware_app, firmware_token, published):
    """Uploading without the bearer token should be rejected and publish nothing."""
    response = firmware_app.put("/api/firmware/esp32/1.0.0.bin", content=IMAGE)

    assert_that(response.status_code, equal_to(401))
    assert_that(published, equal_to([]))


@pytest.mark.parametrize(("content", "status"), [
    (b"", 422),
    (b"\x00" * 100, 422),
    (b"\xe9" * (MAX_SIZE + 1), 413),
])
def test_put_firmware_invalid_image(firmware_app, firmware_token, published, content, status):
    """An empty, non-ESP or oversized image should be rejected and publish nothing."""
    response = firmware_app.put("/api/firmware/esp32/1.0.0.bin", content=content, headers=firmware_token)

    assert_that(response.status_code, equal_to(status))
    assert_that(published, equal_to([]))


@pytest.mark.parametrize("path", ["/api/firmware/esp32/..bin", "/api/firmware/.hidden/1.0.0.bin"])
def test_put_firmware_invalid_name(firmware_app, firmware_token, path):
    """Board and version names starting with a dot should be rejected, so they can't leave the store."""
    response = firmware_app.put(path, content=IMAGE, headers=firmware_token)

    assert_that(response.status_code, equal_to(422))


def test_put_firmware_publish_failure(firmware_app, firmware_token):
    """A manifest stored but not published should answer 502, so the workflow fails and can be rerun."""

    def fail(board, manifest):
        raise OSError("broker down")

    app.dependency_overrides[get_firmware_publisher] = lambda: fail
    response = firmware_app.put("/api/firmware/esp32/1.0.0.bin", content=IMAGE, headers=firmware_token)

    assert_that(response.status_code, equal_to(502))
    assert_that(firmware_app.get("/api/firmware/esp32").json(), has_entries(version="1.0.0"))


@pytest.mark.parametrize("missing", ["FIRMWARE_DIR", "FIRMWARE_BASE_URL"])
def test_store_from_env_requires(missing):
    """Without where to keep the images, or where boards download them, the store isn't made."""
    env = {"FIRMWARE_DIR": "/data/firmware", "FIRMWARE_BASE_URL": "https://example.test"}
    del env[missing]

    with pytest.raises(KeyError, match=missing):
        FirmwareStore.from_env(env)


def test_store_from_env(tmp_path):
    """The store keeps its images under FIRMWARE_DIR, with URLs on FIRMWARE_BASE_URL."""
    store = FirmwareStore.from_env({"FIRMWARE_DIR": str(tmp_path), "FIRMWARE_BASE_URL": "https://example.test/"})

    assert_that(store.add("esp32", "1.0.0", IMAGE).url, equal_to("https://example.test/api/firmware/esp32/1.0.0.bin"))


def test_get_firmware_unknown(firmware_app):
    """A board without images should answer 404."""
    assert_that(firmware_app.get("/api/firmware/esp32").status_code, equal_to(404))
    assert_that(firmware_app.get("/api/firmware/esp32/1.0.0.bin").status_code, equal_to(404))
