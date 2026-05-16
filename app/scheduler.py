from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import DailyGoal, MealLog, Reminder, ReminderEvent, utc_now
from app.telegram_client import MessageClient, get_message_client, send_message_and_record

EVENT_HORIZON_DAYS = 30


def create_reminder_events(
    db: Session,
    reminder: Reminder,
    settings: Settings,
    horizon_days: int = EVENT_HORIZON_DAYS,
    now: datetime | None = None,
) -> int:
    times = [time.fromisoformat(time_value) for time_value in json.loads(reminder.times_json)]
    now_local = _as_utc(now or utc_now()).astimezone(settings.timezone)
    now_utc = _to_utc_naive(now_local)
    today = now_local.date()
    start = max(reminder.start_date, today)

    if start == today and _all_times_have_passed_today(times, now_local):
        start += timedelta(days=1)

    horizon_end = start + timedelta(days=horizon_days - 1)
    end = min(reminder.end_date or horizon_end, horizon_end)
    if end < start:
        return 0

    created = 0
    current = start
    while current <= end:
        for local_time in times:
            local_dt = datetime.combine(current, local_time, tzinfo=settings.timezone)
            scheduled_at = _to_utc_naive(local_dt)
            if scheduled_at <= now_utc:
                continue
            exists = (
                db.query(ReminderEvent)
                .filter(
                    ReminderEvent.reminder_id == reminder.id,
                    ReminderEvent.scheduled_at == scheduled_at,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                ReminderEvent(
                    reminder_id=reminder.id,
                    chat_id=reminder.chat_id,
                    scheduled_at=scheduled_at,
                    due_at=scheduled_at,
                    status="pending",
                )
            )
            created += 1
        current += timedelta(days=1)
    db.commit()
    return created


def replenish_reminder_events(
    db: Session,
    settings: Settings,
    horizon_days: int = EVENT_HORIZON_DAYS,
) -> int:
    reminders = db.query(Reminder).filter(Reminder.status == "active").all()
    return sum(
        create_reminder_events(db, reminder, settings, horizon_days)
        for reminder in reminders
    )


def send_due_reminders(
    db: Session,
    settings: Settings,
    message_client: MessageClient,
    now: datetime | None = None,
) -> int:
    now = _to_utc_naive(now or utc_now())
    sent_count = 0

    due_events = (
        db.query(ReminderEvent)
        .filter(
            ReminderEvent.status.in_(["pending", "snoozed"]),
            ReminderEvent.due_at <= now,
        )
        .order_by(ReminderEvent.due_at.asc())
        .all()
    )
    for event in due_events:
        send_message_and_record(db, message_client, event.chat_id, _reminder_message(event))
        event.status = "sent"
        event.sent_at = now
        event.last_nudged_at = now
        event.nudge_count = 0
        sent_count += 1

    interval_start = now - timedelta(minutes=settings.nudge_interval_minutes)
    nudge_events = (
        db.query(ReminderEvent)
        .filter(
            ReminderEvent.status == "sent",
            ReminderEvent.last_nudged_at <= interval_start,
        )
        .order_by(ReminderEvent.last_nudged_at.asc())
        .all()
    )
    for event in nudge_events:
        if event.nudge_count >= settings.max_nudges:
            event.status = "missed"
            continue
        send_message_and_record(db, message_client, event.chat_id, _nudge_message(event))
        event.last_nudged_at = now
        event.nudge_count += 1
        sent_count += 1

    db.commit()
    return sent_count


def send_daily_summaries(
    db: Session,
    settings: Settings,
    message_client: MessageClient,
) -> int:
    chat_id = settings.telegram_chat_id
    if not chat_id:
        return 0
    body = render_summary(db, chat_id, settings)
    send_message_and_record(db, message_client, chat_id, body)
    return 1


def send_sunday_goal_prompt(
    db: Session,
    settings: Settings,
    message_client: MessageClient,
) -> int:
    chat_id = settings.telegram_chat_id
    if not chat_id:
        return 0
    body = (
        "Weekly goal check-in: text your target like "
        "'Set weekly goal 2000 calories 170g protein'."
    )
    send_message_and_record(db, message_client, chat_id, body)
    return 1


def render_summary(db: Session, chat_id: str, settings: Settings) -> str:
    start_utc, end_utc = _local_day_bounds(settings)
    done_events = _events_for_statuses(db, chat_id, start_utc, end_utc, ["done"])
    missed_events = _events_for_statuses(db, chat_id, start_utc, end_utc, ["missed"])
    calories, protein = _meal_totals(db, chat_id, start_utc, end_utc)
    goal = _active_goal(db, chat_id)

    lines = [
        "Today's summary:",
        f"Done reminders: {_event_names(done_events) or 'none'}",
        f"Missed reminders: {_event_names(missed_events) or 'none'}",
        f"Calories: {calories}",
        f"Protein: {protein}g",
    ]
    if goal:
        lines.append(f"Goal: {goal.calories} calories, {goal.protein_grams}g protein")
    return "\n".join(lines)


def render_today_status(db: Session, chat_id: str, settings: Settings) -> str:
    start_utc, end_utc = _local_day_bounds(settings)
    pending = _events_for_statuses(db, chat_id, start_utc, end_utc, ["pending"])
    sent = _events_for_statuses(db, chat_id, start_utc, end_utc, ["sent"])
    snoozed = _events_for_statuses(db, chat_id, start_utc, end_utc, ["snoozed"])
    return "\n".join(
        [
            "Today's reminders:",
            f"Pending: {_event_names(pending) or 'none'}",
            f"Sent: {_event_names(sent) or 'none'}",
            f"Snoozed: {_event_names(snoozed) or 'none'}",
        ]
    )


def build_today_payload(db: Session, chat_id: str, settings: Settings) -> dict:
    start_utc, end_utc = _local_day_bounds(settings)
    calories, protein = _meal_totals(db, chat_id, start_utc, end_utc)
    return {
        "reminders": [
            _event_payload(event, settings)
            for event in (
                db.query(ReminderEvent)
                .filter(
                    ReminderEvent.chat_id == chat_id,
                    ReminderEvent.scheduled_at >= start_utc,
                    ReminderEvent.scheduled_at < end_utc,
                )
                .order_by(ReminderEvent.scheduled_at.asc())
                .all()
            )
        ],
        "calories": calories,
        "protein_grams": protein,
    }


def send_test_reminder(
    db: Session,
    settings: Settings,
    message_client: MessageClient,
    name: str = "test reminder",
) -> ReminderEvent:
    if not settings.telegram_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is required for dev test reminders")

    now = utc_now()
    local_now = _as_utc(now).astimezone(settings.timezone)
    reminder = Reminder(
        chat_id=settings.telegram_chat_id,
        category="general",
        name=name,
        dosage=None,
        instructions=name,
        frequency="once",
        times_json=json.dumps([local_now.strftime("%H:%M")]),
        start_date=local_now.date(),
        end_date=local_now.date(),
        status="active",
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)

    event = ReminderEvent(
        reminder_id=reminder.id,
        chat_id=settings.telegram_chat_id,
        scheduled_at=now,
        due_at=now,
        status="pending",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    send_due_reminders(db, settings, message_client, now=now)
    db.refresh(event)
    return event


def create_scheduler(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] = SessionLocal,
    message_client: MessageClient | None = None,
) -> BackgroundScheduler:
    settings = settings or get_settings()
    message_client = message_client or get_message_client()
    scheduler = BackgroundScheduler(timezone=settings.timezone)

    def with_db(fn):
        db = session_factory()
        try:
            return fn(db)
        finally:
            db.close()

    scheduler.add_job(
        lambda: with_db(lambda db: send_due_reminders(db, settings, message_client)),
        "interval",
        minutes=1,
        id="send-due-reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: with_db(lambda db: replenish_reminder_events(db, settings)),
        "cron",
        hour=0,
        minute=5,
        id="replenish-reminder-events",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: with_db(lambda db: send_daily_summaries(db, settings, message_client)),
        "cron",
        hour=settings.daily_summary_hour,
        minute=0,
        id="daily-summary",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: with_db(lambda db: send_sunday_goal_prompt(db, settings, message_client)),
        "cron",
        day_of_week="sun",
        hour=settings.sunday_goal_prompt_hour,
        minute=0,
        id="sunday-goal-prompt",
        replace_existing=True,
    )
    return scheduler


def _reminder_message(event: ReminderEvent) -> str:
    reminder = event.reminder
    dosage = f" {reminder.dosage}" if reminder.dosage else ""
    return (
        f"Reminder: {reminder.instructions}{dosage if reminder.dosage and reminder.dosage not in reminder.instructions else ''}.\n"
        "Reply DONE, SKIP, or SNOOZE 10."
    )


def _nudge_message(event: ReminderEvent) -> str:
    return f"Nudge {event.nudge_count + 1}: {_reminder_message(event)}"


def _local_day_bounds(settings: Settings, target_date: date | None = None) -> tuple[datetime, datetime]:
    local_date = target_date or datetime.now(settings.timezone).date()
    local_start = datetime.combine(local_date, time.min, tzinfo=settings.timezone)
    local_end = local_start + timedelta(days=1)
    return _to_utc_naive(local_start), _to_utc_naive(local_end)


def _all_times_have_passed_today(times: list[time], now_local: datetime) -> bool:
    if not times:
        return False
    return all(local_time <= now_local.time() for local_time in times)


def _events_for_statuses(
    db: Session,
    chat_id: str,
    start_utc: datetime,
    end_utc: datetime,
    statuses: list[str],
) -> list[ReminderEvent]:
    return (
        db.query(ReminderEvent)
        .filter(
            ReminderEvent.chat_id == chat_id,
            ReminderEvent.scheduled_at >= start_utc,
            ReminderEvent.scheduled_at < end_utc,
            ReminderEvent.status.in_(statuses),
        )
        .order_by(ReminderEvent.scheduled_at.asc())
        .all()
    )


def _event_names(events: list[ReminderEvent]) -> str:
    return ", ".join(event.reminder.name for event in events)


def _meal_totals(
    db: Session,
    chat_id: str,
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[int, int]:
    calories, protein = (
        db.query(
            func.coalesce(func.sum(MealLog.calories), 0),
            func.coalesce(func.sum(MealLog.protein_grams), 0),
        )
        .filter(
            MealLog.chat_id == chat_id,
            MealLog.logged_at >= start_utc,
            MealLog.logged_at < end_utc,
        )
        .one()
    )
    return int(calories), int(protein)


def _active_goal(db: Session, chat_id: str) -> DailyGoal | None:
    return (
        db.query(DailyGoal)
        .filter(DailyGoal.chat_id == chat_id, DailyGoal.active.is_(True))
        .order_by(DailyGoal.created_at.desc())
        .first()
    )


def _event_payload(event: ReminderEvent, settings: Settings) -> dict:
    return {
        "id": event.id,
        "reminder_id": event.reminder_id,
        "name": event.reminder.name,
        "status": event.status,
        "scheduled_at": _as_utc(event.scheduled_at).astimezone(settings.timezone).isoformat(),
        "due_at": _as_utc(event.due_at).astimezone(settings.timezone).isoformat(),
        "nudge_count": event.nudge_count,
    }


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
