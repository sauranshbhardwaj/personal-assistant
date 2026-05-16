from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_db
from app.main import create_app
from app.twilio_client import get_sms_client


class ApiFakeSmsClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_sms(self, to: str, body: str) -> None:
        self.sent.append((to, body))


def test_health_endpoint(db_session, settings) -> None:
    app = _test_app(db_session, settings, ApiFakeSmsClient())
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_twilio_inbound_accepts_form_payload(db_session, settings) -> None:
    fake_sms = ApiFakeSmsClient()
    app = _test_app(db_session, settings, fake_sms)
    with TestClient(app) as client:
        response = client.post(
            "/twilio/inbound",
            data={
                "From": settings.my_phone_number,
                "Body": "help",
            },
        )

    assert response.status_code == 200
    assert response.text == "<Response></Response>"
    assert fake_sms.sent
    assert "Commands:" in fake_sms.sent[-1][1]


def test_dev_today_returns_payload(db_session, settings) -> None:
    app = _test_app(db_session, settings, ApiFakeSmsClient())
    with TestClient(app) as client:
        response = client.get("/dev/today")

    assert response.status_code == 200
    assert response.json() == {
        "reminders": [],
        "calories": 0,
        "protein_grams": 0,
    }


def _test_app(db_session, settings: Settings, fake_sms: ApiFakeSmsClient):
    app = create_app(settings, init_database=False, start_scheduler=False)

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_sms_client] = lambda: fake_sms
    return app
