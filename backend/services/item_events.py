"""Single write path and presentation text for item lifecycle events."""

from datetime import datetime
from typing import Any

from sqlmodel import Session

from database import iso_utc
from models import Building, Item, ItemEvent, User

EVENT_TYPES = {
    "ITEM_CREATED", "PRICE_STRATEGY_SELECTED", "ACTIVE_CONFIRMED", "WANT_CREATED",
    "RESERVATION_CREATED", "RESERVATION_CONFIRMED", "BUYER_DEPARTED",
    "BUYER_ARRIVED", "BUYER_DELAYED", "RESERVATION_CANCELLED",
    "SELLER_WAIT_EXTENDED", "TRANSACTION_COMPLETED", "ITEM_ARCHIVED", "ITEM_RELISTED",
}
PUBLIC_ACTIVITY_TYPES = {"ITEM_CREATED", "ACTIVE_CONFIRMED", "RESERVATION_CONFIRMED", "TRANSACTION_COMPLETED"}
STRATEGY_NAMES = {"FAST": "快速流转", "BALANCED": "均衡流转", "PRICE_FIRST": "价格优先"}


def record_item_event(
    session: Session, item_id: int, event_type: str,
    user_id: int | None = None, metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> ItemEvent:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported item event type: {event_type}")
    event = ItemEvent(item_id=item_id, user_id=user_id, event_type=event_type,
                      metadata_json=metadata or None)
    if created_at is not None:
        event.created_at = created_at
    session.add(event)
    return event


def timeline_text(event: ItemEvent, item: Item, viewer_id: int, actor_name: str | None = None) -> str:
    metadata = event.metadata_json or {}
    actor = None
    if event.user_id and (viewer_id == item.owner_id or event.user_id == viewer_id):
        actor = actor_name or metadata.get("actor_name")
    name = actor or "邻居"
    match event.event_type:
        case "ITEM_CREATED":
            return "发布闲置"
        case "PRICE_STRATEGY_SELECTED":
            strategy = STRATEGY_NAMES.get(str(metadata.get("strategy")), "流转")
            source = "AI" if metadata.get("source") == "DEEPSEEK" else ""
            price = metadata.get("price")
            return f"采用{source}{strategy}建议 ¥{price}" if isinstance(price, int) else f"采用{source}{strategy}建议"
        case "ACTIVE_CONFIRMED":
            return "发布者确认物品还在"
        case "WANT_CREATED":
            return f"{name}表达了兴趣" if actor else "一位邻居表达了兴趣"
        case "RESERVATION_CREATED":
            return f"{name}提交了领取预约"
        case "RESERVATION_CONFIRMED":
            return "发布者接受了预约"
        case "BUYER_DEPARTED":
            return f"{name}已出发"
        case "BUYER_ARRIVED":
            return f"{name}已到达交接地点"
        case "BUYER_DELAYED":
            return f"{name}预计晚到约{metadata.get('delay_minutes', 10)}分钟"
        case "RESERVATION_CANCELLED":
            return "预约已取消"
        case "SELLER_WAIT_EXTENDED":
            return "发布者决定再等10分钟"
        case "TRANSACTION_COMPLETED":
            return "完成交接，物品找到了新主人"
        case "ITEM_ARCHIVED":
            return "物品已归档"
        case "ITEM_RELISTED":
            return "上一位邻居再次发布这件物品"
    return event.event_type


def event_data(event: ItemEvent, item: Item, viewer_id: int, actor_name: str | None = None) -> dict:
    return {"id": event.id, "item_id": item.id, "type": event.event_type,
            "text": timeline_text(event, item, viewer_id, actor_name), "created_at": iso_utc(event.created_at)}


def activity_data(session: Session, event: ItemEvent, item: Item) -> dict:
    building = session.get(Building, item.building_id)
    if event.event_type == "ITEM_CREATED":
        text = f"{building.name}发布了「{item.title}」"
    elif event.event_type == "ACTIVE_CONFIRMED":
        text = f"「{item.title}」已确认仍在架"
    elif event.event_type == "RESERVATION_CONFIRMED":
        text = f"「{item.title}」已经有人预约"
    else:
        text = f"「{item.title}」找到了新主人"
    return {"id": event.id, "type": event.event_type, "text": text,
            "created_at": iso_utc(event.created_at), "item_id": item.id}
