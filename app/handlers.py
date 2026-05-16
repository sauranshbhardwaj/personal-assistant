from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import DailyGoal, MealLog, PendingConfirmation, Reminder, ReminderEvent
from app.parser import parse_message
from app.scheduler import (
    create_reminder_events,
    render_summary,
    render_today_status,
)
from app.schemas import ParsedReminder, schema_to_dict
from app.twilio_client import SmsClient, record_inbound_message, send_sms_and_record

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
- Set weekly goal 2000 calories 170g protein"""

FALLBACK_TEXT = (
    "I could not understand that yet. Text HELP for commands, or try: "
    "Take Vitamin D 2000 IU every morning at 9 AM."
)


class SmsHandler:
    def __init__(self, db: Session, sms_client: SmsClient, settings: Settings):
        self.db = db
        self.sms_client = sms_client
        self.settings = settings

    def handle_inbound_sms(self, phone_number: str, body: str) -> str:
        body = body.strip()
        record_inbound_message(self.db, phone_number, body)

        if self.settings.my_phone_number and phone_number != self.settings.my_phone_number:
            return self._reply(
                phone_number,
                "This assistant is configured for one personal phone number.",
            )

        normalized = re.sub(r"\s+", " ", body).strip()
        command = normalized.lower()

        if command == "help":
            return self._reply(phone_number, HELP_TEXT)
        if command == "yes":
            return self._confirm_latest(phone_number)
        if command == "cancel":
            return self._cancel_latest(phone_number)
        if command == "done":
            return self._mark_latest_event(phone_number, "done")
        if command == "skip":
            return self._mark_latest_event(phone_number, "skipped")
        if command.startswith("snooze"):
            return self._snooze_latest(phone_number, command)
        if command == "today":
            return self._reply(phone_number, render_today_status(self.db, phone_number, self.settings))
        if command == "summary":
            return self._reply(phone_number, render_summary(self.db, phone_number, self.settings))

        parsed = parse_message(normalized, today=datetime.now(self.settings.timezone).date())
        if parsed.kind == "meal_log" and parsed.meal_log:
            return self._log_meal(phone_number, parsed.meal_log.calories, parsed.meal_log.protein_grams)
        if parsed.kind == "daily_goal" and parsed.daily_goal:
            return self._set_goal(phone_number, parsed.daily_goal.calories, parsed.daily_goal.protein_grams)
        if parsed.kind == "reminder" and parsed.reminder:
            return self._create_pending_confirmation(phone_number, normalized, parsed.reminder)

        return self._reply(phone_number, FALLBACK_TEXT)

    def _reply(self, phone_number: str, body: str) -> str:
        send_sms_and_record(self.db, self.sms_client, phone_number, body)
        return body

    def _create_pending_confirmation(
        self,
        phone_number: str,
        raw_text: str,
        reminder: ParsedReminder,
    ) -> str:
        payload = schema_to_dict(reminder)
        pending = PendingConfirmation(
            phone_number=phone_number,
            raw_text=raw_text,
            parsed_payload=json.dumps(payload, default=str),
            status="pending",
        )
        self.db.add(pending)
        self.db.commit()
        return self._reply(phone_number, _confirmation_text(reminder))

    def _confirm_latest(self, phone_number: str) -> str:
        pending = self._latest_pending_confirmation(phone_number)
        if pending is None:
            return self._reply(phone_number, "No pending reminder to confirm. Text HELP for commands.")

        reminder_payload = json.loads(pending.parsed_payload)
        parsed = ParsedReminder(**reminder_payload)
        reminder = Reminder(
            phone_number=phone_number,
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
            phone_number,
            f"Confirmed {reminder.name}. I created {event_count} reminder event(s).",
        )

    def _cancel_latest(self, phone_number: str) -> str:
        pending = self._latest_pending_confirmation(phone_number)
        if pending is None:
            return self._reply(phone_number, "No pending reminder to cancel. Text HELP for commands.")
        self.db.delete(pending)
        self.db.commit()
        return self._reply(phone_number, "Canceled the latest pending reminder.")

    def _mark_latest_event(self, phone_number: str, status: str) -> str:
        event = self._latest_actionable_event(phone_number)
        if event is None:
            return self._reply(phone_number, "No active reminder event found. Text today to see reminders.")
        event.status = status
        self.db.commit()
        verb = "Marked done" if status == "done" else "Skipped"
        return self._reply(phone_number, f"{verb}: {event.reminder.name}.")

    def _snooze_latest(self, phone_number: str, command: str) -> str:
        match = re.fullmatch(r"snooze\s+(10|30)", command)
        if not match:
            return self._reply(phone_number, "Use SNOOZE 10 or SNOOZE 30.")
        event = self._latest_actionable_event(phone_number)
        if event is None:
            return self._reply(phone_number, "No active reminder event found. Text today to see reminders.")
        minutes = int(match.group(1))
        event.status = "snoozed"
        event.due_at = datetime.utcnow() + timedelta(minutes=minutes)
        self.db.commit()
        return self._reply(phone_number, f"Snoozed {event.reminder.name} for {minutes} minutes.")

    def _log_meal(self, phone_number: str, calories: int, protein_grams: int) -> str:
        self.db.add(
            MealLog(
                phone_number=phone_number,
                calories=calories,
                protein_grams=protein_grams,
            )
        )
        self.db.commit()
        return self._reply(phone_number, f"Logged meal: {calories} calories, {protein_grams}g protein.")

    def _set_goal(self, phone_number: str, calories: int, protein_grams: int) -> str:
        self.db.query(DailyGoal).filter(
            DailyGoal.phone_number == phone_number,
            DailyGoal.active.is_(True),
        ).update({"active": False})
        self.db.add(
            DailyGoal(
                phone_number=phone_number,
                calories=calories,
                protein_grams=protein_grams,
                effective_date=datetime.now(self.settings.timezone).date(),
                active=True,
            )
        )
        self.db.commit()
        return self._reply(phone_number, f"Set goal: {calories} calories, {protein_grams}g protein.")

    def _latest_pending_confirmation(self, phone_number: str) -> PendingConfirmation | None:
        return (
            self.db.query(PendingConfirmation)
            .filter(
                PendingConfirmation.phone_number == phone_number,
                PendingConfirmation.status == "pending",
            )
            .order_by(PendingConfirmation.created_at.desc(), PendingConfirmation.id.desc())
            .first()
        )

    def _latest_actionable_event(self, phone_number: str) -> ReminderEvent | None:
        return (
            self.db.query(ReminderEvent)
            .filter(
                ReminderEvent.phone_number == phone_number,
                ReminderEvent.status.in_(["sent", "snoozed", "pending"]),
            )
            .order_by(
                desc(ReminderEvent.sent_at.isnot(None)),
                ReminderEvent.sent_at.desc(),
                ReminderEvent.due_at.desc(),
                ReminderEvent.id.desc(),
            )
            .first()
        )


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
