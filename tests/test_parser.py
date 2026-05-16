from __future__ import annotations

from datetime import date

from app.parser import parse_message


TODAY = date(2026, 5, 16)


def test_parse_vitamin_d_reminder() -> None:
    parsed = parse_message("Take Vitamin D 2000 IU every morning at 9 AM for 60 days", today=TODAY)

    assert parsed.kind == "reminder"
    assert parsed.reminder is not None
    assert parsed.reminder.category == "supplement"
    assert parsed.reminder.name == "Vitamin D"
    assert parsed.reminder.dosage == "2000 IU"
    assert parsed.reminder.frequency == "every morning"
    assert parsed.reminder.times == ["09:00"]
    assert parsed.reminder.start_date == TODAY
    assert parsed.reminder.end_date == date(2026, 7, 14)


def test_parse_magnesium_reminder() -> None:
    parsed = parse_message("Remind me to take magnesium 400mg every night at 10 PM", today=TODAY)

    assert parsed.kind == "reminder"
    assert parsed.reminder is not None
    assert parsed.reminder.category == "supplement"
    assert parsed.reminder.name == "magnesium"
    assert parsed.reminder.dosage == "400mg"
    assert parsed.reminder.frequency == "every night"
    assert parsed.reminder.times == ["22:00"]
    assert parsed.reminder.end_date is None


def test_parse_antibiotic_twice_daily() -> None:
    parsed = parse_message("Take antibiotic twice daily at 9 AM and 9 PM for 7 days", today=TODAY)

    assert parsed.kind == "reminder"
    assert parsed.reminder is not None
    assert parsed.reminder.category == "medicine"
    assert parsed.reminder.name == "antibiotic"
    assert parsed.reminder.dosage is None
    assert parsed.reminder.frequency == "twice daily"
    assert parsed.reminder.times == ["09:00", "21:00"]
    assert parsed.reminder.end_date == date(2026, 5, 22)


def test_parse_meal_log() -> None:
    parsed = parse_message("Log meal 650 calories 45g protein", today=TODAY)

    assert parsed.kind == "meal_log"
    assert parsed.meal_log is not None
    assert parsed.meal_log.meal_type == "meal"
    assert parsed.meal_log.calories == 650
    assert parsed.meal_log.protein_grams == 45


def test_parse_typed_meal_logs() -> None:
    lunch = parse_message("Log lunch 650 calories 45g protein", today=TODAY)
    breakfast = parse_message("Log breakfast 500 calories 35g protein", today=TODAY)
    snack = parse_message("Log snack 250 calories 20g protein", today=TODAY)
    dinner = parse_message("Log dinner 700 calories 50g protein", today=TODAY)
    colon_lunch = parse_message("Lunch: 650 calories, 45g protein", today=TODAY)

    assert lunch.kind == "meal_log"
    assert lunch.meal_log is not None
    assert lunch.meal_log.meal_type == "lunch"
    assert breakfast.meal_log is not None
    assert breakfast.meal_log.meal_type == "breakfast"
    assert snack.meal_log is not None
    assert snack.meal_log.meal_type == "snack"
    assert dinner.meal_log is not None
    assert dinner.meal_log.meal_type == "dinner"
    assert colon_lunch.meal_log is not None
    assert colon_lunch.meal_log.meal_type == "lunch"


def test_parse_weekly_goal() -> None:
    parsed = parse_message("Set weekly goal 2000 calories 170g protein", today=TODAY)

    assert parsed.kind == "daily_goal"
    assert parsed.daily_goal is not None
    assert parsed.daily_goal.calories == 2000
    assert parsed.daily_goal.protein_grams == 170


def test_ambiguous_reminder_without_time_is_unknown() -> None:
    parsed = parse_message("Take Vitamin D every morning", today=TODAY)

    assert parsed.kind == "unknown"


def test_unsupported_text_is_unknown() -> None:
    parsed = parse_message("What should I take for a headache?", today=TODAY)

    assert parsed.kind == "unknown"
