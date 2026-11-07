from datetime import datetime
from typing import Any

from sqlalchemy import Column, Index, JSON, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from database import utc_now


class Community(SQLModel, table=True):
    __tablename__ = "communities"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)


class CommunityProfile(SQLModel, table=True):
    __tablename__ = "community_profiles"

    id: int | None = Field(default=None, primary_key=True)
    community_id: int = Field(foreign_key="communities.id", unique=True)
    kind: str = "NEIGHBORHOOD"
    city: str = ""
    district: str = ""
    address: str | None = None
    join_code: str = Field(unique=True, index=True)
    is_public: bool = False
    latitude: float | None = None
    longitude: float | None = None
    created_by_id: int | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utc_now)


class CommunityMember(SQLModel, table=True):
    __tablename__ = "community_members"
    __table_args__ = (UniqueConstraint("community_id", "user_id", name="uq_member_community_user"),)

    id: int | None = Field(default=None, primary_key=True)
    community_id: int = Field(foreign_key="communities.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    building_id: int | None = Field(default=None, foreign_key="buildings.id")
    role: str = "MEMBER"
    joined_at: datetime = Field(default_factory=utc_now)


class Building(SQLModel, table=True):
    __tablename__ = "buildings"

    id: int | None = Field(default=None, primary_key=True)
    community_id: int = Field(foreign_key="communities.id")
    name: str
    map_key: str = Field(unique=True)
    map_x: float | None = None
    map_y: float | None = None
    latitude: float | None = None
    longitude: float | None = None


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    display_name: str
    building_id: int | None = Field(default=None, foreign_key="buildings.id")
    avatar_color: str = "#dae9d5"
    email: str | None = Field(default=None, index=True, unique=True)
    password_hash: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    community_id: int | None = Field(default=None, foreign_key="communities.id")
    onboarding_completed: bool = False
    product_tour_completed: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UserPreference(SQLModel, table=True):
    __tablename__ = "user_preferences"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    goals: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    categories: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    trade_preferences: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    use_distance: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    jti: str = Field(unique=True, index=True)
    expires_at: datetime
    revoked_at: datetime | None = None


class Item(SQLModel, table=True):
    __tablename__ = "items"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="users.id", index=True)
    building_id: int = Field(foreign_key="buildings.id", index=True)
    title: str = Field(index=True)
    description: str
    category: str = Field(index=True)
    condition: str
    trade_type: str = Field(index=True)
    price: int | None = None
    original_price: int | None = None
    image_key: int = 0
    brand: str | None = None
    model_name: str | None = None
    public_location: str | None = None
    passport_id: int | None = Field(default=None, foreign_key="item_passports.id", index=True)
    batch_id: int | None = Field(default=None, foreign_key="batch_publishes.id", index=True)
    status: str = Field(default="AVAILABLE", index=True)
    disposal_goal: str = "BALANCED"
    last_confirmed_at: datetime | None = None
    handover_location: str | None = None
    created_at: datetime = Field(default_factory=utc_now, index=True)
    completed_at: datetime | None = None


class BatchPublish(SQLModel, table=True):
    __tablename__ = "batch_publishes"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    community_id: int = Field(foreign_key="communities.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    confirmed_at: datetime = Field(default_factory=utc_now)


class Need(SQLModel, table=True):
    __tablename__ = "needs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    community_id: int = Field(foreign_key="communities.id", index=True)
    building_id: int | None = Field(default=None, foreign_key="buildings.id", index=True)
    raw_text: str
    category: str | None = None
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    budget_min: int | None = None
    budget_max: int | None = None
    status: str = Field(default="ACTIVE", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class NeedMatch(SQLModel, table=True):
    __tablename__ = "need_matches"
    __table_args__ = (UniqueConstraint("need_id", "item_id", name="uq_need_match"),)

    id: int | None = Field(default=None, primary_key=True)
    need_id: int = Field(foreign_key="needs.id", index=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)


class NeedReply(SQLModel, table=True):
    __tablename__ = "need_replies"

    id: int | None = Field(default=None, primary_key=True)
    need_id: int = Field(foreign_key="needs.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    body: str
    item_id: int | None = Field(default=None, foreign_key="items.id")
    created_at: datetime = Field(default_factory=utc_now)


class ItemPassport(SQLModel, table=True):
    __tablename__ = "item_passports"

    id: int | None = Field(default=None, primary_key=True)
    root_item_id: int = Field(unique=True, index=True)
    passport_code: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)


class HandoverSlot(SQLModel, table=True):
    __tablename__ = "handover_slots"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    starts_at: datetime
    ends_at: datetime


class Reservation(SQLModel, table=True):
    __tablename__ = "reservations"
    __table_args__ = (
        Index("uq_reservation_confirmed_item", "item_id", unique=True,
              sqlite_where=text("status = 'CONFIRMED'"), postgresql_where=text("status = 'CONFIRMED'")),
        Index("uq_reservation_pending_buyer", "item_id", "buyer_id", unique=True,
              sqlite_where=text("status = 'PENDING'"), postgresql_where=text("status = 'PENDING'")),
    )

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    buyer_id: int = Field(foreign_key="users.id", index=True)
    seller_id: int = Field(foreign_key="users.id")
    slot_id: int = Field(foreign_key="handover_slots.id")
    status: str = Field(default="PENDING", index=True)
    pickup_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    handover_status: str = "WAITING"
    arrived_at: datetime | None = None
    delay_minutes: int = 0
    wait_until: datetime | None = None


class ItemEvent(SQLModel, table=True):
    __tablename__ = "item_events"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    user_id: int | None = Field(default=None, foreign_key="users.id")
    event_type: str = Field(index=True)
    metadata_json: dict[str, Any] | None = Field(default=None, sa_column=Column("metadata", JSON, nullable=True))
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Interest(SQLModel, table=True):
    __tablename__ = "interests"
    __table_args__ = (UniqueConstraint("item_id", "user_id", name="uq_interest_item_user"),)

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    user_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utc_now)


class ItemView(SQLModel, table=True):
    __tablename__ = "item_views"
    __table_args__ = (UniqueConstraint("item_id", "user_id", name="uq_view_item_user"),)

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    viewed_at: datetime = Field(default_factory=utc_now)


class Comment(SQLModel, table=True):
    __tablename__ = "comments"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    user_id: int = Field(foreign_key="users.id")
    body: str
    created_at: datetime = Field(default_factory=utc_now)


class PrivateMessage(SQLModel, table=True):
    __tablename__ = "private_messages"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    sender_id: int = Field(foreign_key="users.id", index=True)
    recipient_id: int = Field(foreign_key="users.id", index=True)
    body: str
    message_type: str = Field(default="TEXT")
    is_ai: bool = Field(default=False)
    read_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now, index=True)


class UserPresence(SQLModel, table=True):
    __tablename__ = "user_presence"

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    last_seen_at: datetime = Field(default_factory=utc_now)


class UploadedImage(SQLModel, table=True):
    __tablename__ = "uploaded_images"

    id: int = Field(primary_key=True)
    owner_id: int = Field(foreign_key="users.id", index=True)
    community_id: int = Field(foreign_key="communities.id", index=True)
    filename: str
    mime_type: str
    created_at: datetime = Field(default_factory=utc_now)


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", unique=True)
    recipient_id: int = Field(foreign_key="users.id")
    completed_at: datetime = Field(default_factory=utc_now)
