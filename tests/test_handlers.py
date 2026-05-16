from __future__ import annotations

import json
from datetime import datetime

from app.handlers import HELP_TEXT, SmsHandler
from app.models import DailyGoal, MealLog, PendingConfirmation, Reminder, ReminderEvent


PHONE = "+15555550100"


def make_handler(db_session, fake_sms, settings) -> SmsHandler:
    return SmsHandler(db_session, fake_sms, settings)


def test_reminder_text_creates_pending_confirmation_with_fields(db_session, fake_sms, settings) -> None:
    handler = make_handler(db_session, fake_sms, settings)

    response = handler.handle_inbound_sms(
        PHONE,
        "Take Vitamin D 2000 IU every morning at 9 AM for 60 days",
    )

    assert "Please confirm reminder:" in response
    assert "Name: Vitamin D" in response
    assert "Dosage: 2000 IU" in response
    assert "Category: supplement" in response
    assert "Time(s): 09:00" in response
    assert "Frequency: every morning" in response
    assert "Reply YES to confirm or CANCEL to discard." in response
    assert db_session.query(PendingConfirmation).count() == 1
    assert fake_sms.sent[-1] == (PHONE, response)


def test_yes_confirms_latest_pending_and_creates_events(db_session, fake_sms, settings) -> None:
    handler = make_handler(db_session, fake_sms, settings)
    handler.handle_inbound_sms(PHONE, "Take antibiotic twice daily at 9 AM and 9 PM for 7 days")

    response = handler.handle_inbound_sms(PHONE, "YES")

    reminder = db_session.query(Reminder).one()
    assert reminder.name == "antibiotic"
    assert reminder.status == "active"
    assert db_session.query(PendingConfirmation).filter_by(status="pending").count() == 0
    assert db_session.query(ReminderEvent).count() == 14
    assert "Confirmed antibiotic" in response


def test_cancel_deletes_latest_pending_confirmation(db_session, fake_sms, settings) -> None:
    handler = make_handler(db_session, fake_sms, settings)
    handler.handle_inbound_sms(PHONE, "Take Vitamin D 2000 IU every morning at 9 AM")

    response = handler.handle_inbound_sms(PHONE, "CANCEL")

    assert response == "Canceled the latest pending reminder."
    assert db_session.query(PendingConfirmation).count() == 0


def test_done_marks_latest_actionable_event_done(db_session, fake_sms, settings) -> None:
    event = _create_event(db_session, status="sent")
    handler = make_handler(db_session, fake_sms, settings)

    response = handler.handle_inbound_sms(PHONE, "DONE")

    db_session.refresh(event)
    assert event.status == "done"
    assert response == "Marked done: magnesium."


def test_skip_marks_latest_actionable_event_skipped(db_session, fake_sms, settings) -> None:
    event = _create_event(db_session, status="sent")
    handler = make_handler(db_session, fake_sms, settings)

    response = handler.handle_inbound_sms(PHONE, "SKIP")

    db_session.refresh(event)
    assert event.status == "skipped"
    assert response == "Skipped: magnesium."


def test_snooze_delays_latest_actionable_event(db_session, fake_sms, settings) -> None:
    event = _create_event(db_session, status="sent")
    handler = make_handler(db_session, fake_sms, settings)

    response = handler.handle_inbound_sms(PHONE, "SNOOZE 10")

    db_session.refresh(event)
    assert event.status == "snoozed"
    assert event.due_at > datetime.utcnow()
    assert response == "Snoozed magnesium for 10 minutes."


def test_today_lists_pending_sent_and_snoozed(db_session, fake_sms, settings) -> None:
    _create_event(db_session, status="pending", name="Vitamin D")
    _create_event(db_session, status="sent", name="magnesium")
    _create_event(db_session, status="snoozed", name="antibiotic")
    handler = make_handler(db_session, fake_sms, settings)

    response = handler.handle_inbound_sms(PHONE, "today")

    assert "Pending: Vitamin D" in response
    assert "Sent: magnesium" in response
    assert "Snoozed: antibiotic" in response


def test_summary_includes_done_missed_and_meal_totals(db_session, fake_sms, settings) -> None:
    _create_event(db_session, status="done", name="Vitamin D")
    _create_event(db_session, status="missed", name="magnesium")
    db_session.add(MealLog(phone_number=PHONE, calories=650, protein_grams=45))
    db_session.commit()
    handler = make_handler(db_session, fake_sms, settings)

    response = handler.handle_inbound_sms(PHONE, "summary")

    assert "Done reminders: Vitamin D" in response
    assert "Missed reminders: magnesium" in response
    assert "Calories: 650" in response
    assert "Protein: 45g" in response


def test_help_command_lists_available_commands(db_session, fake_sms, settings) -> None:
    handler = make_handler(db_session, fake_sms, settings)

    response = handler.handle_inbound_sms(PHONE, "help")

    assert response == HELP_TEXT
    assert "SNOOZE 10" in response
    assert "SNOOZE 30" in response
    assert "Log meal 650 calories 45g protein" in response


def test_unknown_message_gets_helpful_fallback(db_session, fake_sms, settings) -> None:
    handler = make_handler(db_session, fake_sms, settings)

    response = handler.handle_inbound_sms(PHONE, "Should I change my medication?")

    assert "I could not understand that yet." in response
    assert "Text HELP" in response


def test_meal_and_goal_commands_store_records(db_session, fake_sms, settings) -> None:
    handler = make_handler(db_session, fake_sms, settings)

    meal_response = handler.handle_inbound_sms(PHONE, "Log meal 650 calories 45g protein")
    goal_response = handler.handle_inbound_sms(PHONE, "Set weekly goal 2000 calories 170g protein")

    assert meal_response == "Logged meal: 650 calories, 45g protein."
    assert goal_response == "Set goal: 2000 calories, 170g protein."
    assert db_session.query(MealLog).count() == 1
    assert db_session.query(DailyGoal).count() == 1


def _create_event(db_session, status: str, name: str = "magnesium") -> ReminderEvent:
    reminder = Reminder(
        phone_number=PHONE,
        category="supplement",
        name=name,
        dosage="400mg" if name == "magnesium" else None,
        instructions=f"Take {name}",
        frequency="daily",
        times_json=json.dumps(["09:00"]),
        start_date=datetime.utcnow().date(),
        status="active",
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)
    event = ReminderEvent(
        reminder_id=reminder.id,
        phone_number=PHONE,
        scheduled_at=datetime.utcnow(),
        due_at=datetime.utcnow(),
        sent_at=datetime.utcnow() if status == "sent" else None,
        status=status,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event
