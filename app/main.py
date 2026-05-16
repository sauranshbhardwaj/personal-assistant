from __future__ import annotations

import json
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db, init_db
from app.handlers import SmsHandler
from app.scheduler import build_today_payload, create_scheduler, send_test_reminder
from app.twilio_client import SmsClient, get_sms_client


def create_app(
    settings: Settings | None = None,
    init_database: bool = True,
    start_scheduler: bool = True,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        fastapi_app.state.settings = settings
        fastapi_app.state.scheduler = None
        if init_database:
            init_db()
        if start_scheduler:
            scheduler = create_scheduler(settings=settings)
            scheduler.start()
            fastapi_app.state.scheduler = scheduler
        try:
            yield
        finally:
            scheduler = fastapi_app.state.scheduler
            if scheduler and scheduler.running:
                scheduler.shutdown(wait=False)

    app = FastAPI(
        title="Personal SMS Health Reminder Assistant",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/twilio/inbound")
    async def twilio_inbound(
        request: Request,
        db: Session = Depends(get_db),
        sms_client: SmsClient = Depends(get_sms_client),
    ) -> Response:
        # TODO: Verify Twilio request signatures before exposing this beyond
        # personal/local use.
        payload = await _read_twilio_payload(request)
        phone_number = payload.get("From", "")
        body = payload.get("Body", "")
        handler = SmsHandler(db, sms_client, settings)
        handler.handle_inbound_sms(phone_number, body)
        return Response("<Response></Response>", media_type="application/xml")

    @app.post("/dev/send-test-reminder")
    async def dev_send_test_reminder(
        request: Request,
        db: Session = Depends(get_db),
        sms_client: SmsClient = Depends(get_sms_client),
    ) -> JSONResponse:
        payload = await _read_optional_json(request)
        name = str(payload.get("name") or "test reminder")
        event = send_test_reminder(db, settings, sms_client, name=name)
        return JSONResponse(
            {
                "event_id": event.id,
                "reminder_id": event.reminder_id,
                "status": event.status,
            }
        )

    @app.get("/dev/today")
    def dev_today(db: Session = Depends(get_db)) -> JSONResponse:
        if not settings.my_phone_number:
            return JSONResponse({"error": "MY_PHONE_NUMBER is not configured"}, status_code=400)
        return JSONResponse(build_today_payload(db, settings.my_phone_number, settings))

    return app


async def _read_twilio_payload(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        raw_json = await request.json()
        return {str(key): str(value) for key, value in raw_json.items()}

    raw_body = (await request.body()).decode("utf-8")
    parsed = parse_qs(raw_body)
    return {key: values[0] if values else "" for key, values in parsed.items()}


async def _read_optional_json(request: Request) -> dict:
    raw_body = await request.body()
    if not raw_body:
        return {}
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


app = create_app()
