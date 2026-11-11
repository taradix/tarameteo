"""API service."""

import asyncio
import logging
import os
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from taraqueue import Queue, QueueEmpty

from tarameteo import alert_text
from tarameteo.alert_checker import manage_url
from tarameteo.alerts import Alert, AlertCreate, AlertStore, ManageRequest
from tarameteo.ca_client import (
    CAClient,
    IssueCertificateRequest,
    IssueCertificateResponse,
    get_ca_client,
    require_token,
)
from tarameteo.consumer import run as run_consumer
from tarameteo.db import SessionLocal
from tarameteo.notifier import SmtpNotifier
from tarameteo.sensors import (
    AggregateReading,
    BBox,
    ClusterList,
    SensorInfo,
    SensorList,
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
    app.state.manage_sent = {}

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
                run_sync(app.state.ts_writer, app.state.queue, notifier=notifier, alert_secret=alert_secret, alert_base_url=app.state.alert_base_url),
                name="sources-sync",
            ),
        )

        tasks.append(
            asyncio.create_task(
                run_consumer(app.state.ts_writer, app.state.queue, notifier=notifier, alert_secret=alert_secret, alert_base_url=app.state.alert_base_url),
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


@app.post("/api/certs", response_model=IssueCertificateResponse, dependencies=[Depends(require_token)])
def post_cert(
    request: IssueCertificateRequest,
    ca_client: Annotated[CAClient, Depends(get_ca_client)],
) -> IssueCertificateResponse:
    # Server certificates are issued on the internal network only (mosquitto-init calls the CA directly).
    if request.server_auth:
        raise HTTPException(status_code=403, detail="Server certificates are not issued through the public API")
    return ca_client.issue_certificate(request)


BBOX_DESCRIPTION = "Map area as west,south,east,north in degrees; west > east crosses the antimeridian"


def _parse_bbox(value: str) -> BBox:
    try:
        bbox = BBox(*(float(v) for v in value.split(",")))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="bbox must be west,south,east,north") from None
    if not (
        -180 <= bbox.west <= 180 and -180 <= bbox.east <= 180 and -90 <= bbox.south <= bbox.north <= 90
    ):
        raise HTTPException(status_code=422, detail="bbox is out of range, or south is above north")
    return bbox


@app.get("/api/sensors")
def get_sensors(
    service: SensorServiceDep,
    names: Annotated[list[str] | None, Query(max_length=100, description="Only sensors with these exact names")] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100, description="Only names containing this, any case")] = None,
    bbox: Annotated[str | None, Query(description=BBOX_DESCRIPTION)] = None,
    latitude: Annotated[float | None, Query(ge=-90, le=90, description="Sort nearest first from this point")] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180, description="Sort nearest first from this point")] = None,
    radius: Annotated[float | None, Query(gt=0, description="Only sensors within this many km of the point")] = None,
    limit: Annotated[int | None, Query(ge=1, le=200, description="At most this many sensors; see truncated")] = None,
) -> SensorList:
    near = (latitude, longitude) if latitude is not None and longitude is not None else None
    if near is None and (latitude, longitude, radius) != (None, None, None):
        raise HTTPException(status_code=422, detail="latitude and longitude go together, and radius needs both")
    return service.list_sensors(
        names=names,
        q=q,
        bbox=_parse_bbox(bbox) if bbox is not None else None,
        near=near,
        radius_km=radius,
        limit=limit,
    )


@app.get("/api/sensors/clusters")
def get_sensor_clusters(
    service: SensorServiceDep,
    bbox: Annotated[str, Query(description=BBOX_DESCRIPTION)],
    zoom: Annotated[int, Query(ge=0, le=22, description="Map zoom level, which sets the cluster size")],
) -> ClusterList:
    return service.cluster_sensors(_parse_bbox(bbox), zoom)


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


def get_alert_store() -> Iterator[AlertStore]:
    db = SessionLocal()
    try:
        yield AlertStore(db)
    finally:
        db.close()


AlertStoreDep = Annotated[AlertStore, Depends(get_alert_store)]

CONFIRM_EXPIRY = timedelta(days=1)
MAX_ALERTS = 20
# Confirm emails an address can be sent per day, so the form can't flood a stranger's inbox.
# ponytail: no per-IP limit; add one (at the proxy) if someone sprays many addresses.
MAX_PENDING = 3


@app.post("/api/alerts", status_code=201)
async def post_alert(body: AlertCreate, request: Request, alert_store: AlertStoreDep) -> dict[str, str]:
    secret = request.app.state.alert_secret
    notifier = request.app.state.notifier
    base_url = request.app.state.alert_base_url

    if not secret or not notifier:
        raise HTTPException(status_code=503, detail="Alert service not configured")

    alert_store.delete_unconfirmed(datetime.now(UTC) - CONFIRM_EXPIRY)
    if alert_store.count_by_email(body.email) >= MAX_ALERTS:
        raise HTTPException(status_code=409, detail=f"At most {MAX_ALERTS} alerts per email")
    # Same answer as when sent, so this doesn't tell anyone about the address.
    if alert_store.count_by_email(body.email, confirmed=False) >= MAX_PENDING:
        return {"status": "confirmation_sent"}

    alert = Alert(id=uuid.uuid4().hex, **body.model_dump())
    alert_store.create(alert)

    token = sign_token({"alert_id": alert.id, "action": "confirm"}, secret, expires_in=CONFIRM_EXPIRY.total_seconds())
    subject, email_body = alert_text.email(alert, "confirm", f"{base_url}/api/alerts/confirm/{token}")
    await notifier.send(alert.email, subject, email_body)
    return {"status": "confirmation_sent"}


