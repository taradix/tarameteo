"""API service."""

import logging
import os
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
from tarameteo.sensors import (
    SensorInfo,
    SensorService,
    WeatherReading,
)
from tarameteo.ts import (
    InfluxReader,
    TSReader,
)

logger = logging.getLogger("uvicorn")
app = FastAPI(
    title="TaraMeteo API",
    docs_url="/api/swagger",
    openapi_url="/api/openapi.json",
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


def get_ts_reader() -> TSReader:
    return InfluxReader.from_env()


TSReaderDep = Annotated[TSReader, Depends(get_ts_reader)]


def get_sensor_service(ts_reader: TSReaderDep) -> SensorService:
    return SensorService(ts_reader=ts_reader)


SensorServiceDep = Annotated[SensorService, Depends(get_sensor_service)]


def get_queue() -> Queue:
    return Queue.from_url(os.environ["QUEUE_URL"])


QueueDep = Annotated[Queue, Depends(get_queue)]


@app.post("/api/certs", response_model=IssueCertificateResponse)
def post_cert(
    request: IssueCertificateRequest,
    ca_client: Annotated[CAClient, Depends(get_ca_client)],
) -> IssueCertificateResponse:
    return ca_client.issue_certificate(request)


@app.get("/api/sensors")
def get_sensors(service: SensorServiceDep) -> dict[str, list[str]]:
    return {"sensors": service.list_sensors()}


@app.get("/api/sensors/{name}")
def get_sensor(name: str, service: SensorServiceDep) -> SensorInfo:
    return service.get_sensor(name)


@app.get("/api/sensors/{name}/weather/latest")
def get_sensor_weather_latest(
    name: str,
    service: SensorServiceDep,
) -> WeatherReading:
    reading = service.get_latest(name)
    if reading is None:
        raise HTTPException(status_code=404, detail=f"No readings for sensor {name!r}")
    return reading


@app.get("/api/sensors/{name}/weather")
def get_sensor_weather(
    name: str,
    service: SensorServiceDep,
    start: Annotated[datetime, Query(description="ISO timestamp (inclusive)")],
    end: Annotated[datetime | None, Query(description="ISO timestamp (exclusive)")] = None,
    limit: Annotated[int | None, Query(ge=1, le=10000)] = None,
) -> list[WeatherReading]:
    return service.get_weather(name, start=start, end=end, limit=limit)


@app.get("/api/sensors/{name}/weather/stream")
async def stream_sensor_weather(name: str, request: Request, queue: QueueDep) -> StreamingResponse:
    async def event_generator():
        async with queue.connect(f"weather:{name}") as q:
            while not await request.is_disconnected():
                try:
                    message = await q.receive(timeout=60)
                    yield f"data: {message}\n\n"
                except QueueEmpty:
                    pass

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
