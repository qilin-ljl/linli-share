"""Small additive migration for the pre-auth NeighLoop database.

Run with ``python -c "from database import create_db; create_db()"``.
The application also runs it on startup. Existing demo users remain intact.
"""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine


AUTH_COLUMNS = {
    "email": "VARCHAR",
    "password_hash": "VARCHAR",
    "nickname": "VARCHAR",
    "avatar_url": "VARCHAR",
    "community_id": "INTEGER",
    "onboarding_completed": "BOOLEAN DEFAULT TRUE NOT NULL",
    "product_tour_completed": "BOOLEAN DEFAULT TRUE NOT NULL",
    "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL",
    "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL",
}


def migrate_auth_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "community_profiles" in inspector.get_table_names():
        profile_columns = {column["name"] for column in inspector.get_columns("community_profiles")}
        with engine.begin() as connection:
            if "is_public" not in profile_columns:
                default = "FALSE" if engine.dialect.name == "postgresql" else "0"
                enabled = "TRUE" if engine.dialect.name == "postgresql" else "1"
                connection.exec_driver_sql(f"ALTER TABLE community_profiles ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT {default}")
                connection.exec_driver_sql(f"UPDATE community_profiles SET is_public = {enabled} WHERE community_id = 1")
            if "latitude" not in profile_columns:
                connection.exec_driver_sql("ALTER TABLE community_profiles ADD COLUMN latitude FLOAT")
            if "longitude" not in profile_columns:
                connection.exec_driver_sql("ALTER TABLE community_profiles ADD COLUMN longitude FLOAT")
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns("users")}
    if engine.dialect.name == "sqlite" and (not AUTH_COLUMNS.keys() <= columns.keys() or columns["building_id"]["nullable"] is False):
        names = set(columns)
        copied = [
            "id", "display_name", "building_id", "avatar_color",
            *AUTH_COLUMNS.keys(),
        ]
        expressions = [
            column if column in names else
            "1" if column in {"onboarding_completed", "product_tour_completed"} else
            "CURRENT_TIMESTAMP" if column in {"created_at", "updated_at"} else "NULL"
            for column in copied
        ]
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.exec_driver_sql("""CREATE TABLE users_auth_new (
                id INTEGER PRIMARY KEY, display_name VARCHAR NOT NULL,
                building_id INTEGER REFERENCES buildings(id), avatar_color VARCHAR NOT NULL,
                email VARCHAR, password_hash VARCHAR, nickname VARCHAR, avatar_url VARCHAR,
                community_id INTEGER REFERENCES communities(id),
                onboarding_completed BOOLEAN NOT NULL DEFAULT 0,
                product_tour_completed BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
            )""")
            connection.exec_driver_sql(
                f"INSERT INTO users_auth_new ({', '.join(copied)}) "
                f"SELECT {', '.join(expressions)} FROM users"
            )
            connection.exec_driver_sql("DROP TABLE users")
            connection.exec_driver_sql("ALTER TABLE users_auth_new RENAME TO users")
            connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        return
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            for name, definition in AUTH_COLUMNS.items():
                connection.exec_driver_sql(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {name} {definition}")
            connection.exec_driver_sql("ALTER TABLE users ALTER COLUMN building_id DROP NOT NULL")
            connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
