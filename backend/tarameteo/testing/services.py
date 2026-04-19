"""Service fixtures."""

import sys
from functools import partial
from pathlib import Path

import pytest
from httpx import AsyncClient

from tarameteo.ca_client import get_ca_client
from tarameteo.testing.compose import ComposeServer
from tarameteo.ts import (
    InfluxReader,
    InfluxWriter,
)


@pytest.fixture(scope="session")
def project():
    return "test"


@pytest.fixture(scope="session")
def env_vars(project):
    """Environment variables for the services.

    Static because they are persisted in volumes, e.g. mysql-vol-1.
    """
    v = sys.version_info
    python_version = f"{v.major}.{v.minor}.{v.micro}"

    return {
        "CA_TOKEN": "test",
        "COMPOSE_PROJECT_NAME": project,
        "INFLUX_PASSWORD": "testtest",  # must be between 8 and 72 characters long
        "INFLUX_TOKEN": "test",
        "MQTT_PASSWORD": "test",
        "PYTHON_VERSION": python_version,
        "SERVER_HOSTNAME": "test.local",
    }


@pytest.fixture(scope="session")
def env_file(env_vars, request):
    """Environment file containing `env_vars`.

    Cached for troubleshooting purposes.
    """
    env_file = request.config.cache.makedir("compose") / "env"
    with env_file.open("w") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")

    return env_file


@pytest.fixture(scope="session")
def compose_files(request):
    directory = Path(request.config.rootdir)
    filenames = ["docker-compose.yml", "compose.yaml", "compose.yml"]
    while True:
        for filename in filenames:
            path = directory / filename
            if path.exists():
                all_files = directory.glob(f"{path.stem}.*")
                ordered_files = sorted(all_files, key=lambda p: len(p.name))
                return list(ordered_files)

        if directory == directory.parent:
            raise KeyError("Docker compose file not found")

        directory = directory.parent


@pytest.fixture(scope="session")
def compose_server(project, env_file, compose_files, process):
    return partial(
        ComposeServer,
        project=project,
        env_file=env_file,
        compose_files=compose_files,
        process=process,
    )


@pytest.fixture(scope="session")
def api_service(compose_server):
    """API service fixture."""
    server = compose_server("Application startup complete")
    with server.run("api") as service:
        yield service


@pytest.fixture
async def api_client(api_service):
    """Client to the API service fixture."""
    url = f"http://{api_service.ip}"
    async with AsyncClient(base_url=url, timeout=5.0) as client:
        yield client


@pytest.fixture(scope="session")
def ca_service(compose_server):
    """CA service fixture."""
    server = compose_server("Application startup complete")
    with server.run("ca") as service:
        yield service


@pytest.fixture
def ca_client(ca_service):
    """Client to the CA service fixture."""
    env = {
        "CA_URL": f"http://{ca_service.ip}/v1/certs",
        **ca_service.env,
    }
    yield from get_ca_client(env)


@pytest.fixture(scope="session")
def influxdb_service(compose_server):
    """InfluxDB service fixture."""
    server = compose_server("port=8086")
    with server.run("influxdb") as service:
        yield service


@pytest.fixture(scope="session")
def influxdb_reader(influxdb_service):
    env = influxdb_service.env
    return InfluxReader.from_url(
        url=f"http://{influxdb_service.ip}:8086",
        token=env["DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"],
        org=env["DOCKER_INFLUXDB_INIT_ORG"],
        bucket=env["DOCKER_INFLUXDB_INIT_BUCKET"],
    )


@pytest.fixture(scope="session")
def influxdb_writer(influxdb_service):
    env = influxdb_service.env
    return InfluxWriter.from_url(
        url=f"http://{influxdb_service.ip}:8086",
        token=env["DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"],
        org=env["DOCKER_INFLUXDB_INIT_ORG"],
        bucket=env["DOCKER_INFLUXDB_INIT_BUCKET"],
    )


@pytest.fixture(scope="session")
def mosquitto_service(compose_server):
    """Mosquitto service fixture."""
    server = compose_server("mosquitto version 2.0.22 running")
    with server.run("mosquitto") as service:
        yield service
