from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.handlers import HELP_TEXT, MessageHandler
from app.models import DailyGoal, MealLog, PendingConfirmation, Reminder, ReminderEvent
from app.reminder_catalog import OMEGA3_NAME, OMEGA3_REMINDER_MESSAGE


CHAT_ID = "123456789"


def make_handler(db_session, fake_telegram, settings) -> MessageHandler:
    return MessageHandler(db_session, fake_telegram, settings)


def test_reminder_text_creates_pending_confirmation_with_fields(db_session, fake_telegram, settings) -> None:
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(
        CHAT_ID,
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
    assert fake_telegram.sent[-1] == (CHAT_ID, response)


def test_yes_confirms_latest_pending_and_creates_events(db_session, fake_telegram, settings) -> None:
    handler = make_handler(db_session, fake_telegram, settings)
    handler.handle_inbound_message(CHAT_ID, "Take antibiotic twice daily at 9 AM and 9 PM for 7 days")

    response = handler.handle_inbound_message(CHAT_ID, "YES")

    reminder = db_session.query(Reminder).one()
    assert reminder.name == "antibiotic"
    assert reminder.status == "active"
    assert db_session.query(PendingConfirmation).filter_by(status="pending").count() == 0
    events = db_session.query(ReminderEvent).all()
    assert events
    assert all(event.scheduled_at > datetime.utcnow() for event in events)
    assert "Confirmed antibiotic" in response


def test_cancel_deletes_latest_pending_confirmation(db_session, fake_telegram, settings) -> None:
    handler = make_handler(db_session, fake_telegram, settings)
    handler.handle_inbound_message(CHAT_ID, "Take Vitamin D 2000 IU every morning at 9 AM")

    response = handler.handle_inbound_message(CHAT_ID, "CANCEL")

    assert response == "Canceled the latest pending reminder."
    assert db_session.query(PendingConfirmation).count() == 0


def test_done_marks_latest_actionable_event_done(db_session, fake_telegram, settings) -> None:
    event = _create_event(db_session, status="sent")
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "DONE")

    db_session.refresh(event)
    assert event.status == "done"
    assert response == "Marked done: magnesium."


def test_skip_marks_latest_actionable_event_skipped(db_session, fake_telegram, settings) -> None:
    event = _create_event(db_session, status="sent")
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "SKIP")

    db_session.refresh(event)
    assert event.status == "skipped"
    assert response == "Skipped: magnesium."


def test_snooze_delays_latest_actionable_event(db_session, fake_telegram, settings) -> None:
    event = _create_event(db_session, status="sent")
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "SNOOZE 10")

    db_session.refresh(event)
    assert event.status == "snoozed"
    assert event.due_at > datetime.utcnow()
    assert response == "Snoozed magnesium for 10 minutes."


def test_done_does_not_complete_future_pending_event(db_session, fake_telegram, settings) -> None:
    event = _create_event(
        db_session,
        status="pending",
        scheduled_at=datetime.utcnow() + timedelta(hours=2),
        due_at=datetime.utcnow() + timedelta(hours=2),
    )
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "DONE")

    db_session.refresh(event)
    assert event.status == "pending"
    assert response == "No active reminder event found. Text today to see reminders."


def test_skip_can_handle_due_pending_event(db_session, fake_telegram, settings) -> None:
    event = _create_event(
        db_session,
        status="pending",
        scheduled_at=datetime.utcnow() - timedelta(minutes=1),
        due_at=datetime.utcnow() - timedelta(minutes=1),
    )
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "SKIP")

    db_session.refresh(event)
    assert event.status == "skipped"
    assert response == "Skipped: magnesium."


def test_today_lists_pending_sent_and_snoozed(db_session, fake_telegram, settings) -> None:
    _create_event(db_session, status="pending", name="Vitamin D")
    _create_event(db_session, status="sent", name="magnesium")
    _create_event(db_session, status="snoozed", name="antibiotic")
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "today")

    assert "Pending: Vitamin D" in response
    assert "Sent: magnesium" in response
    assert "Snoozed: antibiotic" in response


def test_summary_includes_done_missed_and_meal_totals(db_session, fake_telegram, settings) -> None:
    _create_event(db_session, status="done", name="Vitamin D")
    _create_event(db_session, status="missed", name="magnesium")
    db_session.add(MealLog(chat_id=CHAT_ID, calories=650, protein_grams=45))
    db_session.commit()
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "summary")

    assert "Done reminders: Vitamin D" in response
    assert "Missed reminders: magnesium" in response
    assert "Calories: 650" in response
    assert "Protein: 45g" in response


