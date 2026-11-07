"""Idempotent local schema upgrade for the exam prototype.

Fresh databases are created directly from SQLModel. Existing SQLite/PostgreSQL
databases can run this before starting the upgraded API.
"""

from datetime import timedelta

from sqlalchemy import inspect, text
from sqlmodel import Session, select

from database import create_db, engine, utc_now
from models import HandoverSlot, Item


def migrate() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("items")}
    timestamp_type = "TIMESTAMPTZ" if engine.dialect.name == "postgresql" else "DATETIME"
    additions = {
        "disposal_goal": "VARCHAR DEFAULT 'BALANCED'",
        "last_confirmed_at": timestamp_type,
        "handover_location": "VARCHAR",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE items ADD COLUMN {name} {sql_type}"))
        connection.execute(text("UPDATE items SET status = 'AVAILABLE' WHERE status = 'ACTIVE'"))
        connection.execute(text("UPDATE items SET disposal_goal = 'BALANCED' WHERE disposal_goal IS NULL"))
        connection.execute(text("UPDATE items SET last_confirmed_at = created_at WHERE last_confirmed_at IS NULL"))
        connection.execute(text("UPDATE items SET handover_location = "
                                "(SELECT name FROM buildings WHERE buildings.id = items.building_id) || '大厅' "
                                "WHERE handover_location IS NULL"))
    create_db()

    reservation_columns = {column["name"] for column in inspect(engine).get_columns("reservations")}
    reservation_additions = {
        "handover_status": "VARCHAR DEFAULT 'WAITING'",
        "arrived_at": timestamp_type,
        "delay_minutes": "INTEGER DEFAULT 0",
        "wait_until": timestamp_type,
    }
    with engine.begin() as connection:
        for name, sql_type in reservation_additions.items():
            if name not in reservation_columns:
                connection.execute(text(f"ALTER TABLE reservations ADD COLUMN {name} {sql_type}"))
        connection.execute(text("UPDATE reservations SET handover_status = 'WAITING' WHERE handover_status IS NULL"))
        connection.execute(text("UPDATE reservations SET delay_minutes = 0 WHERE delay_minutes IS NULL"))

    now = utc_now()
    added = 0
    with Session(engine) as session:
        active = session.exec(select(Item).where(Item.status == "AVAILABLE")).all()
        for item in active:
            if session.exec(select(HandoverSlot.id).where(HandoverSlot.item_id == item.id)).first():
                continue
            for hours in (2, 4, 26):
                start = now + timedelta(hours=hours)
                session.add(HandoverSlot(item_id=item.id, starts_at=start, ends_at=start + timedelta(minutes=30)))
                added += 1
        session.commit()
    print(f"Schema ready; added {added} future handover slots for existing items.")


if __name__ == "__main__":
    migrate()
