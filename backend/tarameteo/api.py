"""API service."""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
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

from tarameteo.alerts import Alert, AlertCreate, AlertStore
from tarameteo.ca_client import (
    CAClient,
    IssueCertificateRequest,
    IssueCertificateResponse,
    get_ca_client,
)
from tarameteo.consumer import run as run_consumer
from tarameteo.db import SessionLocal
from tarameteo.notifier import SmtpNotifier
from tarameteo.sensors import (
    AggregateReading,
    SensorEntry,
    SensorInfo,
    SensorService,
    WeatherReading,
)
from tarameteo.sources import run_sync
from tarameteo.tokens import sign_token, verify_token
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

    # Alert infrastructure.
    alert_secret = os.environ.get("ALERT_SECRET", "")
    app.state.alert_secret = alert_secret
    app.state.alert_base_url = os.environ.get("ALERT_BASE_URL", "")
    app.state.alert_cooldown = timedelta(
        seconds=_parse_cooldown(os.environ.get("ALERT_COOLDOWN", "3600"))
    )

    # Notifier.
    notifier = None
    if os.environ.get("SMTP_HOST"):
        notifier = SmtpNotifier(
            host=os.environ["SMTP_HOST"],
            port=int(os.environ.get("SMTP_PORT", "587")),
            username=os.environ.get("SMTP_USERNAME", ""),
            password=os.environ.get("SMTP_PASSWORD", ""),
            from_address=os.environ.get("SMTP_FROM", "noreply@taram.ca"),
        )
    app.state.notifier = notifier

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
                run_consumer(app.state.ts_writer, app.state.queue, notifier=notifier, alert_secret=alert_secret, alert_base_url=app.state.alert_base_url, alert_cooldown=app.state.alert_cooldown),
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


def _parse_cooldown(value: str) -> float:
    """Parse cooldown value in seconds."""
    return float(value)


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


# --- Alert endpoints ---


def get_alert_store(request: Request) -> AlertStore:
    db = SessionLocal()
    try:
        return AlertStore(db)
    except Exception:
        db.close()
        raise


AlertStoreDep = Annotated[AlertStore, Depends(get_alert_store)]


@app.post("/api/alerts", status_code=201)
async def post_alert(body: AlertCreate, request: Request, alert_store: AlertStoreDep) -> dict[str, str]:
    secret = request.app.state.alert_secret
    notifier = request.app.state.notifier
    base_url = request.app.state.alert_base_url

    if not secret or not notifier:
        raise HTTPException(status_code=503, detail="Alert service not configured")

    alert_id = uuid.uuid4().hex
    alert = Alert(
        id=alert_id,
        email=body.email,
        sensor=body.sensor,
        field=body.field,
        condition=body.condition,
        threshold=body.threshold,
    )
    alert_store.create(alert)

    token = sign_token({"alert_id": alert_id, "action": "confirm"}, secret, expires_in=86400)
    confirm_url = f"{base_url}/api/alerts/confirm/{token}"

    subject = "Confirm your weather alert"
    email_body = (
        f"Please confirm your alert:\n\n"
        f"Sensor: {alert.sensor}\n"
        f"Condition: {alert.field} {alert.condition} {alert.threshold}\n\n"
        f"Click to confirm:\n{confirm_url}\n"
    )

    await notifier.send(alert.email, subject, email_body)
    return {"status": "confirmation_sent"}


@app.get("/api/alerts/confirm/{token}")
def confirm_alert(token: str, request: Request, alert_store: AlertStoreDep) -> dict[str, str]:
    secret = request.app.state.alert_secret
    payload = verify_token(token, secret)
    if not payload or payload.get("action") != "confirm":
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    alert_id = payload["alert_id"]
    if not alert_store.confirm(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found or already confirmed")

    return {"status": "confirmed"}


@app.get("/api/alerts/unsubscribe/{token}")
def unsubscribe_alert(token: str, request: Request, alert_store: AlertStoreDep) -> dict[str, str]:
    secret = request.app.state.alert_secret
    payload = verify_token(token, secret)
    if not payload or payload.get("action") != "unsubscribe":
        raise HTTPException(status_code=400, detail="Invalid token")

    alert_id = payload["alert_id"]
    if not alert_store.delete(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"status": "unsubscribed"}


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
