from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_db
from app.main import create_app
from app.telegram_client import get_message_client


class ApiFakeTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.webhooks: list[str] = []

    def send_message(self, to: str, body: str) -> None:
        self.sent.append((to, body))

    def set_webhook(self, webhook_url: str) -> dict:
        self.webhooks.append(webhook_url)
        return {"ok": True, "result": True}


def test_health_endpoint(db_session, settings) -> None:
    app = _test_app(db_session, settings, ApiFakeTelegramClient())
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_telegram_webhook_accepts_text_update(db_session, settings) -> None:
    fake_telegram = ApiFakeTelegramClient()
    app = _test_app(db_session, settings, fake_telegram)
    with TestClient(app) as client:
        response = client.post(
            "/telegram/webhook",
            json={
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "chat": {"id": int(settings.telegram_chat_id), "type": "private"},
                    "text": "help",
                },
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert fake_telegram.sent
    assert "Commands:" in fake_telegram.sent[-1][1]


def test_telegram_set_webhook_endpoint(db_session, settings) -> None:
    fake_telegram = ApiFakeTelegramClient()
    app = _test_app(db_session, settings, fake_telegram)
    with TestClient(app) as client:
        response = client.post(
            "/telegram/set-webhook",
            json={"url": "https://example.ngrok-free.app/telegram/webhook"},
        )

    assert response.status_code == 200
    assert response.json()["webhook_url"] == "https://example.ngrok-free.app/telegram/webhook"
    assert fake_telegram.webhooks == ["https://example.ngrok-free.app/telegram/webhook"]


def test_dev_today_returns_payload(db_session, settings) -> None:
    app = _test_app(db_session, settings, ApiFakeTelegramClient())
    with TestClient(app) as client:
        response = client.get("/dev/today")

    assert response.status_code == 200
    assert response.json() == {
        "reminders": [],
        "calories": 0,
        "protein_grams": 0,
    }


def _test_app(db_session, settings: Settings, fake_telegram: ApiFakeTelegramClient):
    app = create_app(settings, init_database=False, start_scheduler=False)

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_message_client] = lambda: fake_telegram
    return app
