from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.utcnow()


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=False)
    name = Column(String(255), nullable=False)
    dosage = Column(String(255), nullable=True)
    instructions = Column(Text, nullable=False)
    frequency = Column(String(128), nullable=False)
    times_json = Column(Text, nullable=False)
    start_date = Column(Date, nullable=False, default=date.today)
    end_date = Column(Date, nullable=True)
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    events = relationship("ReminderEvent", back_populates="reminder")


class ReminderEvent(Base):
    __tablename__ = "reminder_events"

    id = Column(Integer, primary_key=True)
    reminder_id = Column(Integer, ForeignKey("reminders.id"), nullable=False, index=True)
    chat_id = Column(String(64), nullable=False, index=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    due_at = Column(DateTime(timezone=True), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    nudge_count = Column(Integer, nullable=False, default=0)
    last_nudged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    reminder = relationship("Reminder", back_populates="events")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(64), nullable=False, index=True)
    direction = Column(String(16), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class MealLog(Base):
    __tablename__ = "meal_logs"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(64), nullable=False, index=True)
    meal_type = Column(String(32), nullable=True, index=True)
    calories = Column(Integer, nullable=False)
    protein_grams = Column(Integer, nullable=False)
    logged_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class DailyGoal(Base):
    __tablename__ = "daily_goals"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(64), nullable=False, index=True)
    calories = Column(Integer, nullable=False)
    protein_grams = Column(Integer, nullable=False)
    effective_date = Column(Date, nullable=False, default=date.today)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(64), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    parsed_payload = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
