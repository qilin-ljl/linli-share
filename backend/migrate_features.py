"""Additive migration for location, needs, batch publishing and item passports."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, select


FEATURE_COLUMNS = {
    "community_profiles": {"address": "VARCHAR"},
    "buildings": {"map_x": "FLOAT", "map_y": "FLOAT", "latitude": "FLOAT", "longitude": "FLOAT"},
    "items": {"brand": "VARCHAR", "model_name": "VARCHAR", "public_location": "VARCHAR",
              "passport_id": "INTEGER", "batch_id": "INTEGER"},
    "batch_publishes": {"confirmed_at": "TIMESTAMP"},
    "private_messages": {"message_type": "VARCHAR DEFAULT 'TEXT'", "is_ai": "BOOLEAN DEFAULT 0", "read_at": "TIMESTAMP"},
}


def migrate_feature_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, additions in FEATURE_COLUMNS.items():
            if table not in tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            for column, definition in additions.items():
                if column not in present:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        if "items" in tables and "public_location" not in {c["name"] for c in inspector.get_columns("items")}:
            connection.exec_driver_sql("UPDATE items SET public_location = "
                                       "(SELECT name FROM buildings WHERE buildings.id = items.building_id) || '附近' "
                                       "WHERE public_location IS NULL")
        if "batch_publishes" in tables and "confirmed_at" not in {c["name"] for c in inspector.get_columns("batch_publishes")}:
            connection.exec_driver_sql("UPDATE batch_publishes SET confirmed_at = created_at WHERE confirmed_at IS NULL")


def backfill_passports(engine: Engine) -> None:
    from models import Item, ItemPassport

    with Session(engine) as session:
        items = session.exec(select(Item).where(Item.status == "COMPLETED", Item.passport_id == None)).all()  # noqa: E711
        for item in items:
            passport = session.exec(select(ItemPassport).where(ItemPassport.root_item_id == item.id)).first()
            if not passport:
                passport = ItemPassport(root_item_id=item.id, passport_code=f"NL-{item.id:05d}",
                                        created_at=item.created_at)
                session.add(passport)
                session.flush()
            item.passport_id = passport.id
            session.add(item)
        session.commit()
