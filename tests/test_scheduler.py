from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models import Reminder, ReminderEvent
from app.scheduler import create_reminder_events, send_due_reminders


CHAT_ID = "123456789"


def test_create_reminder_events_skips_same_day_time_that_already_passed(
    db_session,
    fake_telegram,
    settings,
) -> None:
    reminder = _create_reminder(db_session, times=["00:30"])
    now = datetime(2026, 5, 16, 21, 30, tzinfo=timezone.utc)  # 5:30 PM in New York.

    created = create_reminder_events(db_session, reminder, settings, now=now)
    sent = send_due_reminders(db_session, settings, fake_telegram, now=now)

    events = db_session.query(ReminderEvent).order_by(ReminderEvent.scheduled_at.asc()).all()
    first_local = events[0].scheduled_at.replace(tzinfo=timezone.utc).astimezone(settings.timezone)
    assert created == 30
    assert sent == 0
    assert fake_telegram.sent == []
    assert first_local.date().isoformat() == "2026-05-17"
    assert first_local.strftime("%H:%M") == "00:30"
    assert all(event.scheduled_at > now.replace(tzinfo=None) for event in events)


def test_create_reminder_events_keeps_same_day_time_that_is_still_future(
    db_session,
    settings,
) -> None:
    reminder = _create_reminder(db_session, times=["23:00"])
    now = datetime(2026, 5, 16, 21, 30, tzinfo=timezone.utc)  # 5:30 PM in New York.

    created = create_reminder_events(db_session, reminder, settings, now=now)

    events = db_session.query(ReminderEvent).order_by(ReminderEvent.scheduled_at.asc()).all()
    first_local = events[0].scheduled_at.replace(tzinfo=timezone.utc).astimezone(settings.timezone)
    assert created == 30
    assert first_local.date().isoformat() == "2026-05-16"
    assert first_local.strftime("%H:%M") == "23:00"


def test_create_reminder_events_does_not_extend_past_finite_end_date(
    db_session,
    settings,
) -> None:
    reminder = _create_reminder(db_session, times=["09:00", "21:00"], end_date="2026-05-22")
    now = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)  # 10:00 AM in New York.

    created = create_reminder_events(db_session, reminder, settings, now=now)

    events = db_session.query(ReminderEvent).order_by(ReminderEvent.scheduled_at.asc()).all()
    first_local = events[0].scheduled_at.replace(tzinfo=timezone.utc).astimezone(settings.timezone)
    last_local = events[-1].scheduled_at.replace(tzinfo=timezone.utc).astimezone(settings.timezone)
    assert created == 13
    assert first_local.strftime("%Y-%m-%d %H:%M") == "2026-05-16 21:00"
    assert last_local.strftime("%Y-%m-%d %H:%M") == "2026-05-22 21:00"


def _create_reminder(
    db_session,
    times: list[str],
    end_date: str | None = None,
) -> Reminder:
    reminder = Reminder(
        chat_id=CHAT_ID,
        category="supplement",
        name="Magnesium Glycinate",
        dosage=None,
        instructions="Take Magnesium Glycinate",
        frequency="daily",
        times_json=json.dumps(times),
        start_date=datetime(2026, 5, 16).date(),
        end_date=datetime.fromisoformat(end_date).date() if end_date else None,
        status="active",
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)
    return reminder
