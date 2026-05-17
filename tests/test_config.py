from __future__ import annotations

from app.config import Settings, normalize_database_url


def test_sqlite_database_url_is_unchanged() -> None:
    assert normalize_database_url("sqlite:///./health_reminders.db") == "sqlite:///./health_reminders.db"


def test_railway_postgres_url_is_normalized_for_sqlalchemy() -> None:
    assert (
        normalize_database_url("postgres://user:pass@example.railway.internal:5432/railway")
        == "postgresql://user:pass@example.railway.internal:5432/railway"
    )


def test_existing_postgresql_url_is_unchanged() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@example.railway.internal:5432/railway")
        == "postgresql://user:pass@example.railway.internal:5432/railway"
    )


def test_settings_normalizes_database_url() -> None:
    settings = Settings(database_url="postgres://user:pass@example.railway.internal:5432/railway")

    assert settings.database_url == "postgresql://user:pass@example.railway.internal:5432/railway"
