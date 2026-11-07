from datetime import timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database import as_utc, utc_now
from models import Building, Community, HandoverSlot, Item, User
from seed import ITEMS, ensure_future_demo_slots


def test_refresh_demo_slots_is_idempotent_and_skips_user_listings(monkeypatch):
    monkeypatch.setenv("NEIGHLOOP_DEMO_MODE", "true")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    now = utc_now()
    with Session(engine) as session:
        community = Community(name="绿荫花园小区")
        session.add(community)
        session.flush()
        building = Building(community_id=community.id, name="1号楼", map_key="building1")
        session.add(building)
        session.flush()
        owner = User(display_name="演示发布者", building_id=building.id)
        session.add(owner)
        session.flush()
        title, category, condition, trade_type, price, image_key, description = ITEMS[0]
        demo = Item(owner_id=owner.id, building_id=building.id, title=title,
                    category=category, condition=condition, trade_type=trade_type,
                    price=price, image_key=image_key, description=description)
        own = Item(owner_id=owner.id, building_id=building.id, title="用户自己发布的物品",
                   category=category, condition=condition, trade_type=trade_type,
                   price=price, image_key=image_key, description=description)
        session.add_all([demo, own])
        session.flush()
        session.add(HandoverSlot(item_id=demo.id, starts_at=now - timedelta(hours=1),
                                 ends_at=now - timedelta(minutes=30)))
        session.commit()

        assert ensure_future_demo_slots(session, community) == 3
        assert ensure_future_demo_slots(session, community) == 0
        demo_slots = session.exec(select(HandoverSlot).where(HandoverSlot.item_id == demo.id)).all()
        own_slots = session.exec(select(HandoverSlot).where(HandoverSlot.item_id == own.id)).all()
        assert len([slot for slot in demo_slots if as_utc(slot.starts_at) > now]) == 3
        assert own_slots == []
    engine.dispose()


@pytest.mark.parametrize(
    ("environment", "demo_enabled", "status", "existing_hours", "expected_added"),
    [
        ("development", "false", "AVAILABLE", [], 0),
        ("production", "true", "AVAILABLE", [], 0),
        ("development", "true", "COMPLETED", [], 0),
        ("development", "true", "RESERVED", [], 0),
        ("development", "true", "AVAILABLE", [1, 3, 25], 0),
        ("development", "true", "AVAILABLE", [1], 2),
    ],
)
def test_refresh_demo_slots_preserves_existing_times_and_respects_mode_and_status(
    monkeypatch, environment, demo_enabled, status, existing_hours, expected_added
):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("NEIGHLOOP_DEMO_MODE", demo_enabled)
    now = utc_now()
    monkeypatch.setattr("seed.utc_now", lambda: now)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            community = Community(name="边界测试社区")
            session.add(community)
            session.flush()
            building = Building(community_id=community.id, name="1号楼", map_key="building1")
            session.add(building)
            session.flush()
            owner = User(display_name="演示发布者", building_id=building.id)
            session.add(owner)
            session.flush()
            title, category, condition, trade_type, price, image_key, description = ITEMS[0]
            item = Item(owner_id=owner.id, building_id=building.id, title=title,
                        category=category, condition=condition, trade_type=trade_type,
                        price=price, image_key=image_key, description=description, status=status)
            session.add(item)
            session.flush()
            for hours in existing_hours:
                start = now + timedelta(hours=hours)
                session.add(HandoverSlot(item_id=item.id, starts_at=start,
                                        ends_at=start + timedelta(minutes=30)))
            session.commit()
            original = {
                slot.id: (as_utc(slot.starts_at), as_utc(slot.ends_at))
                for slot in session.exec(select(HandoverSlot)).all()
            }

            assert ensure_future_demo_slots(session, community) == expected_added
            assert ensure_future_demo_slots(session, community) == 0
            session.expire_all()
            slots = session.exec(select(HandoverSlot)).all()
            assert len(slots) == len(existing_hours) + expected_added
            current = {slot.id: (as_utc(slot.starts_at), as_utc(slot.ends_at)) for slot in slots}
            assert all(current[slot_id] == times for slot_id, times in original.items())
            assert all(as_utc(slot.ends_at) > as_utc(slot.starts_at) > now for slot in slots)
    finally:
        engine.dispose()