def test_help_command_lists_available_commands(db_session, fake_telegram, settings) -> None:
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "help")

    assert response == HELP_TEXT
    assert "SNOOZE 10" in response
    assert "SNOOZE 30" in response
    assert "Log meal 650 calories 45g protein" in response
    assert "Log breakfast/lunch/snack/dinner 650 calories 45g protein" in response


def test_unknown_message_gets_helpful_fallback(db_session, fake_telegram, settings) -> None:
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "Should I change my medication?")

    assert "I could not understand that yet." in response
    assert "Text HELP" in response


def test_meal_and_goal_commands_store_records(db_session, fake_telegram, settings) -> None:
    handler = make_handler(db_session, fake_telegram, settings)

    meal_response = handler.handle_inbound_message(CHAT_ID, "Log meal 650 calories 45g protein")
    goal_response = handler.handle_inbound_message(CHAT_ID, "Set weekly goal 2000 calories 170g protein")

    assert meal_response == "Logged meal: 650 calories, 45g protein."
    assert goal_response == "Set goal: 2000 calories, 170g protein."
    assert db_session.query(MealLog).count() == 1
    assert db_session.query(DailyGoal).count() == 1


def test_lunch_logging_triggers_omega3(db_session, fake_telegram, settings) -> None:
    _create_omega3_reminder(db_session)
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "Log lunch 650 calories 45g protein")

    event = db_session.query(ReminderEvent).one()
    meal = db_session.query(MealLog).one()
    assert meal.meal_type == "lunch"
    assert event.status == "sent"
    assert event.sent_at is not None
    assert response == OMEGA3_REMINDER_MESSAGE
    assert fake_telegram.sent[-2] == (CHAT_ID, "Logged lunch: 650 calories, 45g protein.")
    assert fake_telegram.sent[-1] == (CHAT_ID, OMEGA3_REMINDER_MESSAGE)


def test_non_lunch_meal_logs_do_not_trigger_omega3(db_session, fake_telegram, settings) -> None:
    _create_omega3_reminder(db_session)
    handler = make_handler(db_session, fake_telegram, settings)

    response = handler.handle_inbound_message(CHAT_ID, "Log breakfast 500 calories 35g protein")

    assert response == "Logged breakfast: 500 calories, 35g protein."
    assert db_session.query(MealLog).count() == 1
    assert db_session.query(ReminderEvent).count() == 0
    assert fake_telegram.sent[-1] == (CHAT_ID, "Logged breakfast: 500 calories, 35g protein.")


def test_duplicate_lunch_logs_do_not_create_duplicate_omega3_events(
    db_session,
    fake_telegram,
    settings,
) -> None:
    _create_omega3_reminder(db_session)
    handler = make_handler(db_session, fake_telegram, settings)

    first_response = handler.handle_inbound_message(CHAT_ID, "Lunch: 650 calories, 45g protein")
    second_response = handler.handle_inbound_message(CHAT_ID, "Log lunch 300 calories 25g protein")

    assert first_response == OMEGA3_REMINDER_MESSAGE
    assert second_response == "Logged lunch: 300 calories, 25g protein."
    assert db_session.query(MealLog).count() == 2
    assert db_session.query(ReminderEvent).count() == 1
    assert [body for _, body in fake_telegram.sent].count(OMEGA3_REMINDER_MESSAGE) == 1


def _create_event(
    db_session,
    status: str,
    name: str = "magnesium",
    scheduled_at: datetime | None = None,
    due_at: datetime | None = None,
) -> ReminderEvent:
    reminder = Reminder(
        chat_id=CHAT_ID,
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
        chat_id=CHAT_ID,
        scheduled_at=scheduled_at or datetime.utcnow(),
        due_at=due_at or datetime.utcnow(),
        sent_at=datetime.utcnow() if status == "sent" else None,
        status=status,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def _create_omega3_reminder(db_session) -> Reminder:
    reminder = Reminder(
        chat_id=CHAT_ID,
        category="supplement",
        name=OMEGA3_NAME,
        dosage="1 tablet",
        instructions="Take Omega 3 Tablet 1 tablet",
        frequency="after lunch log",
        times_json=json.dumps([]),
        start_date=datetime.utcnow().date(),
        status="active",
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)
    return reminder
