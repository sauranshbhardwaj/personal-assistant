from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base


class FakeSmsClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_sms(self, to: str, body: str) -> None:
        self.sent.append((to, body))


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        my_phone_number="+15555550100",
        database_url="sqlite://",
        nudge_interval_minutes=15,
        max_nudges=4,
        daily_summary_hour=20,
        sunday_goal_prompt_hour=18,
    )


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def fake_sms() -> FakeSmsClient:
    return FakeSmsClient()