def _token_payload(token: str, action: str, request: Request) -> dict | None:
    secret = request.app.state.alert_secret
    payload = verify_token(token, secret) if secret else None
    return payload if payload and payload.get("action") == action else None


def _token_alert_id(token: str, action: str, request: Request) -> str | None:
    payload = _token_payload(token, action, request)
    return payload and payload["alert_id"]


def _html(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(content, status_code=status_code)


INVALID_PAGE = alert_text.page("fr", alert_text.INVALID)
GONE_PAGE = alert_text.page("fr", alert_text.GONE)

# Email links only show a button; acting on GET would let link scanners confirm or stop alerts.


@app.get("/api/alerts/confirm/{token}", response_class=HTMLResponse)
def confirm_alert_page(token: str, request: Request, alert_store: AlertStoreDep) -> HTMLResponse:
    alert_id = _token_alert_id(token, "confirm", request)
    if alert_id is None:
        return _html(INVALID_PAGE, 400)
    alert = alert_store.get(alert_id)
    if alert is None:
        return _html(GONE_PAGE, 404)
    text = alert_text.TEXT[alert.language]
    if alert.confirmed:
        return _html(alert_text.page(alert.language, text["confirmed"].format(rule=alert_text.rule(alert))))
    return _html(alert_text.page(alert.language, text["confirm_title"], alert_text.rule(alert), button=text["confirm_button"]))


@app.post("/api/alerts/confirm/{token}", response_class=HTMLResponse)
def confirm_alert(token: str, request: Request, alert_store: AlertStoreDep) -> HTMLResponse:
    alert_id = _token_alert_id(token, "confirm", request)
    if alert_id is None:
        return _html(INVALID_PAGE, 400)
    alert_store.confirm(alert_id)
    alert = alert_store.get(alert_id)
    if alert is None:
        return _html(GONE_PAGE, 404)
    text = alert_text.TEXT[alert.language]
    return _html(alert_text.page(alert.language, text["confirmed"].format(rule=alert_text.rule(alert))))


@app.get("/api/alerts/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_alert_page(token: str, request: Request, alert_store: AlertStoreDep) -> HTMLResponse:
    alert_id = _token_alert_id(token, "unsubscribe", request)
    if alert_id is None:
        return _html(INVALID_PAGE, 400)
    alert = alert_store.get(alert_id)
    if alert is None:
        return _html(GONE_PAGE, 404)
    text = alert_text.TEXT[alert.language]
    return _html(alert_text.page(alert.language, text["remove_title"], alert_text.rule(alert), button=text["remove_button"]))


# Also the one-click unsubscribe target for the List-Unsubscribe-Post header.
@app.post("/api/alerts/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_alert(token: str, request: Request, alert_store: AlertStoreDep) -> HTMLResponse:
    alert_id = _token_alert_id(token, "unsubscribe", request)
    if alert_id is None:
        return _html(INVALID_PAGE, 400)
    alert = alert_store.get(alert_id)
    if alert is None:
        return _html(GONE_PAGE, 404)
    alert_store.delete(alert_id)
    return _html(alert_text.page(alert.language, alert_text.TEXT[alert.language]["removed"]))


MANAGE_EXPIRY = timedelta(hours=1)
# One manage email per address this often, so the form can't flood an inbox.
MANAGE_EVERY = timedelta(minutes=5)


@app.post("/api/alerts/manage", status_code=202)
async def post_alert_manage(body: ManageRequest, request: Request, alert_store: AlertStoreDep) -> dict[str, str]:
    """Email a link to see and stop the address's alerts; the answer is the same whether or not it has any."""
    state = request.app.state
    if not state.alert_secret or not state.notifier:
        raise HTTPException(status_code=503, detail="Alert service not configured")

    email, now = body.email.lower(), datetime.now(UTC)
    # ponytail: in-memory and per process, so a restart forgets it; fine for one API process.
    sent = state.manage_sent
    if alert_store.count_by_email(email) and now - sent.get(email, datetime.min.replace(tzinfo=UTC)) >= MANAGE_EVERY:
        sent[email] = now
        url = manage_url(email, body.language, state.alert_secret, state.alert_base_url, MANAGE_EXPIRY)
        text = alert_text.TEXT[body.language]
        await state.notifier.send(body.email, text["manage_subject"], text["manage_body"].format(url=url))
    return {"status": "sent"}


@app.get("/api/alerts/manage/{token}", response_class=HTMLResponse)
def alert_manage_page(token: str, request: Request, alert_store: AlertStoreDep) -> HTMLResponse:
    payload = _token_payload(token, "manage", request)
    if payload is None:
        return _html(INVALID_PAGE, 400)
    email = payload["email"]
    return _html(alert_text.manage_page(payload["language"], email, alert_store.list_by_email(email)))


@app.post("/api/alerts/manage/{token}")
def alert_manage(
    token: str,
    request: Request,
    alert_store: AlertStoreDep,
    alert: Annotated[str | None, Query(description="The alert to stop; all of them when left out")] = None,
) -> Response:
    payload = _token_payload(token, "manage", request)
    if payload is None:
        return _html(INVALID_PAGE, 400)
    alert_store.delete_by_email(payload["email"], alert)
    # Back to the list, as a GET, so reloading doesn't post again.
    return RedirectResponse(request.url.path, status_code=303)


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
