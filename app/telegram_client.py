from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

import httpx
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Message

logger = logging.getLogger(__name__)


class MessageClient(Protocol):
    def send_message(self, to: str, body: str) -> None:
        ...


class TelegramMessageClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send_message(self, to: str, body: str) -> None:
        if not self.settings.telegram_enabled:
            logger.info("No-op Telegram message to %s: %s", to, body)
            return

        url = self._api_url("sendMessage")
        response = httpx.post(
            url,
            json={
                "chat_id": self.settings.telegram_chat_id,
                "text": body,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        response.raise_for_status()

    def set_webhook(self, webhook_url: str) -> dict:
        if not self.settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required to set the webhook")

        response = httpx.post(
            self._api_url("setWebhook"),
            json={"url": webhook_url},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/{method}"


@lru_cache(maxsize=1)
def get_message_client() -> TelegramMessageClient:
    return TelegramMessageClient(get_settings())


def record_inbound_message(db: Session, chat_id: str, body: str) -> Message:
    message = Message(chat_id=chat_id, direction="inbound", body=body)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def send_message_and_record(
    db: Session,
    message_client: MessageClient,
    chat_id: str,
    body: str,
) -> Message:
    message = Message(chat_id=chat_id, direction="outbound", body=body)
    db.add(message)
    db.commit()
    message_client.send_message(chat_id, body)
    db.refresh(message)
    return message
