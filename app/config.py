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
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    my_phone_number: str | None = None
    database_url: str = "sqlite:///./health_reminders.db"
    nudge_interval_minutes: int = 15
    max_nudges: int = 4
    daily_summary_hour: int = 20
    sunday_goal_prompt_hour: int = 18
    timezone_name: str = "America/New_York"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def twilio_enabled(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_phone_number
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
        twilio_phone_number=os.getenv("TWILIO_PHONE_NUMBER"),
        my_phone_number=os.getenv("MY_PHONE_NUMBER"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./health_reminders.db"),
        nudge_interval_minutes=_int_env("NUDGE_INTERVAL_MINUTES", 15),
        max_nudges=_int_env("MAX_NUDGES", 4),
        daily_summary_hour=_int_env("DAILY_SUMMARY_HOUR", 20),
        sunday_goal_prompt_hour=_int_env("SUNDAY_GOAL_PROMPT_HOUR", 18),
        timezone_name=os.getenv("TIMEZONE", "America/New_York"),
    )
