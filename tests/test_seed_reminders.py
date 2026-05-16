from __future__ import annotations

from datetime import date, datetime, timezone

from app.models import Reminder, ReminderEvent
from app.reminder_catalog import OMEGA3_NAME
from app.seed_reminders import seed_predecided_reminders


SEED_NOW = datetime(2026, 5, 16, 16, 0, tzinfo=timezone.utc)


def test_seed_script_does_not_duplicate_reminders_or_events(db_session, settings) -> None:
    first = seed_predecided_reminders(db_session, settings, now=SEED_NOW)
    event_count = db_session.query(ReminderEvent).count()

    second = seed_predecided_reminders(db_session, settings, now=SEED_NOW)

    assert first.created_reminders == 7
    assert first.created_events == event_count
    assert second.created_reminders == 0
    assert second.updated_reminders == 7
    assert second.created_events == 0
    assert db_session.query(Reminder).count() == 7
    assert db_session.query(ReminderEvent).count() == event_count


def test_halovate_date_range_and_times(db_session, settings) -> None:
    seed_predecided_reminders(db_session, settings, now=SEED_NOW)

    events = _events_for(db_session, "Halovate Cream")
    local_datetimes = [_local_datetime(event, settings) for event in events]

    assert len(events) == 14
    assert {local_dt.strftime("%H:%M") for local_dt in local_datetimes} == {"12:00", "22:00"}
    assert local_datetimes[0].strftime("%Y-%m-%d %H:%M") == "2026-05-18 12:00"
    assert local_datetimes[-1].strftime("%Y-%m-%d %H:%M") == "2026-05-24 22:00"


def test_momrazone_starts_after_halovate_ends(db_session, settings) -> None:
    seed_predecided_reminders(db_session, settings, now=SEED_NOW)

    halovate_dates = [_local_datetime(event, settings).date() for event in _events_for(db_session, "Halovate Cream")]
    momrazone_dates = [_local_datetime(event, settings).date() for event in _events_for(db_session, "Momrazone Cream")]

    assert max(halovate_dates) == date(2026, 5, 24)
    assert min(momrazone_dates) == date(2026, 5, 25)


def test_uprise_d3_creates_eight_sunday_reminders(db_session, settings) -> None:
    seed_predecided_reminders(db_session, settings, now=SEED_NOW)

    local_datetimes = [_local_datetime(event, settings) for event in _events_for(db_session, "Uprise D3 Tablet")]

    assert [local_dt.date() for local_dt in local_datetimes] == [
        date(2026, 5, 31),
        date(2026, 6, 7),
        date(2026, 6, 14),
        date(2026, 6, 21),
        date(2026, 6, 28),
        date(2026, 7, 5),
        date(2026, 7, 12),
        date(2026, 7, 19),
    ]
    assert all(local_dt.weekday() == 6 for local_dt in local_datetimes)
    assert {local_dt.strftime("%H:%M") for local_dt in local_datetimes} == {"09:00"}


def test_creatine_and_whey_use_rolling_thirty_day_horizon(db_session, settings) -> None:
    seed_predecided_reminders(db_session, settings, now=SEED_NOW)

    creatine = [_local_datetime(event, settings) for event in _events_for(db_session, "Creatine")]
    whey = [_local_datetime(event, settings) for event in _events_for(db_session, "Whey Protein")]

    assert len(creatine) == 30
    assert len(whey) == 30
    assert creatine[0].strftime("%Y-%m-%d %H:%M") == "2026-05-18 15:00"
    assert creatine[-1].strftime("%Y-%m-%d %H:%M") == "2026-06-16 15:00"
    assert whey[0].strftime("%Y-%m-%d %H:%M") == "2026-05-18 19:30"
    assert whey[-1].strftime("%Y-%m-%d %H:%M") == "2026-06-16 19:30"


def test_omega3_is_active_without_fixed_events(db_session, settings) -> None:
    seed_predecided_reminders(db_session, settings, now=SEED_NOW)

    omega = db_session.query(Reminder).filter(Reminder.name == OMEGA3_NAME).one()

    assert omega.status == "active"
    assert omega.frequency == "after lunch log"
    assert _events_for(db_session, OMEGA3_NAME) == []


def _events_for(db_session, name: str) -> list[ReminderEvent]:
    return (
        db_session.query(ReminderEvent)
        .join(Reminder)
        .filter(Reminder.name == name)
        .order_by(ReminderEvent.scheduled_at.asc())
        .all()
    )


def _local_datetime(event: ReminderEvent, settings):
    return event.scheduled_at.replace(tzinfo=timezone.utc).astimezone(settings.timezone)
