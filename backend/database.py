import os
from collections.abc import Generator
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine

load_dotenv()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    if not value:
        return None
    return as_utc(value).isoformat()


database_url = os.getenv("DATABASE_URL", "sqlite:///./neighloop.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def create_db() -> None:
    import models  # noqa: F401 - register SQLModel tables
    from migrations import migrate_auth_schema
    from migrate_features import backfill_passports, migrate_feature_columns

    migrate_auth_schema(engine)
    migrate_feature_columns(engine)
    SQLModel.metadata.create_all(engine)
    backfill_passports(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
