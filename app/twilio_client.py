from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Message

logger = logging.getLogger(__name__)


class SmsClient(Protocol):
    def send_sms(self, to: str, body: str) -> None:
        ...


class TwilioSmsClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        if settings.twilio_enabled:
            try:
                from twilio.rest import Client

                self._client = Client(
                    settings.twilio_account_sid,
                    settings.twilio_auth_token,
                )
            except Exception:
                logger.exception("Unable to initialize Twilio client; using no-op sender")
                self._client = None

    def send_sms(self, to: str, body: str) -> None:
        if self._client is None or not self.settings.twilio_phone_number:
            logger.info("No-op SMS to %s: %s", to, body)
            return

        self._client.messages.create(
            to=to,
            from_=self.settings.twilio_phone_number,
            body=body,
        )


@lru_cache(maxsize=1)
def get_sms_client() -> TwilioSmsClient:
    return TwilioSmsClient(get_settings())


def record_inbound_message(db: Session, phone_number: str, body: str) -> Message:
    message = Message(phone_number=phone_number, direction="inbound", body=body)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def send_sms_and_record(
    db: Session,
    sms_client: SmsClient,
    phone_number: str,
    body: str,
) -> Message:
    message = Message(phone_number=phone_number, direction="outbound", body=body)
    db.add(message)
    db.commit()
    sms_client.send_sms(phone_number, body)
    db.refresh(message)
    return message
