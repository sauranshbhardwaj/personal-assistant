from __future__ import annotations

import re
from datetime import date, timedelta

from app.schemas import ParsedCommand, ParsedDailyGoal, ParsedMealLog, ParsedReminder


TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
DOSAGE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:mg|g|mcg|iu|units?|ml|pills?|tablets?|capsules?))\b",
    re.IGNORECASE,
)
MEAL_RE = re.compile(
    r"^log meal\s+(\d+)\s*(?:cal|calories)\s+(\d+)\s*g\s*protein$",
    re.IGNORECASE,
)
GOAL_RE = re.compile(
    r"^set weekly goal\s+(\d+)\s*(?:cal|calories)\s+(\d+)\s*g\s*protein$",
    re.IGNORECASE,
)
DURATION_RE = re.compile(r"\bfor\s+(\d+)\s+days?\b", re.IGNORECASE)

SUPPLEMENT_KEYWORDS = {
    "vitamin",
    "magnesium",
    "supplement",
    "probiotic",
    "fish oil",
    "calcium",
    "zinc",
}
MEDICINE_KEYWORDS = {
    "antibiotic",
    "medicine",
    "medication",
    "pill",
    "tablet",
    "capsule",
}


def parse_message(text: str, today: date | None = None) -> ParsedCommand:
    today = today or date.today()
    cleaned = _collapse_spaces(text)
    if not cleaned:
        return ParsedCommand(kind="unknown", reason="empty message")

    meal_match = MEAL_RE.match(cleaned)
    if meal_match:
        return ParsedCommand(
            kind="meal_log",
            meal_log=ParsedMealLog(
                calories=int(meal_match.group(1)),
                protein_grams=int(meal_match.group(2)),
            ),
        )

    goal_match = GOAL_RE.match(cleaned)
    if goal_match:
        return ParsedCommand(
            kind="daily_goal",
            daily_goal=ParsedDailyGoal(
                calories=int(goal_match.group(1)),
                protein_grams=int(goal_match.group(2)),
            ),
        )

    reminder = _parse_reminder(cleaned, today)
    if reminder is None:
        return ParsedCommand(
            kind="unknown",
            reason="unsupported or ambiguous message",
        )

    return ParsedCommand(kind="reminder", reminder=reminder)


def _parse_reminder(text: str, today: date) -> ParsedReminder | None:
    lower = text.lower()
    if lower.startswith("remind me to take "):
        body = text[len("remind me to take ") :]
        take_style = True
    elif lower.startswith("take "):
        body = text[len("take ") :]
        take_style = True
    elif lower.startswith("remind me to "):
        body = text[len("remind me to ") :]
        take_style = False
    else:
        return None

    times = [_normalize_time(match) for match in TIME_RE.finditer(text)]
    if not times:
        return None

    frequency = _parse_frequency(lower, len(times))
    end_date = _parse_end_date(lower, today)
    core = _extract_core_name(body)
    if not core:
        return None

    dosage_match = DOSAGE_RE.search(core)
    dosage = _normalize_dosage(dosage_match.group(1)) if dosage_match else None
    name = _collapse_spaces(DOSAGE_RE.sub("", core)).strip(" ,.-")
    if not name:
        return None

    category = _category_for(lower, name.lower(), take_style)
    instructions = _build_instructions(take_style, name, dosage)

    return ParsedReminder(
        category=category,
        name=name,
        dosage=dosage,
        instructions=instructions,
        frequency=frequency,
        times=times,
        start_date=today,
        end_date=end_date,
    )


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _normalize_time(match: re.Match[str]) -> str:
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3).lower()
    if hour == 12:
        hour = 0
    if meridiem == "pm":
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def _normalize_dosage(value: str) -> str:
    collapsed = _collapse_spaces(value)
    return re.sub(r"\s+(mg|g|mcg|iu|ml)$", lambda m: f" {m.group(1).upper()}", collapsed, flags=re.IGNORECASE)


def _parse_frequency(lower_text: str, time_count: int) -> str:
    if "twice daily" in lower_text:
        return "twice daily"
    if "every morning" in lower_text:
        return "every morning"
    if "every night" in lower_text:
        return "every night"
    if "every evening" in lower_text:
        return "every evening"
    if "daily" in lower_text:
        return "daily"
    if time_count > 1:
        return "daily"
    return "daily"


def _parse_end_date(lower_text: str, today: date) -> date | None:
    duration_match = DURATION_RE.search(lower_text)
    if not duration_match:
        return None
    days = int(duration_match.group(1))
    return today + timedelta(days=max(days, 1) - 1)


def _extract_core_name(body: str) -> str:
    core = DURATION_RE.sub("", body)
    core = re.split(
        r"\b(?:every morning|every night|every evening|twice daily|daily)\b",
        core,
        flags=re.IGNORECASE,
        maxsplit=1,
    )[0]
    core = re.split(r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", core, flags=re.IGNORECASE)[0]
    return _collapse_spaces(core).strip(" ,.-")


def _category_for(full_lower: str, name_lower: str, take_style: bool) -> str:
    joined = f"{full_lower} {name_lower}"
    if any(keyword in joined for keyword in SUPPLEMENT_KEYWORDS):
        return "supplement"
    if any(keyword in joined for keyword in MEDICINE_KEYWORDS):
        return "medicine"
    if any(keyword in joined for keyword in {"meal", "calories", "protein"}):
        return "diet"
    if take_style:
        return "medicine"
    return "general"


def _build_instructions(take_style: bool, name: str, dosage: str | None) -> str:
    if take_style:
        return f"Take {name}{f' {dosage}' if dosage else ''}"
    return name
