"""Explicit request matching based only on category, keywords and budget."""

from datetime import datetime, timezone

from models import Item, Need


def need_is_active(need: Need, now: datetime) -> bool:
    expires = need.expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return need.status == "ACTIVE" and (expires is None or expires > now)


def match_need(item: Item, need: Need) -> list[str]:
    if item.owner_id == need.user_id:
        return []
    title = f"{item.title} {item.description}".lower()
    normalized = {"厨房电器": "家电", "厨房家电": "家电", "厨房小家电": "家电",
                  "家具": "家居", "生活日用": "生活用品"}
    item_category = normalized.get(item.category, item.category)
    need_category = normalized.get(need.category or "", need.category or "")
    category_matches = bool(need_category and item_category == need_category)
    keyword_matches = [word for word in need.keywords if len(word.strip()) >= 2 and word.lower() in title]
    if not category_matches and not keyword_matches:
        return []
    if (need.budget_min is not None or need.budget_max is not None) and item.trade_type == "NEGOTIABLE":
        return []
    price = item.price if item.trade_type == "FIXED_PRICE" else 0
    if need.budget_min is not None and price < need.budget_min:
        return []
    if need.budget_max is not None and price > need.budget_max:
        return []
    reasons = ["位于同一社区"]
    if category_matches:
        reasons.append(f"都属于{need.category}")
    if keyword_matches:
        reasons.append(f"物品信息包含：{'、'.join(keyword_matches[:3])}")
    if need.budget_max is not None:
        reasons.append(f"标价满足不超过 ¥{need.budget_max} 的预算")
    return reasons
