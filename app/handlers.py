from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import DailyGoal, MealLog, PendingConfirmation, Reminder, ReminderEvent
from app.parser import parse_message
from app.scheduler import (
    create_reminder_events,
    local_day_bounds,
    render_summary,
    render_today_status,
)
from app.reminder_catalog import OMEGA3_NAME, OMEGA3_REMINDER_MESSAGE
from app.schemas import ParsedReminder, schema_to_dict
from app.telegram_client import MessageClient, record_inbound_message, send_message_and_record

HELP_TEXT = """Commands:
- create reminder by plain text
- YES
- CANCEL
- DONE
- SKIP
- SNOOZE 10
- SNOOZE 30
- today
- summary
- Log meal 650 calories 45g protein
- Log breakfast/lunch/snack/dinner 650 calories 45g protein
- Set weekly goal 2000 calories 170g protein"""

FALLBACK_TEXT = (
    "I could not understand that yet. Text HELP for commands, or try: "
    "Take Vitamin D 2000 IU every morning at 9 AM."
)


class MessageHandler:
    def __init__(self, db: Session, message_client: MessageClient, settings: Settings):
        self.db = db
        self.message_client = message_client
        self.settings = settings

    def handle_inbound_message(self, chat_id: str, body: str) -> str:
        body = body.strip()
        record_inbound_message(self.db, chat_id, body)

        if self.settings.telegram_chat_id and chat_id != self.settings.telegram_chat_id:
            return "Ignored message from unauthorized Telegram chat."

        normalized = re.sub(r"\s+", " ", body).strip()
        command = normalized.lower()

        if command == "help":
            return self._reply(chat_id, HELP_TEXT)
        if command == "yes":
            return self._confirm_latest(chat_id)
        if command == "cancel":
            return self._cancel_latest(chat_id)
        if command == "done":
            return self._mark_latest_event(chat_id, "done")
        if command == "skip":
            return self._mark_latest_event(chat_id, "skipped")
        if command.startswith("snooze"):
            return self._snooze_latest(chat_id, command)
        if command == "today":
            return self._reply(chat_id, render_today_status(self.db, chat_id, self.settings))
        if command == "summary":
            return self._reply(chat_id, render_summary(self.db, chat_id, self.settings))

        parsed = parse_message(normalized, today=datetime.now(self.settings.timezone).date())
        if parsed.kind == "meal_log" and parsed.meal_log:
            return self._log_meal(
                chat_id,
                parsed.meal_log.calories,
                parsed.meal_log.protein_grams,
                parsed.meal_log.meal_type,
            )
        if parsed.kind == "daily_goal" and parsed.daily_goal:
            return self._set_goal(chat_id, parsed.daily_goal.calories, parsed.daily_goal.protein_grams)
        if parsed.kind == "reminder" and parsed.reminder:
            return self._create_pending_confirmation(chat_id, normalized, parsed.reminder)

        return self._reply(chat_id, FALLBACK_TEXT)

    def _reply(self, chat_id: str, body: str) -> str:
        send_message_and_record(self.db, self.message_client, chat_id, body)
        return body

    def _create_pending_confirmation(
        self,
        chat_id: str,
        raw_text: str,
        reminder: ParsedReminder,
    ) -> str:
        payload = schema_to_dict(reminder)
        pending = PendingConfirmation(
            chat_id=chat_id,
            raw_text=raw_text,
            parsed_payload=json.dumps(payload, default=str),
            status="pending",
        )
        self.db.add(pending)
        self.db.commit()
        return self._reply(chat_id, _confirmation_text(reminder))

    def _confirm_latest(self, chat_id: str) -> str:
        pending = self._latest_pending_confirmation(chat_id)
        if pending is None:
            return self._reply(chat_id, "No pending reminder to confirm. Text HELP for commands.")

        reminder_payload = json.loads(pending.parsed_payload)
        parsed = ParsedReminder(**reminder_payload)
        reminder = Reminder(
            chat_id=chat_id,
            category=parsed.category,
            name=parsed.name,
            dosage=parsed.dosage,
            instructions=parsed.instructions,
            frequency=parsed.frequency,
            times_json=json.dumps(parsed.times),
            start_date=parsed.start_date,
            end_date=parsed.end_date,
            status="active",
        )
        self.db.add(reminder)
        pending.status = "confirmed"
        self.db.commit()
        self.db.refresh(reminder)
        event_count = create_reminder_events(self.db, reminder, self.settings)
        return self._reply(
            chat_id,
            f"Confirmed {reminder.name}. I created {event_count} reminder event(s).",
        )

    def _cancel_latest(self, chat_id: str) -> str:
        pending = self._latest_pending_confirmation(chat_id)
        if pending is None:
            return self._reply(chat_id, "No pending reminder to cancel. Text HELP for commands.")
        self.db.delete(pending)
        self.db.commit()
        return self._reply(chat_id, "Canceled the latest pending reminder.")

    def _mark_latest_event(self, chat_id: str, status: str) -> str:
        event = self._latest_actionable_event(chat_id)
        if event is None:
            return self._reply(chat_id, "No active reminder event found. Text today to see reminders.")
        event.status = status
        self.db.commit()
        verb = "Marked done" if status == "done" else "Skipped"
        return self._reply(chat_id, f"{verb}: {event.reminder.name}.")

    def _snooze_latest(self, chat_id: str, command: str) -> str:
        match = re.fullmatch(r"snooze\s+(10|30)", command)
        if not match:
            return self._reply(chat_id, "Use SNOOZE 10 or SNOOZE 30.")
        event = self._latest_actionable_event(chat_id)
        if event is None:
            return self._reply(chat_id, "No active reminder event found. Text today to see reminders.")
        minutes = int(match.group(1))
        event.status = "snoozed"
        event.due_at = datetime.utcnow() + timedelta(minutes=minutes)
        self.db.commit()
        return self._reply(chat_id, f"Snoozed {event.reminder.name} for {minutes} minutes.")

    def _log_meal(
        self,
        chat_id: str,
        calories: int,
        protein_grams: int,
        meal_type: str,
    ) -> str:
        self.db.add(
            MealLog(
                chat_id=chat_id,
                meal_type=meal_type,
                calories=calories,
                protein_grams=protein_grams,
            )
        )
        self.db.commit()
        meal_label = meal_type if meal_type != "meal" else "meal"
        ack = self._reply(
            chat_id,
            f"Logged {meal_label}: {calories} calories, {protein_grams}g protein.",
        )
        omega3_message = self._trigger_omega3_for_lunch(chat_id, meal_type)
        return omega3_message or ack

    def _set_goal(self, chat_id: str, calories: int, protein_grams: int) -> str:
        self.db.query(DailyGoal).filter(
            DailyGoal.chat_id == chat_id,
            DailyGoal.active.is_(True),
        ).update({"active": False})
        self.db.add(
            DailyGoal(
                chat_id=chat_id,
                calories=calories,
                protein_grams=protein_grams,
                effective_date=datetime.now(self.settings.timezone).date(),
                active=True,
            )
        )
        self.db.commit()
        return self._reply(chat_id, f"Set goal: {calories} calories, {protein_grams}g protein.")

    def _latest_pending_confirmation(self, chat_id: str) -> PendingConfirmation | None:
        return (
            self.db.query(PendingConfirmation)
            .filter(
                PendingConfirmation.chat_id == chat_id,
                PendingConfirmation.status == "pending",
            )
            .order_by(PendingConfirmation.created_at.desc(), PendingConfirmation.id.desc())
            .first()
        )

    def _latest_actionable_event(self, chat_id: str) -> ReminderEvent | None:
        now = datetime.utcnow()
        return (
            self.db.query(ReminderEvent)
            .filter(
                ReminderEvent.chat_id == chat_id,
                or_(
                    ReminderEvent.status.in_(["sent", "snoozed"]),
                    and_(
                        ReminderEvent.status == "pending",
                        ReminderEvent.due_at <= now,
                    ),
                ),
            )
            .order_by(
                desc(ReminderEvent.sent_at.isnot(None)),
                ReminderEvent.sent_at.desc(),
                ReminderEvent.due_at.desc(),
                ReminderEvent.id.desc(),
            )
            .first()
        )

    def _trigger_omega3_for_lunch(self, chat_id: str, meal_type: str) -> str | None:
        if meal_type != "lunch":
            return None

        now_utc = datetime.utcnow()
        local_today = datetime.now(self.settings.timezone).date()
        reminder = (
            self.db.query(Reminder)
            .filter(
                Reminder.chat_id == chat_id,
                Reminder.name == OMEGA3_NAME,
                Reminder.status == "active",
                Reminder.start_date <= local_today,
                or_(Reminder.end_date.is_(None), Reminder.end_date >= local_today),
            )
            .order_by(Reminder.created_at.desc(), Reminder.id.desc())
            .first()
        )
        if reminder is None:
            return None

        start_utc, end_utc = local_day_bounds(self.settings, local_today)
        already_triggered = (
            self.db.query(ReminderEvent)
            .filter(
                ReminderEvent.reminder_id == reminder.id,
                ReminderEvent.scheduled_at >= start_utc,
                ReminderEvent.scheduled_at < end_utc,
            )
            .first()
        )
        if already_triggered is not None:
            return None

        self.db.add(
            ReminderEvent(
                reminder_id=reminder.id,
                chat_id=chat_id,
                scheduled_at=now_utc,
                due_at=now_utc,
                sent_at=now_utc,
                status="sent",
                nudge_count=0,
                last_nudged_at=now_utc,
            )
        )
        self.db.commit()
        return self._reply(chat_id, OMEGA3_REMINDER_MESSAGE)


def _confirmation_text(reminder: ParsedReminder) -> str:
    end_date = reminder.end_date.isoformat() if reminder.end_date else "none"
    return "\n".join(
        [
            "Please confirm reminder:",
            f"Name: {reminder.name}",
            f"Dosage: {reminder.dosage or 'none'}",
            f"Category: {reminder.category}",
            f"Time(s): {', '.join(reminder.times)}",
            f"Frequency: {reminder.frequency}",
            f"Start date: {reminder.start_date.isoformat()}",
            f"End date: {end_date}",
            "Reply YES to confirm or CANCEL to discard.",
        ]
    )
