"""Unit tests for need matching service."""
from types import SimpleNamespace

from services.need_matching_service import match_need


def _make_item(**kwargs):
    defaults = {
        "owner_id": "item-owner",
        "title": "",
        "description": "",
        "category": "",
        "price": 0,
        "trade_type": "FIXED_PRICE",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_need(**kwargs):
    defaults = {
        "user_id": "need-owner",
        "category": None,
        "keywords": [],
        "budget_min": None,
        "budget_max": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_same_owner_item_does_not_match():
    item = _make_item(owner_id="user-1")
    need = _make_need(user_id="user-1", category="家电")
    assert match_need(item, need) == []


def test_category_synonym_kitchen_appliance_normalizes_to_home_appliance():
    item = _make_item(category="厨房电器", title="电饭煲", description="")
    need = _make_need(category="家电")
    reasons = match_need(item, need)
    assert "都属于家电" in reasons


def test_keyword_shorter_than_two_chars_is_ignored():
    item = _make_item(category="家具", title="a", description="")
    need = _make_need(category="家电", keywords=["a"])
    assert match_need(item, need) == []


def test_fixed_price_within_budget_matches():
    item = _make_item(category="家电", price=15, trade_type="FIXED_PRICE")
    need = _make_need(category="家电", budget_min=10, budget_max=20)
    reasons = match_need(item, need)
    assert reasons
    assert "标价满足不超过 ¥20 的预算" in reasons


def test_fixed_price_below_budget_min_is_rejected():
    item = _make_item(category="家电", price=5, trade_type="FIXED_PRICE")
    need = _make_need(category="家电", budget_min=10)
    assert match_need(item, need) == []


def test_fixed_price_above_budget_max_is_rejected():
    item = _make_item(category="家电", price=25, trade_type="FIXED_PRICE")
    need = _make_need(category="家电", budget_max=20)
    assert match_need(item, need) == []


def test_negotiable_item_is_rejected_when_budget_present():
    item = _make_item(category="家电", trade_type="NEGOTIABLE")
    need = _make_need(category="家电", budget_min=10)
    assert match_need(item, need) == []


def test_keyword_match_adds_reason():
    item = _make_item(category="其他", title="九成新冰箱", description="")
    need = _make_need(category="家电", keywords=["冰箱"])
    reasons = match_need(item, need)
    assert "物品信息包含：冰箱" in reasons
