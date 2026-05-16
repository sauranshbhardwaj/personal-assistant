from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db, init_db
from app.handlers import MessageHandler
from app.scheduler import build_today_payload, create_scheduler, send_test_reminder
from app.telegram_client import MessageClient, TelegramMessageClient, get_message_client


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
        title="Personal Telegram Health Reminder Assistant",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        db: Session = Depends(get_db),
        message_client: MessageClient = Depends(get_message_client),
    ) -> JSONResponse:
        payload = await request.json()
        message = _extract_telegram_text(payload)
        if message is None:
            return JSONResponse({"ok": True, "ignored": True})

        chat_id, body = message
        handler = MessageHandler(db, message_client, settings)
        handler.handle_inbound_message(chat_id, body)
        return JSONResponse({"ok": True})

    @app.post("/telegram/set-webhook")
    async def telegram_set_webhook(
        request: Request,
        message_client: TelegramMessageClient = Depends(get_message_client),
    ) -> JSONResponse:
        payload = await _read_optional_json(request)
        webhook_url = str(payload.get("url") or "").strip()
        if not webhook_url:
            webhook_url = f"{str(request.base_url).rstrip('/')}/telegram/webhook"

        try:
            result = message_client.set_webhook(webhook_url)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        return JSONResponse({"webhook_url": webhook_url, "telegram": result})

    @app.post("/dev/send-test-reminder")
    async def dev_send_test_reminder(
        request: Request,
        db: Session = Depends(get_db),
        message_client: MessageClient = Depends(get_message_client),
    ) -> JSONResponse:
        payload = await _read_optional_json(request)
        name = str(payload.get("name") or "test reminder")
        event = send_test_reminder(db, settings, message_client, name=name)
        return JSONResponse(
            {
                "event_id": event.id,
                "reminder_id": event.reminder_id,
                "status": event.status,
            }
        )

    @app.get("/dev/today")
    def dev_today(db: Session = Depends(get_db)) -> JSONResponse:
        if not settings.telegram_chat_id:
            return JSONResponse({"error": "TELEGRAM_CHAT_ID is not configured"}, status_code=400)
        return JSONResponse(build_today_payload(db, settings.telegram_chat_id, settings))

    return app


def _extract_telegram_text(payload: dict) -> tuple[str, str] | None:
    message = payload.get("message") or payload.get("edited_message")
    if not isinstance(message, dict):
        return None

    chat = message.get("chat")
    text = message.get("text")
    if not isinstance(chat, dict) or text is None:
        return None

    chat_id = chat.get("id")
    if chat_id is None:
        return None

    return str(chat_id), str(text)


async def _read_optional_json(request: Request) -> dict:
    raw_body = await request.body()
    if not raw_body:
        return {}
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


app = create_app()
