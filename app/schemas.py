from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ParsedReminder(BaseModel):
    category: Literal["medicine", "supplement", "diet", "general"]
    name: str
    dosage: str | None = None
    instructions: str
    frequency: str
    times: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date | None = None


class ParsedMealLog(BaseModel):
    calories: int
    protein_grams: int


class ParsedDailyGoal(BaseModel):
    calories: int
    protein_grams: int


class ParsedCommand(BaseModel):
    kind: Literal["reminder", "meal_log", "daily_goal", "unknown"]
    reminder: ParsedReminder | None = None
    meal_log: ParsedMealLog | None = None
    daily_goal: ParsedDailyGoal | None = None
    reason: str | None = None


def schema_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
