"""API service."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from taraqueue import Queue, QueueEmpty

from tarameteo.ca_client import (
    CAClient,
    IssueCertificateRequest,
    IssueCertificateResponse,
    get_ca_client,
)
from tarameteo.consumer import run as run_consumer
from tarameteo.sensors import (
    AggregateReading,
    SensorEntry,
    SensorInfo,
    SensorService,
    WeatherReading,
)
from tarameteo.sources import run_sync
from tarameteo.ts import (
    InfluxReader,
    InfluxWriter,
    TSReader,
)

logger = logging.getLogger("uvicorn")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks (MQTT consumer and external sources) on startup."""
    tasks = []
    app.state.queue = Queue.from_url("memory://")
    app.state.ts_reader = None
    app.state.ts_writer = None

    if os.environ.get("INFLUX_URL"):
        app.state.ts_reader = InfluxReader.from_env()
        app.state.ts_writer = InfluxWriter.from_env()

        tasks.append(
            asyncio.create_task(
                run_sync(app.state.ts_writer, app.state.queue),
                name="sources-sync",
            ),
        )

        tasks.append(
            asyncio.create_task(
                run_consumer(app.state.ts_writer, app.state.queue),
                name="mqtt-consumer",
            ),
        )

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="TaraMeteo API",
    docs_url="/api/swagger",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

origins = [
    "http://172.22.1.5",
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_ts_reader(request: Request) -> TSReader:
    return request.app.state.ts_reader


TSReaderDep = Annotated[TSReader, Depends(get_ts_reader)]


def get_sensor_service(ts_reader: TSReaderDep) -> SensorService:
    return SensorService(ts_reader=ts_reader)


SensorServiceDep = Annotated[SensorService, Depends(get_sensor_service)]


def get_queue(request: Request) -> Queue:
    return request.app.state.queue


QueueDep = Annotated[Queue, Depends(get_queue)]


@app.post("/api/certs", response_model=IssueCertificateResponse)
def post_cert(
    request: IssueCertificateRequest,
    ca_client: Annotated[CAClient, Depends(get_ca_client)],
) -> IssueCertificateResponse:
    return ca_client.issue_certificate(request)


@app.get("/api/sensors")
def get_sensors(service: SensorServiceDep) -> dict[str, list[SensorEntry]]:
    return {"sensors": service.list_sensors()}


@app.get("/api/sensors/{name}")
def get_sensor(name: str, service: SensorServiceDep) -> SensorInfo:
    try:
        return service.get_sensor(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/sensors/{name}/weather")
def get_sensor_weather(
    name: str,
    service: SensorServiceDep,
    start: Annotated[datetime, Query(description="ISO timestamp (inclusive)")],
    end: Annotated[datetime | None, Query(description="ISO timestamp (exclusive)")] = None,
    limit: Annotated[int | None, Query(ge=1, le=10000)] = None,
) -> list[WeatherReading]:
    return service.get_weather(name, start=start, end=end, limit=limit)


@app.get("/api/sensors/{name}/weather/aggregate")
def get_sensor_weather_aggregate(
    name: str,
    service: SensorServiceDep,
    start: Annotated[datetime, Query(description="ISO timestamp (inclusive)")],
    end: Annotated[datetime | None, Query(description="ISO timestamp (exclusive)")] = None,
    limit: Annotated[int | None, Query(ge=1, le=10000)] = None,
) -> list[AggregateReading]:
    return service.get_weather_aggregate(name, start=start, end=end, limit=limit)


@app.get("/api/sensors/{name}/weather/latest")
def get_sensor_weather_latest(
    name: str,
    service: SensorServiceDep,
) -> WeatherReading:
    reading = service.get_latest(name)
    if reading is None:
        raise HTTPException(status_code=404, detail=f"No readings for sensor {name!r}")
    return reading


@app.get("/api/sensors/{name}/weather/stream")
async def stream_sensor_weather(name: str, request: Request, queue: QueueDep) -> StreamingResponse:
    async def event_generator():
        async with queue.connect(f"weather:{name}") as q:
            while not await request.is_disconnected():
                try:
                    message = await q.receive(timeout=60)
                    yield f"data: {message}\n\n"
                except QueueEmpty:
                    yield ": ping\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception at {request.url}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


@app.get("/healthz", include_in_schema=False)
def get_healthz() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
