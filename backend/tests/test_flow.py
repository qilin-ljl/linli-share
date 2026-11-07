import base64
from io import BytesIO
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from PIL import Image

from database import get_session
from main import app
from models import Building, Community, CommunityMember, CommunityProfile, Item, User
import main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEIGHLOOP_DEMO_MODE", "true")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        community = Community(name="测试社区")
        session.add(community)
        session.flush()
        building = Building(community_id=community.id, name="1号楼", map_key="building1")
        session.add(building)
        session.flush()
        users = [
            User(display_name="发布者", building_id=building.id),
            User(display_name="领取者", building_id=building.id),
            User(display_name="旁观者", building_id=building.id),
        ]
        session.add_all(users)
        session.flush()
        session.add(CommunityProfile(community_id=community.id, kind="NEIGHBORHOOD", city="测试城市",
                                     join_code="TESTCODE", is_public=True, latitude=31.2304,
                                     longitude=121.4737, created_by_id=users[0].id))
        session.add_all([CommunityMember(community_id=community.id, user_id=u.id,
                                         building_id=building.id, role="MEMBER") for u in users])
        session.commit()

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def as_user(user_id, community_id=1):
    return {"X-Demo-User-Id": str(user_id), "X-Community-Id": str(community_id)}


def test_effective_status_accepts_sqlite_naive_timestamp():
    item = Item(status="AVAILABLE", created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    assert main.effective_status(item) == "AVAILABLE"


def test_publish_reserve_pickup_complete_and_archive(client):
    payload = {
        "title": "测试台灯", "description": "暖光台灯，功能正常", "category": "家居", "condition": "九成新",
        "trade_type": "FREE", "price": None, "building_id": 1, "image_key": 0,
    }
    created = client.post("/api/items", json=payload, headers=as_user(1))
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    assert client.get("/api/community/stats").json()["active_count"] == 1
    assert client.get("/api/community/map?trade_type=FREE").json()["buildings"][0]["active_count"] == 1
    assert client.get("/api/community/map?trade_type=FIXED_PRICE").json()["buildings"][0]["active_count"] == 0

    assert client.post(f"/api/items/{item_id}/interest", headers=as_user(1)).status_code == 403
    assert client.post(f"/api/items/{item_id}/interest", headers=as_user(2)).status_code == 200
    assert client.post(f"/api/items/{item_id}/interest", headers=as_user(2)).status_code == 200
    assert client.get(f"/api/items/{item_id}", headers=as_user(1)).json()["interest_count"] == 1
    assert client.post(f"/api/items/{item_id}/comments", json={"body": "请问还在吗？"}, headers=as_user(2)).status_code == 201
    slot_id = client.get(f"/api/items/{item_id}", headers=as_user(2)).json()["handover_slots"][0]["id"]
    booked = client.post(f"/api/items/{item_id}/reservations", json={"slot_id": slot_id}, headers=as_user(2))
    assert booked.status_code == 201, booked.text
    reservation_id = booked.json()["id"]
    assert client.post(f"/api/items/{item_id}/reservations", json={"slot_id": slot_id}, headers=as_user(2)).status_code == 409
    assert client.post(f"/api/reservations/{reservation_id}/confirm", headers=as_user(3)).status_code == 403
    assert client.post(f"/api/items/{item_id}/complete", json={"recipient_id": 2}, headers=as_user(1)).status_code == 409

    confirmed = client.post(f"/api/reservations/{reservation_id}/confirm", headers=as_user(1))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["pickup_code"] is None
    buyer_bookings = client.get("/api/my/reservations", headers=as_user(2)).json()
    assert len(buyer_bookings) == 1 and len(buyer_bookings[0]["pickup_code"]) == 4
    buyer_detail = client.get(f"/api/items/{item_id}", headers=as_user(2)).json()
    code = buyer_detail["my_reservation"]["pickup_code"]
    assert len(code) == 4
    assert buyer_detail["status"] == "RESERVED"
    assert client.post(f"/api/items/{item_id}/reservations", json={"slot_id": slot_id}, headers=as_user(3)).status_code == 409
    assert client.post(f"/api/reservations/{reservation_id}/complete", json={"pickup_code": "0000"}, headers=as_user(1)).status_code == 422

    completed = client.post(f"/api/reservations/{reservation_id}/complete", json={"pickup_code": code}, headers=as_user(1))
    assert completed.status_code == 200, completed.text
    assert completed.json()["item"]["status"] == "COMPLETED"
    assert completed.json()["item"]["completed_at"].endswith("+00:00")
    assert client.post(f"/api/reservations/{reservation_id}/complete", json={"pickup_code": code}, headers=as_user(1)).status_code == 409
    assert client.post(f"/api/items/{item_id}/interest", headers=as_user(3)).status_code == 409
    assert client.post(f"/api/items/{item_id}/comments", json={"body": "还能要吗"}, headers=as_user(3)).status_code == 409
    assert client.get("/api/items", headers=as_user(2)).json() == []
    assert len(client.get("/api/items?status=COMPLETED", headers=as_user(2)).json()) == 1
    stats = client.get("/api/community/stats").json()
    assert stats["active_count"] == 0 and stats["total_completed"] == 1
    assert stats["daily_trend"][-1]["published"] == 1
    assert stats["daily_trend"][-1]["completed"] == 1
    assert stats["category_distribution"][0]["category"] == "家居"
    assert stats["building_heat"][0]["completed_count"] == 1
    summary = client.get("/api/my/summary", headers=as_user(1)).json()
    assert summary["published_count"] == 1 and summary["completed_count"] == 1
    assert summary["received_interests"] == 1 and summary["helped_neighbors"] == 1
    assert client.get("/api/my/reservations", headers=as_user(2)).json() == []
    assert client.get("/api/my/activity", headers=as_user(1)).json()[0]["item_title"] == "测试台灯"


def test_ai_reports_missing_key_without_fake_answer(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    response = client.post("/api/ai/optimize-description", json={
        "title": "测试台灯", "rough_description": "灯能用，外观不错", "condition": "九成新"
    }, headers=as_user(1))
    assert response.status_code == 503
    assert "DeepSeek API Key" in response.json()["detail"]


def test_description_ai_retries_empty_json_without_thinking(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            content = "" if len(calls) == 1 else '{"description":"灯光柔和，适合放在书桌上，欢迎邻居来看看。"}'
            message = type("Message", (), {"content": content})()
            choice = type("Choice", (), {"message": message, "finish_reason": "stop"})()
            return type("Result", (), {"choices": [choice]})()

    completions = FakeCompletions()
    fake_client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(main, "OpenAI", lambda **kwargs: fake_client)
    result = main.deepseek_json("请输出JSON", "台灯", fast=True, required_key="description")
    assert result["description"].startswith("灯光柔和")
    assert len(calls) == 2
    assert all(call["extra_body"] == {"thinking": {"type": "disabled"}} for call in calls)


def test_recommendations_follow_explicit_preferences_not_views(client):
    base = {"description": "功能正常，可在楼下自提", "condition": "九成新", "trade_type": "FREE", "price": None, "building_id": 1}
    plant = client.post("/api/items", json={**base, "title": "绿萝盆栽", "category": "绿植", "image_key": 1}, headers=as_user(1)).json()
    book = client.post("/api/items", json={**base, "title": "科普图书", "category": "图书", "image_key": 10}, headers=as_user(1)).json()

    assert client.post(f"/api/items/{plant['id']}/view", headers=as_user(2)).status_code == 200
    assert client.post(f"/api/items/{plant['id']}/view", headers=as_user(2)).status_code == 200
    assert client.post(f"/api/items/{book['id']}/view", headers=as_user(3)).status_code == 200
    assert client.patch("/api/me/preferences", json={"goals": ["FIND"], "categories": ["绿植"],
                        "trade_preferences": [], "use_distance": False}, headers=as_user(2)).status_code == 200
    assert client.patch("/api/me/preferences", json={"goals": ["FIND"], "categories": ["图书"],
                        "trade_preferences": [], "use_distance": False}, headers=as_user(3)).status_code == 200
    for_user_2 = client.get("/api/recommendations", headers=as_user(2)).json()
    for_user_3 = client.get("/api/recommendations", headers=as_user(3)).json()
    assert for_user_2["items"][0]["id"] == plant["id"]
    assert for_user_3["items"][0]["id"] == book["id"]
    assert for_user_2["items"][0]["recommendation_reason"] == "你选择的绿植兴趣"
    assert client.get("/api/recommendations?mode=FREE&limit=1", headers=as_user(2)).json()["total"] == 2


def test_recommendations_use_completed_receipts(client):
    base = {"description": "正常使用，社区自提", "condition": "九成新", "trade_type": "FREE", "building_id": 1}
    received = client.post("/api/items", json={**base, "title": "以前领过的绿萝", "category": "绿植"}, headers=as_user(1)).json()
    slot = client.get(f"/api/items/{received['id']}", headers=as_user(2)).json()["handover_slots"][0]
    booking = client.post(f"/api/items/{received['id']}/reservations", json={"slot_id": slot["id"]}, headers=as_user(2)).json()
    assert client.post(f"/api/reservations/{booking['id']}/confirm", headers=as_user(1)).status_code == 200
    code = client.get(f"/api/items/{received['id']}", headers=as_user(2)).json()["my_reservation"]["pickup_code"]
    assert client.post(f"/api/reservations/{booking['id']}/complete", json={"pickup_code": code}, headers=as_user(1)).status_code == 200
    plant = client.post("/api/items", json={**base, "title": "新的绿萝盆栽", "category": "绿植"}, headers=as_user(1)).json()
    client.post("/api/items", json={**base, "title": "更新的书架", "category": "家居"}, headers=as_user(1))
    result = client.get("/api/recommendations", headers=as_user(2)).json()
    assert result["items"][0]["id"] == plant["id"]
    assert "曾领过" in result["items"][0]["recommendation_reason"]


def test_market_advanced_filters_and_sorting(client):
    base = {"description": "功能正常，可在楼下自提", "category": "家居", "condition": "九成新", "building_id": 1}
    cheap = client.post("/api/items", json={**base, "title": "便宜台灯", "trade_type": "FIXED_PRICE", "price": 20, "image_key": 0}, headers=as_user(1)).json()
    expensive = client.post("/api/items", json={**base, "title": "贵一些的椅子", "trade_type": "FIXED_PRICE", "price": 100, "image_key": 3}, headers=as_user(1)).json()
    client.post("/api/items", json={**base, "title": "免费书架", "trade_type": "FREE", "price": None, "image_key": 2}, headers=as_user(1))

    priced = client.get("/api/items?category=家居&condition=九成新&min_price=10&max_price=50", headers=as_user(2)).json()
    assert [item["id"] for item in priced] == [cheap["id"]]
    descending = client.get("/api/items?sort_by=PRICE_DESC", headers=as_user(2)).json()
    assert [item["id"] for item in descending[:2]] == [expensive["id"], cheap["id"]]
    assert client.get("/api/items?freshness_hours=24", headers=as_user(2)).status_code == 200
    assert client.get("/api/items?min_price=100&max_price=10", headers=as_user(2)).status_code == 422


def test_create_join_and_isolate_communities(client):
    created = client.post("/api/communities", json={
        "name": "办公室测试圈", "kind": "OFFICE", "city": "测试城市", "district": "一区",
        "location_names": ["三楼", "四楼"],
    }, headers=as_user(1))
    assert created.status_code == 201, created.text
    community = created.json()
    community_id = community["id"]
    building_id = community["buildings"][0]["id"]
    code = community["join_code"]
    assert community["joined"] is True
    assert client.get("/api/items", headers={"X-Community-Id": str(community_id)}).status_code == 403
    assert client.get("/api/items", headers=as_user(2, community_id)).status_code == 403
    assert client.post(f"/api/communities/{community_id}/join", json={
        "join_code": "WRONG", "building_id": building_id
    }, headers=as_user(2)).status_code == 403
    assert client.post(f"/api/communities/{community_id}/join", json={
        "join_code": code, "building_id": building_id
    }, headers=as_user(2)).status_code == 200

    payload = {"title": "办公室台灯", "description": "暖光，功能正常，可在三楼自提", "category": "家居",
               "condition": "九成新", "trade_type": "FREE", "price": None,
               "building_id": building_id, "image_key": 0}
    item = client.post("/api/items", json=payload, headers=as_user(1, community_id)).json()
    assert item["id"] in [entry["id"] for entry in client.get("/api/items", headers=as_user(2, community_id)).json()]
    assert client.get(f"/api/items/{item['id']}", headers=as_user(2, 1)).status_code == 404
    assert any(event["item_id"] == item["id"] for event in client.get("/api/activity", headers=as_user(2, community_id)).json())
    assert all(event["item_id"] != item["id"] for event in client.get("/api/activity", headers=as_user(1, 1)).json())
    slot_id = client.get(f"/api/items/{item['id']}", headers=as_user(2, community_id)).json()["handover_slots"][0]["id"]
    reservation = client.post(f"/api/items/{item['id']}/reservations", json={"slot_id": slot_id}, headers=as_user(2, community_id)).json()
    assert client.post(f"/api/reservations/{reservation['id']}/confirm", headers=as_user(1, 1)).status_code == 404
    assert client.get("/api/community/stats", headers=as_user(1, community_id)).json()["active_count"] == 1
    assert client.get("/api/community/stats", headers=as_user(1, 1)).json()["active_count"] == 0
    assert client.get("/api/my/summary", headers=as_user(1, community_id)).json()["published_count"] == 1
    assert client.get("/api/my/summary", headers=as_user(1, 1)).json()["published_count"] == 0


def test_heartbeat_blocks_booking_until_owner_reconfirms(client, monkeypatch):
    payload = {"title": "待确认台灯", "description": "灯光正常，适合书桌使用", "category": "家居",
               "condition": "九成新", "trade_type": "FREE", "price": None, "building_id": 1}
    item = client.post("/api/items", json=payload, headers=as_user(1)).json()
    slot_id = client.get(f"/api/items/{item['id']}", headers=as_user(2)).json()["handover_slots"][0]["id"]
    future = datetime.now(timezone.utc) + timedelta(days=4)
    monkeypatch.setattr(main, "utc_now", lambda: future)
    assert client.get(f"/api/items/{item['id']}", headers=as_user(2)).json()["status"] == "UNCONFIRMED"
    assert client.post(f"/api/items/{item['id']}/reservations", json={"slot_id": slot_id}, headers=as_user(2)).status_code == 409
    assert client.patch(f"/api/items/{item['id']}/confirm-active", headers=as_user(2)).status_code == 403
    confirmed = client.patch(f"/api/items/{item['id']}/confirm-active", headers=as_user(1))
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "AVAILABLE"
    archived = client.post(f"/api/items/{item['id']}/archive", headers=as_user(1))
    assert archived.status_code == 200 and archived.json()["status"] == "ARCHIVED"


def test_confirmed_booking_can_be_cancelled_and_reopened(client):
    payload = {"title": "可预约书架", "description": "四层书架，结构稳固", "category": "家居",
               "condition": "八成新", "trade_type": "FIXED_PRICE", "price": 60, "building_id": 1}
    item = client.post("/api/items", json=payload, headers=as_user(1)).json()
    slot_id = client.get(f"/api/items/{item['id']}", headers=as_user(2)).json()["handover_slots"][0]["id"]
    reservation = client.post(f"/api/items/{item['id']}/reservations", json={"slot_id": slot_id}, headers=as_user(2)).json()
    client.post(f"/api/reservations/{reservation['id']}/confirm", headers=as_user(1))
    assert client.post(f"/api/reservations/{reservation['id']}/cancel", headers=as_user(2)).status_code == 200
    assert client.get(f"/api/items/{item['id']}", headers=as_user(2)).json()["status"] == "AVAILABLE"
    assert client.post(f"/api/items/{item['id']}/reservations", json={"slot_id": slot_id}, headers=as_user(2)).status_code == 201


def test_pricing_strategy_fallback_is_labelled(client, monkeypatch):
    monkeypatch.setattr(main, "deepseek_json", lambda *_: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    result = client.post("/api/ai/pricing-suggestion", json={"title": "测试台灯", "description": "功能正常，九成新",
        "category": "家居", "condition": "九成新", "disposal_goal": "FAST", "original_price": 120}, headers=as_user(1))
    assert result.status_code == 200
    data = result.json()
    assert data["source"] == "RULE_FALLBACK"
    assert 0 <= data["quick_price"] <= data["balanced_price"] <= data["price_first"]
    assert data["recommended_mode"] == "FAST"
    assert data["options"]["balanced"]["price"] == data["balanced_price"]
    assert any("处理目标" in factor for factor in data["factors"])


def test_item_timeline_activity_and_buyer_handover_progress(client):
    payload = {"title": "流转台灯", "description": "暖光灯泡一起转，开关正常", "category": "家居",
               "condition": "九成新", "trade_type": "FIXED_PRICE", "price": 50, "building_id": 1,
               "selected_price_strategy": "BALANCED", "selected_price_source": "DEEPSEEK"}
    item = client.post("/api/items", json=payload, headers=as_user(1)).json()
    item_id = item["id"]
    slot_id = client.get(f"/api/items/{item_id}", headers=as_user(2)).json()["handover_slots"][0]["id"]
    client.post(f"/api/items/{item_id}/interest", headers=as_user(2))
    reservation = client.post(f"/api/items/{item_id}/reservations", json={"slot_id": slot_id}, headers=as_user(2)).json()
    rid = reservation["id"]
    assert client.post(f"/api/reservations/{rid}/confirm", headers=as_user(1)).status_code == 200
    assert client.post(f"/api/reservations/{rid}/handover-status", json={"status": "DEPARTED"}, headers=as_user(1)).status_code == 403
    departed = client.post(f"/api/reservations/{rid}/handover-status", json={"status": "DEPARTED"}, headers=as_user(2))
    assert departed.status_code == 200 and departed.json()["handover_status"] == "DEPARTED"
    assert client.post(f"/api/reservations/{rid}/handover-status", json={"status": "DEPARTED"}, headers=as_user(2)).status_code == 200
    delayed = client.post(f"/api/reservations/{rid}/handover-status", json={"status": "DELAYED"}, headers=as_user(2))
    assert delayed.json()["delay_minutes"] == 10
    arrived = client.post(f"/api/reservations/{rid}/handover-status", json={"status": "ARRIVED"}, headers=as_user(2))
    assert arrived.json()["arrived_at"] is not None
    assert client.post(f"/api/reservations/{rid}/handover-status", json={"status": "DELAYED"}, headers=as_user(2)).status_code == 409
    code = client.get(f"/api/items/{item_id}", headers=as_user(2)).json()["my_reservation"]["pickup_code"]
    assert client.post(f"/api/reservations/{rid}/complete", json={"pickup_code": code}, headers=as_user(1)).status_code == 200

    timeline = client.get(f"/api/items/{item_id}/events", headers=as_user(1)).json()
    types = [event["type"] for event in timeline["events"]]
    assert types == ["ITEM_CREATED", "PRICE_STRATEGY_SELECTED", "WANT_CREATED", "RESERVATION_CREATED",
                     "RESERVATION_CONFIRMED", "BUYER_DEPARTED", "BUYER_DELAYED", "BUYER_ARRIVED", "TRANSACTION_COMPLETED"]
    assert timeline["total_minutes"] is not None
    assert all("pickup_code" not in event for event in timeline["events"])
    activity = client.get("/api/activity?limit=10", headers=as_user(2)).json()
    assert activity[0]["type"] == "TRANSACTION_COMPLETED"
    assert all(event["type"] not in {"BUYER_DEPARTED", "BUYER_ARRIVED", "BUYER_DELAYED"} for event in activity)
    stats = client.get("/api/community/stats", headers=as_user(1)).json()
    assert stats["no_chat_completion_rate"] == 100
    assert stats["avg_transfer_hours"] >= 0


def test_overdue_wait_then_release_reuses_cancel_flow(client, monkeypatch):
    payload = {"title": "预约书桌", "description": "书桌稳固，楼下自提", "category": "家居",
               "condition": "八成新", "trade_type": "FREE", "price": None, "building_id": 1}
    item = client.post("/api/items", json=payload, headers=as_user(1)).json()
    slot = client.get(f"/api/items/{item['id']}", headers=as_user(2)).json()["handover_slots"][0]
    reservation = client.post(f"/api/items/{item['id']}/reservations", json={"slot_id": slot["id"]}, headers=as_user(2)).json()
    rid = reservation["id"]
    client.post(f"/api/reservations/{rid}/confirm", headers=as_user(1))
    assert client.post(f"/api/reservations/{rid}/release", headers=as_user(1)).status_code == 409
    overdue_now = datetime.fromisoformat(slot["starts_at"]) + timedelta(minutes=16)
    monkeypatch.setattr(main, "utc_now", lambda: overdue_now)
    assert client.post(f"/api/reservations/{rid}/wait", headers=as_user(2)).status_code == 403
    waiting = client.post(f"/api/reservations/{rid}/wait", headers=as_user(1))
    assert waiting.status_code == 200 and waiting.json()["overdue"] is False
    assert client.post(f"/api/reservations/{rid}/release", headers=as_user(1)).status_code == 409
    monkeypatch.setattr(main, "utc_now", lambda: overdue_now + timedelta(minutes=11))
    released = client.post(f"/api/reservations/{rid}/release", headers=as_user(1))
    assert released.status_code == 200 and released.json()["status"] == "CANCELLED"
    assert client.get(f"/api/items/{item['id']}", headers=as_user(1)).json()["status"] == "AVAILABLE"
    event_types = [event["type"] for event in client.get(f"/api/items/{item['id']}/events", headers=as_user(1)).json()["events"]]
    assert event_types[-2:] == ["SELLER_WAIT_EXTENDED", "RESERVATION_CANCELLED"]


def test_private_item_chat_and_owner_only_timeline(client):
    item = client.post("/api/items", json={
        "title": "私聊测试台灯", "description": "灯光正常，可约楼下交接", "category": "家居",
        "condition": "九成新", "trade_type": "FREE", "price": None, "building_id": 1,
    }, headers=as_user(1)).json()
    path = f"/api/items/{item['id']}"
    assert client.get(f"{path}/events", headers=as_user(2)).status_code == 403
    assert client.get(f"{path}/events", headers=as_user(3)).status_code == 403
    assert client.get(f"{path}/events", headers=as_user(1)).status_code == 200

    assert client.post(f"{path}/interest", headers=as_user(2)).status_code == 200
    assert client.get("/api/my/interests", headers=as_user(2)).json()[0]["id"] == item["id"]
    owner_events = client.get(f"{path}/events", headers=as_user(1)).json()["events"]
    assert any("领取者" in event["text"] for event in owner_events if event["type"] == "WANT_CREATED")
    assert client.get(f"{path}", headers=as_user(2)).json()["interested_users"] == []
    assert client.post("/api/presence/heartbeat", headers=as_user(1)).status_code == 200

    assert client.get(f"{path}/messages?other_user_id=1", headers=as_user(3)).json() == []
    sent = client.post(f"{path}/messages", json={"other_user_id": 1, "body": "请问可以周末取吗？"}, headers=as_user(2))
    assert sent.status_code == 201, sent.text
    assert client.get(f"{path}/messages?other_user_id=1", headers=as_user(2)).json()[0]["body"] == "请问可以周末取吗？"
    assert client.get(f"{path}/messages?other_user_id=2", headers=as_user(1)).json()[0]["body"] == "请问可以周末取吗？"
    assert client.get(f"{path}/messages?other_user_id=2", headers=as_user(3)).status_code == 403
    assert client.post(f"{path}/messages", json={"other_user_id": 3, "body": "越权消息"}, headers=as_user(2)).status_code == 403
    assert client.post(f"{path}/messages", json={"other_user_id": 2, "body": "周末可以，私聊约时间。"}, headers=as_user(1)).status_code == 201
    assert len(client.get(f"{path}/messages?other_user_id=1", headers=as_user(2)).json()) == 2

    conversations = client.get(f"{path}/conversations", headers=as_user(1)).json()
    assert any(entry["user"]["id"] == 2 for entry in conversations)
    assert client.get(f"{path}/conversations", headers=as_user(3)).status_code == 403


def test_offline_ai_faq_and_private_reservation_messages(client, monkeypatch):
    monkeypatch.setattr(main, "item_faq_answer", lambda session, item, question: "AI：公开信息显示物品还在架，时间请以预约选项为准。")
    item = client.post("/api/items", json={"title": "预约测试书架", "description": "四层书架，社区自提",
        "category": "家居", "condition": "八成新", "trade_type": "FREE", "building_id": 1}, headers=as_user(1)).json()
    path = f"/api/items/{item['id']}"
    assert len(client.get(f"{path}/faq").json()["questions"]) == 5
    sent = client.post(f"{path}/messages", json={"other_user_id": 1, "body": "书架还在吗？"}, headers=as_user(2))
    assert sent.status_code == 201
    messages = client.get(f"{path}/messages?other_user_id=1", headers=as_user(2)).json()
    assert len(messages) == 2 and messages[-1]["is_ai"] is True
    assert client.get(f"{path}/messages?other_user_id=1", headers=as_user(3)).json() == []
    assert client.get("/api/messages/threads", headers=as_user(3)).json() == []
    assert client.get("/api/messages/threads", headers=as_user(1)).json()[0]["unread_count"] == 1
    assert client.post(f"{path}/messages/read?other_user_id=2", headers=as_user(1)).json()["read"] == 1
    assert client.get("/api/messages/threads", headers=as_user(1)).json()[0]["unread_count"] == 0
    faq = client.post(f"{path}/faq", json={"other_user_id": 1, "question": "可以预约什么时间？"}, headers=as_user(2))
    assert faq.status_code == 201 and faq.json()["message_type"] == "AI_REPLY"
    slot = client.get(path, headers=as_user(2)).json()["handover_slots"][0]
    booked = client.post(f"{path}/reservations", json={"slot_id": slot["id"]}, headers=as_user(2))
    assert booked.status_code == 201
    assert any(row["message_type"] == "RESERVATION" for row in client.get(f"{path}/messages?other_user_id=2", headers=as_user(1)).json())
    rid = booked.json()["id"]
    assert client.get("/api/messages/threads", headers=as_user(2)).json()[0]["reservation_status"] == "PENDING"
    assert client.post(f"/api/reservations/{rid}/confirm", headers=as_user(1)).status_code == 200
    assert any("预约已确认" in row["body"] for row in client.get(f"{path}/messages?other_user_id=1", headers=as_user(2)).json())


def test_need_discussion_only_attaches_own_active_item(client):
    item = client.post("/api/items", json={"title": "可分享的书桌", "description": "书桌稳固，楼下自提",
        "category": "家居", "condition": "八成新", "trade_type": "FREE", "building_id": 1}, headers=as_user(1)).json()
    need = client.post("/api/needs", json={"raw_text": "想找一张小书桌", "category": "家居", "keywords": ["书桌"]}, headers=as_user(2)).json()
    path = f"/api/needs/{need['id']}/replies"
    assert client.post(path, json={"body": "我有一张书桌", "item_id": item["id"]}, headers=as_user(3)).status_code == 403
    reply = client.post(path, json={"body": "我这张书桌可以看看", "item_id": item["id"]}, headers=as_user(1))
    assert reply.status_code == 201 and reply.json()["item"]["id"] == item["id"]
    assert len(client.get(path, headers=as_user(3)).json()) == 1


def test_need_channel_filters_and_discussion_counts(client):
    item = client.post("/api/items", json={"title": "频道测试台灯", "description": "暖光台灯可自提",
        "category": "家居", "condition": "九成新", "trade_type": "FREE", "building_id": 1}, headers=as_user(1)).json()
    lamp = client.post("/api/needs", json={"raw_text": "想找书桌用的台灯", "category": "家居",
        "keywords": ["台灯"], "budget_max": 60}, headers=as_user(2)).json()
    cooker = client.post("/api/needs", json={"raw_text": "需要一台电饭煲", "category": "家电",
        "keywords": ["电饭煲"]}, headers=as_user(3)).json()
    assert client.post(f"/api/needs/{lamp['id']}/replies", json={"body": "我有一盏台灯", "item_id": item["id"]},
                       headers=as_user(1)).status_code == 201
    assert {"家居", "家电"}.issubset(set(client.get("/api/bootstrap").json()["need_categories"]))
    base = "/api/needs?"
    assert [row["id"] for row in client.get(base + "q=台灯").json()] == [lamp["id"]]
    assert [row["id"] for row in client.get(base + "category=家电").json()] == [cooker["id"]]
    assert [row["id"] for row in client.get(base + "reply_state=UNANSWERED").json()] == [cooker["id"]]
    with_listing = client.get(base + "reply_state=WITH_LISTING").json()
    assert [row["id"] for row in with_listing] == [lamp["id"]]
    assert with_listing[0]["reply_count"] == 1 and with_listing[0]["user"]["id"] == 2
    assert client.get(base + "sort_by=MOST_DISCUSSED").json()[0]["id"] == lamp["id"]
    assert client.get(base + "reply_state=INVALID").status_code == 422


def test_guest_register_login_preferences_and_logout(client):
    assert client.get("/api/items").status_code == 200
    assert client.get("/api/community/stats").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/items", json={"title": "游客台灯", "description": "测试游客不可发布", "category": "家居",
                                            "condition": "九成新", "trade_type": "FREE", "building_id": 1}).status_code == 401
    registered = client.post("/api/auth/register", json={"email": "New@Example.com", "password": "strong-pass-123"})
    assert registered.status_code == 201, registered.text
    assert registered.json()["user"]["email"] == "new@example.com"
    assert registered.json()["user"]["onboarding_completed"] is False
    assert "password_hash" not in registered.json()["user"]
    assert client.get("/api/auth/me").status_code == 200
    protected = {"X-NeighLoop-Request": "1"}
    assert client.patch("/api/me/preferences", json={"goals": ["MOVE", "GIVE"], "categories": ["家居"],
                        "trade_preferences": ["FREE"], "use_distance": False}, headers=protected).status_code == 200
    joined = client.patch("/api/me/community", json={"community_id": 1, "building_id": 1, "join_code": "TESTCODE"}, headers=protected)
    assert joined.status_code == 200, joined.text
    assert client.post("/api/me/onboarding/complete", headers=protected).json()["onboarding_completed"] is True
    assert client.post("/api/auth/logout", headers=protected).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "new@example.com", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "new@example.com", "password": "strong-pass-123"}).status_code == 200
    assert client.get("/api/me/preferences").json()["goals"] == ["MOVE", "GIVE"]


