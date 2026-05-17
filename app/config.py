from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    database_url: str = "sqlite:///./health_reminders.db"
    nudge_interval_minutes: int = 15
    max_nudges: int = 4
    daily_summary_hour: int = 20
    sunday_goal_prompt_hour: int = 18
    timezone_name: str = "America/New_York"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "database_url",
            normalize_database_url(self.database_url),
        )

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./health_reminders.db"),
        nudge_interval_minutes=_int_env("NUDGE_INTERVAL_MINUTES", 15),
        max_nudges=_int_env("MAX_NUDGES", 4),
        daily_summary_hour=_int_env("DAILY_SUMMARY_HOUR", 20),
        sunday_goal_prompt_hour=_int_env("SUNDAY_GOAL_PROMPT_HOUR", 18),
        timezone_name=os.getenv("TIMEZONE", "America/New_York"),
    )


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return f"postgresql://{database_url.removeprefix('postgres://')}"
    return database_url
