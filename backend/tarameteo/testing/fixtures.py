"""Testing fixtures."""

import logging

import pytest
from fastapi.testclient import TestClient

from tarameteo.api import app as _api_app
from tarameteo.api import get_queue, get_ts_reader
from tarameteo.ca import app as _ca_app
from tarameteo.ca_client import IssueCertificateRequest
from tarameteo.crypto import generate_key_pem
from tarameteo.fs import atomic_write
from tarameteo.logger import setup_logger
from tarameteo.pki import create_csr_pem
from tarameteo.testing.logger import LoggerHandler
from tarameteo.ts import (
    MemoryReader,
    MemoryStore,
    MemoryWriter,
)


@pytest.fixture
def memory_store():
    """Shared backing store for the memory reader and writer."""
    return MemoryStore()


@pytest.fixture
def memory_reader(memory_store):
    """In-memory TSReader backed by `memory_store`."""
    return MemoryReader(store=memory_store)


@pytest.fixture
def memory_writer(memory_store):
    """In-memory TSWriter backed by `memory_store`."""
    return MemoryWriter(store=memory_store)


@pytest.fixture
def api_app(memory_reader, memory_queue):
    """API testing app."""
    _api_app.dependency_overrides[get_ts_reader] = lambda: memory_reader
    _api_app.dependency_overrides[get_queue] = lambda: memory_queue
    try:
        with TestClient(_api_app) as client:
            yield client
    finally:
        _api_app.dependency_overrides.pop(get_ts_reader, None)
        _api_app.dependency_overrides.pop(get_queue, None)


@pytest.fixture
def ca_app():
    """CA testing app."""
    with TestClient(_ca_app) as client:
        yield client


@pytest.fixture(autouse=True)
def logger_handler():
    """Logger handler fixture."""
    handler = LoggerHandler()
    setup_logger(logging.DEBUG, handler)
    try:
        yield handler
    finally:
        setup_logger()


@pytest.fixture
def make_certs(ca_client, tmp_path):
    """Function to make temporary certificate files."""
    def func(cn, path=tmp_path):
        key_pem = generate_key_pem()
        csr_pem = create_csr_pem(key_pem, cn)
        request = IssueCertificateRequest(csr_pem=csr_pem)
        response = ca_client.issue_certificate(request)

        key_path = path / f"{cn}.key"
        cert_path = path / f"{cn}.pem"
        cafile_path = path / "ca.pem"

        atomic_write([
            (key_path, key_pem, 0o600),
            (cert_path, response.cert_pem, 0o644),
            (cafile_path, response.chain_pem[0], 0o644),
        ])

        return {
            "cafile": str(cafile_path),
            "certfile": str(cert_path),
            "keyfile": str(key_path),
        }

    return func