def test_public_demo_selector_issues_persistent_cookie_for_allowlisted_account(client, monkeypatch):
    session_source = app.dependency_overrides[get_session]()
    session = next(session_source)
    user = session.get(User, 1)
    user.email = "seller@neighloop.demo"
    session.add(user)
    session.commit()
    session_source.close()

    monkeypatch.setenv("NEIGHLOOP_PUBLIC_DEMO_MODE", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    listed = client.get("/api/auth/demo-accounts")
    assert listed.status_code == 200
    assert [account["id"] for account in listed.json()] == [1]
    assert client.post("/api/auth/demo-login", json={"user_id": 2},
                       headers={"X-NeighLoop-Request": "1"}).status_code == 403
    assert client.post("/api/auth/demo-login", json={"user_id": 1}).status_code == 403

    switched = client.post("https://testserver/api/auth/demo-login", json={"user_id": 1},
                           headers={"X-NeighLoop-Request": "1"})
    assert switched.status_code == 200, switched.text
    cookie = switched.headers["set-cookie"]
    assert "Max-Age=604800" in cookie and "Secure" in cookie and "HttpOnly" in cookie
    assert client.get("https://testserver/api/auth/me").json()["user"]["id"] == 1
    token = client.cookies.get("neighloop_session")
    client.cookies.clear()
    assert client.get("https://testserver/api/auth/me", headers={"Cookie": f"neighloop_session={token}"}).status_code == 200

    monkeypatch.setenv("NEIGHLOOP_PUBLIC_DEMO_MODE", "false")
    assert client.get("/api/auth/demo-accounts").json() == []
    assert client.post("/api/auth/demo-login", json={"user_id": 1},
                       headers={"X-NeighLoop-Request": "1"}).status_code == 404


def test_demo_identity_header_is_disabled_outside_demo_mode(client, monkeypatch):
    monkeypatch.setenv("NEIGHLOOP_DEMO_MODE", "false")
    assert client.get("/api/auth/me", headers=as_user(1)).status_code == 401
    assert client.post("/api/items", json={"title": "越权台灯", "description": "测试演示头不可用于正式模式",
                                            "category": "家居", "condition": "九成新", "trade_type": "FREE",
                                            "building_id": 1}, headers=as_user(1)).status_code == 401


def test_uploaded_photo_and_custom_category(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lZkAAAAASUVORK5CYII=")
    upload = client.post("/api/uploads/images", content=png,
                         headers={**as_user(1), "Content-Type": "image/png"})
    assert upload.status_code == 201, upload.text
    image_key = upload.json()["image_key"]
    served = client.get(f"/api/uploads/images/{image_key}")
    assert served.headers["content-type"].startswith("image/jpeg")
    assert served.content.startswith(b"\xff\xd8")
    payload = {"title": "相册上传台灯", "description": "实物照片，灯光正常", "category": "数码配件",
               "condition": "九成新", "trade_type": "FREE", "building_id": 1, "image_key": image_key}
    created = client.post("/api/items", json=payload, headers=as_user(1))
    assert created.status_code == 201, created.text
    assert created.json()["category"] == "数码配件"
    assert created.json()["image_key"] == image_key
    assert "数码配件" in client.get("/api/bootstrap", headers=as_user(1)).json()["categories"]
    assert client.post("/api/items", json=payload, headers=as_user(2)).status_code == 422
    image = Image.new("RGB", (4, 4), "white")
    metadata = Image.Exif()
    metadata[270] = "PRIVATE_LOCATION"
    output = BytesIO()
    image.save(output, format="JPEG", exif=metadata)
    cleaned = client.post("/api/uploads/images", content=output.getvalue(),
                          headers={**as_user(1), "Content-Type": "image/jpeg"}).json()
    assert b"PRIVATE_LOCATION" not in client.get(f"/api/uploads/images/{cleaned['image_key']}").content
    private = client.post("/api/communities", json={"name": "私有办公角", "kind": "OFFICE",
        "city": "测试城市", "location_names": ["三楼"]}, headers=as_user(1)).json()
    private_upload = client.post("/api/uploads/images", content=png,
        headers={**as_user(1, private["id"]), "Content-Type": "image/png"}).json()
    assert client.get(f"/api/uploads/images/{private_upload['image_key']}").status_code == 403
    assert client.get(f"/api/uploads/images/{private_upload['image_key']}", headers=as_user(1)).status_code == 200


def test_location_manual_search_needs_and_batch_publish(client):
    resolved = client.post("/api/location/resolve-community", json={"latitude": 31.2304, "longitude": 121.4737})
    assert resolved.json()["matched"] is True
    assert resolved.json()["distance_meters"] == 0
    assert client.post("/api/location/resolve-community", json={"latitude": 40, "longitude": 116}).json() == {"matched": False}
    assert client.get("/api/communities?keyword=测试城市").json()[0]["name"] == "测试社区"
    first = client.post("/api/needs", json={"raw_text": "想找电磁炉，100元以内", "category": "厨房小家电",
                                              "keywords": ["电磁炉"], "budget_max": 100, "building_id": 1}, headers=as_user(2))
    assert first.status_code == 201, first.text
    second = client.post("/api/needs", json={"raw_text": "找便宜的电磁炉，80元内", "category": "家电",
                                               "keywords": ["电磁炉"], "budget_max": 80, "building_id": 1}, headers=as_user(3))
    assert second.status_code == 201, second.text
    assert client.patch(f"/api/needs/{first.json()['id']}", json={"status": "CLOSED"}, headers=as_user(3)).status_code == 403
    payload = {"title": "电磁炉", "description": "电磁炉功能正常，有电源线", "category": "家电",
               "condition": "九成新", "trade_type": "FIXED_PRICE", "price": 70, "building_id": 1}
    assert client.post("/api/items/batch", json={"items": [payload]}, headers=as_user(1)).status_code == 422
    batch = client.post("/api/items/batch", json={"items": [payload, {**payload, "title": "电磁炉备用机"}],
                                                   "confirmed": True}, headers=as_user(1))
    assert batch.status_code == 201, batch.text
    assert batch.json()["count"] == 2
    with_distance = client.get("/api/items", headers={"X-Location-Latitude": "31.2304",
                                                       "X-Location-Longitude": "121.4737"}).json()
    assert with_distance[0]["distance_meters"] == 0
    assert "latitude" not in with_distance[0] and "longitude" not in with_distance[0]
    item_id = batch.json()["items"][0]["id"]
    matches = client.get(f"/api/items/{item_id}/matching-needs").json()
    assert matches["count"] == 2
    assert any("预算" in reason for entry in matches["matches"] for reason in entry["reasons"])
    summary = client.get("/api/communities/1/need-summary").json()
    assert summary["buildings"][0]["count"] == 2
    stats = client.get("/api/community/stats").json()
    assert stats["month_batch_items"] == 2 and stats["week_matched_need_count"] == 2


def test_passport_relist_and_progressive_handover_location(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    payload = {"title": "护照台灯", "description": "暖光台灯，外观正常，楼下交接", "category": "家居",
               "condition": "九成新", "trade_type": "FREE", "building_id": 1,
               "handover_location": "1号楼一楼大厅"}
    item = client.post("/api/items", json=payload, headers=as_user(1)).json()
    item_id = item["id"]
    public = client.get(f"/api/items/{item_id}").json()
    assert public["handover_location"] is None and public["visible_location"] == "1号楼附近"
    slot_id = public["handover_slots"][0]["id"]
    reservation = client.post(f"/api/items/{item_id}/reservations", json={"slot_id": slot_id}, headers=as_user(2)).json()
    pending = client.get(f"/api/items/{item_id}", headers=as_user(2)).json()
    assert pending["handover_location"] is None and pending["visible_location"] == "1号楼公共区域"
    client.post(f"/api/reservations/{reservation['id']}/confirm", headers=as_user(1))
    confirmed = client.get(f"/api/items/{item_id}", headers=as_user(2)).json()
    assert confirmed["handover_location"] == "1号楼一楼大厅"
    assert client.get(f"/api/items/{item_id}", headers=as_user(3)).json()["handover_location"] is None
    code = confirmed["my_reservation"]["pickup_code"]
    client.post(f"/api/reservations/{reservation['id']}/complete", json={"pickup_code": code}, headers=as_user(1))
    completed = client.get(f"/api/items/{item_id}", headers=as_user(2)).json()
    assert completed["viewer_can_relist"] is True
    passport_code = completed["passport_code"]
    assert client.post(f"/api/items/{item_id}/relist", json=payload, headers=as_user(1)).status_code == 403
    assert client.post(f"/api/items/{item_id}/relist", json=payload, headers=as_user(2)).status_code == 422
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lZkAAAAASUVORK5CYII=")
    fresh_photo = client.post("/api/uploads/images", content=png,
                              headers={**as_user(2), "Content-Type": "image/png"}).json()["image_key"]
    second = client.post(f"/api/items/{item_id}/relist", json={**payload, "image_key": fresh_photo}, headers=as_user(2))
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]
    second_slot = client.get(f"/api/items/{second_id}", headers=as_user(3)).json()["handover_slots"][0]["id"]
    reservation2 = client.post(f"/api/items/{second_id}/reservations", json={"slot_id": second_slot}, headers=as_user(3)).json()
    client.post(f"/api/reservations/{reservation2['id']}/confirm", headers=as_user(2))
    code2 = client.get(f"/api/items/{second_id}", headers=as_user(3)).json()["my_reservation"]["pickup_code"]
    client.post(f"/api/reservations/{reservation2['id']}/complete", json={"pickup_code": code2}, headers=as_user(2))
    passport = client.get(f"/api/passports/{passport_code}").json()
    assert passport["completed_count"] == 2 and passport["neighbor_count"] == 3
    assert passport["current_item_id"] == second_id
    assert [event["type"] for event in passport["timeline"]].count("TRANSACTION_COMPLETED") == 2
    assert all("一楼大厅" not in event["text"] for event in passport["timeline"])


def test_visual_analysis_is_separate_from_pricing_and_labels_fallback(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    monkeypatch.delenv("VISION_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lZkAAAAASUVORK5CYII=")
    keys = [client.post("/api/uploads/images", content=png,
                        headers={**as_user(1), "Content-Type": "image/png"}).json()["image_key"] for _ in range(2)]
    fallback = client.post("/api/ai/visual-estimate", json={"image_keys": keys}, headers=as_user(1))
    assert fallback.status_code == 200
    assert fallback.json()["analysis"]["source"] == "MANUAL_REVIEW_REQUIRED"
    assert fallback.json()["pricing"] is None
    assert "功能状态" in fallback.json()["analysis"]["unknowns"]

    visual = {"product_type": "电磁炉", "category": "家电", "brand": None, "model": None,
              "condition": "GOOD", "condition_score": 4, "visible_defects": ["面板轻微划痕"],
              "visible_accessories": ["电源线"], "unknowns": ["功能状态"], "source": "VISION_API"}
    monkeypatch.setattr(main, "analyze_item", lambda _: visual)
    monkeypatch.setattr(main, "deepseek_json", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    analyzed = client.post("/api/ai/visual-estimate", json={"image_keys": keys}, headers=as_user(1)).json()
    assert analyzed["analysis"]["product_type"] == "电磁炉"
    assert analyzed["pricing"]["source"] == "RULE_FALLBACK"
    assert analyzed["pricing"]["quick_price"] <= analyzed["pricing"]["balanced_price"] <= analyzed["pricing"]["price_first"]
    assert any("照片可见外观" in factor for factor in analyzed["pricing"]["factors"])


def test_batch_vision_keeps_one_main_object_per_photo(monkeypatch):
    from services import visual_analysis_service as vision

    monkeypatch.setattr(vision, "_vision_json", lambda *_: {"items": [
        {"photo_indices": [0], "product_type": "台灯", "category": "家居照明", "condition": "GOOD"},
        {"photo_indices": [0], "product_type": "背景中的地毯", "category": "家居", "condition": "GOOD"},
        {"photo_indices": [1], "product_type": "绿萝", "category": "绿植", "condition": "GOOD"},
    ]})
    result = vision.analyze_batch([(b"photo-a", "image/jpeg"), (b"photo-b", "image/jpeg")])
    assert result["source"] == "VISION_API"
    assert [entry["product_type"] for entry in result["items"]] == ["台灯", "绿萝"]
    assert result["items"][0]["category"] == "家居"


def test_need_ai_infers_options_for_vague_request_and_requires_confirmation(client, monkeypatch):
    monkeypatch.setattr(main, "deepseek_json", lambda *_: {"suggestions": [
        {"category": "家居", "keywords": ["台灯"], "reason": "搬家后可能需要照明", "inferred": True, "budget_max": 100},
        {"category": "家电", "keywords": ["电饭煲"], "reason": "搬家后可能需要做饭", "inferred": True},
    ]})
    vague = "我刚搬家过来，想看看有没有什么能用得上的东西"
    response = client.post("/api/ai/parse-need", json={"raw_text": vague}, headers=as_user(1))
    assert response.status_code == 200
    result = response.json()
    assert result["source"] == "DEEPSEEK"
    assert result["needs_clarification"] is False and result["inferred"] is True
    assert len(result["suggestions"]) == 2
    assert result["category"] == "家居" and result["keywords"] == ["台灯"]
    assert result["budget_max"] is None  # user never stated a price
    assert "推测" in result["message"]
    assert client.post("/api/needs", json={"raw_text": vague}, headers=as_user(1)).status_code == 422

    monkeypatch.setattr(main, "deepseek_json", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    unavailable = client.post("/api/ai/parse-need", json={"raw_text": vague}, headers=as_user(1)).json()
    assert unavailable["source"] == "RULE_FALLBACK" and unavailable["needs_clarification"] is True
    assert unavailable["suggestions"] == []

    monkeypatch.setattr(main, "deepseek_json", lambda *_: {"suggestions": [
        {"category": "家电", "keywords": ["电磁炉", "电饭锅"],
         "reason": "用户明确提到这两件物品", "inferred": False},
    ]})
    explicit = client.post("/api/ai/parse-need", json={
        "raw_text": "想找电磁炉或电饭锅，100元以内"
    }, headers=as_user(1)).json()
    assert explicit["needs_clarification"] is False
    assert explicit["category"] == "家电"
    assert explicit["keywords"] == ["电磁炉", "电饭锅"]
    assert explicit["budget_max"] == 100
