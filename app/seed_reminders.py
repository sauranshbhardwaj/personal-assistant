from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal, init_db
from app.models import Reminder, ReminderEvent
from app.reminder_catalog import OMEGA3_NAME
from app.scheduler import EVENT_HORIZON_DAYS, create_reminder_events


@dataclass(frozen=True)
class SeedReminderSpec:
    name: str
    dosage: str | None
    category: str
    instructions: str
    frequency: str
    times: list[str]
    start_date: date
    end_date: date | None = None


@dataclass(frozen=True)
class SeedResult:
    created_reminders: int
    updated_reminders: int
    created_events: int


PREDECIDED_REMINDERS = [
    SeedReminderSpec(
        name="Halovate Cream",
        dosage="Apply cream",
        category="medicine",
        instructions="Apply cream: Halovate Cream",
        frequency="daily",
        times=["12:00", "22:00"],
        start_date=date(2026, 5, 18),
        end_date=date(2026, 5, 24),
    ),
    SeedReminderSpec(
        name="Momrazone Cream",
        dosage="Apply cream",
        category="medicine",
        instructions="Apply cream: Momrazone Cream",
        frequency="daily",
        times=["12:00", "22:00"],
        start_date=date(2026, 5, 25),
        end_date=date(2026, 6, 14),
    ),
    SeedReminderSpec(
        name="Adhydra Lotion",
        dosage="Apply lotion",
        category="medicine",
        instructions="Apply lotion: Adhydra Lotion",
        frequency="daily",
        times=["10:00", "15:00", "20:00"],
        start_date=date(2026, 5, 18),
        end_date=date(2026, 6, 16),
    ),
    SeedReminderSpec(
        name="Uprise D3 Tablet",
        dosage="1 tablet",
        category="medicine",
        instructions="Take Uprise D3 Tablet 1 tablet",
        frequency="weekly Sunday",
        # The source reminder did not include a time; 09:00 is the seeded default.
        times=["09:00"],
        start_date=date(2026, 5, 31),
        end_date=date(2026, 7, 19),
    ),
    SeedReminderSpec(
        name="Creatine",
        dosage="Take creatine",
        category="supplement",
        instructions="Take creatine",
        frequency="daily",
        times=["15:00"],
        start_date=date(2026, 5, 18),
    ),
    SeedReminderSpec(
        name="Whey Protein",
        dosage="Take whey protein",
        category="supplement",
        instructions="Take whey protein",
        frequency="daily",
        times=["19:30"],
        start_date=date(2026, 5, 18),
    ),
    SeedReminderSpec(
        name=OMEGA3_NAME,
        dosage="1 tablet",
        category="supplement",
        instructions="Take Omega 3 Tablet 1 tablet",
        frequency="after lunch log",
        times=[],
        start_date=date(2026, 5, 18),
    ),
]


def seed_predecided_reminders(
    db: Session,
    settings: Settings,
    now: datetime | None = None,
) -> SeedResult:
    if not settings.telegram_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is required to seed reminders")

    created_reminders = 0
    updated_reminders = 0
    created_events = 0

    for spec in PREDECIDED_REMINDERS:
        reminder, created = _upsert_reminder(db, settings.telegram_chat_id, spec)
        if created:
            created_reminders += 1
        else:
            updated_reminders += 1

        if spec.times:
            created_events += create_reminder_events(
                db,
                reminder,
                settings,
                horizon_days=_horizon_days_for(spec),
                now=now,
            )

    return SeedResult(
        created_reminders=created_reminders,
        updated_reminders=updated_reminders,
        created_events=created_events,
    )


def main() -> None:
    settings = get_settings()
    init_db()
    db = SessionLocal()
    try:
        result = seed_predecided_reminders(db, settings)
    finally:
        db.close()

    print(
        "Seeded reminders: "
        f"{result.created_reminders} created, "
        f"{result.updated_reminders} updated, "
        f"{result.created_events} event(s) created."
    )


def _upsert_reminder(
    db: Session,
    chat_id: str,
    spec: SeedReminderSpec,
) -> tuple[Reminder, bool]:
    reminder = (
        db.query(Reminder)
        .filter(Reminder.chat_id == chat_id, Reminder.name == spec.name)
        .order_by(Reminder.created_at.desc(), Reminder.id.desc())
        .first()
    )
    created = reminder is None
    if reminder is None:
        reminder = Reminder(chat_id=chat_id)
        db.add(reminder)

    reminder.category = spec.category
    reminder.name = spec.name
    reminder.dosage = spec.dosage
    reminder.instructions = spec.instructions
    reminder.frequency = spec.frequency
    reminder.times_json = json.dumps(spec.times)
    reminder.start_date = spec.start_date
    reminder.end_date = spec.end_date
    reminder.status = "active"

    db.commit()
    db.refresh(reminder)
    return reminder, created


def _horizon_days_for(spec: SeedReminderSpec) -> int:
    if spec.end_date is None:
        return EVENT_HORIZON_DAYS
    return max((spec.end_date - spec.start_date).days + 1, 1)


def count_seeded_events(db: Session, chat_id: str, name: str) -> int:
    return (
        db.query(ReminderEvent)
        .join(Reminder)
        .filter(Reminder.chat_id == chat_id, Reminder.name == name)
        .count()
    )


if __name__ == "__main__":
    main()
