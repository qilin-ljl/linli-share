"""Three disposal-speed pricing strategies, with an explicit demo fallback."""

import json
from statistics import median
from typing import Callable


GOAL_LABELS = {"FAST": "尽快处理", "BALANCED": "均衡推荐", "PRICE_FIRST": "价格优先"}
OPTION_REASONS = {
    "quick": "价格更低，适合希望尽快流转的情况。",
    "balanced": "兼顾价格和等待时间。",
    "price_first": "价格更高，可能需要等待更长时间。",
}


def _with_explanations(result: dict, *, condition: str, disposal_goal: str,
                       original_price: int | None, comparables: list[dict], model_result: dict | None = None,
                       condition_source: str = "发布者标注成色") -> dict:
    model_result = model_result or {}
    def option(name: str, price: int) -> dict:
        candidate = model_result.get(f"{name}_reason")
        reason = candidate.strip() if isinstance(candidate, str) and 4 <= len(candidate) <= 140 else OPTION_REASONS[name]
        return {"price": price, "reason": reason}

    factors = [f"{condition_source}：{condition}", f"处理目标：{GOAL_LABELS[disposal_goal]}"]
    if original_price is not None:
        factors.append(f"发布者填写购入原价：¥{original_price}")
    if comparables:
        factors.append(f"参考同社区 {len(comparables)} 件同类物品的历史标价（非成交价）")
    else:
        factors.append("暂无同社区同类物品的历史标价")
    factors.append("社区内部约定地点自提，无需快递")
    result["options"] = {
        "quick": option("quick", result["quick_price"]),
        "balanced": option("balanced", result["balanced_price"]),
        "price_first": option("price_first", result["price_first"]),
    }
    result["factors"] = factors
    return result


def pricing_suggestion(
    *, title: str, description: str, condition: str, disposal_goal: str,
    category: str, original_price: int | None, comparables: list[dict],
    invoke_json: Callable[[str, str], dict], condition_source: str = "发布者标注成色",
) -> dict:
    system = (
        "你是小区闲置流转助手，不是专业估价师。价格单位为人民币元。"
        "提供三种流转策略：快速流转、均衡推荐、价格优先，必须满足 quick_price <= balanced_price <= price_first。"
        "社区历史数据只有发布者标价，不是已核实成交价；不要声称知道市场真实成交价。"
        "如果资料不足，请在 reason 中说明不确定性。"
        '只输出JSON对象：{"quick_price":30,"balanced_price":50,"price_first":70,'
        '"recommended_mode":"BALANCED","reason":"...","quick_reason":"...",'
        '"balanced_reason":"...","price_first_reason":"..."}。每档理由简短，不编造物品事实。'
    )
    request = (
        f"物品：{title}\n描述：{description}\n成色：{condition}\n类别：{category}"
        f"\n希望处理的速度目标：{disposal_goal}\n购入原价：{original_price}"
        f"\n同社区同类别物品的历史标价：{json.dumps(comparables, ensure_ascii=False)}\n请输出JSON。"
    )
    try:
        result = invoke_json(system, request)
        quick, balanced, high = (result.get(key) for key in ("quick_price", "balanced_price", "price_first"))
        reason = result.get("reason")
        if not all(type(value) is int for value in (quick, balanced, high)):
            raise ValueError("prices are not integers")
        if not 0 < quick <= balanced <= high <= 100000:
            raise ValueError("prices are out of order")
        if not isinstance(reason, str) or not 5 <= len(reason) <= 500:
            raise ValueError("invalid reason")
        return _with_explanations({"quick_price": quick, "balanced_price": balanced, "price_first": high,
                "recommended_mode": disposal_goal, "reason": reason.strip(), "source": "DEEPSEEK",
                "comparable_count": len(comparables)}, condition=condition, disposal_goal=disposal_goal,
                original_price=original_price, comparables=comparables, model_result=result,
                condition_source=condition_source)
    except Exception:
        # Explicitly labelled rule fallback keeps the publishing demo usable.
        prices = [entry["price"] for entry in comparables if type(entry.get("price")) is int]
        base = int(median(prices)) if prices else int((original_price or 120) * 0.3)
        factor = 0.9 if "八成" in condition or "有使用" in condition else 1.0
        balanced = max(5, round(base * factor / 5) * 5)
        quick = max(0, round(balanced * 0.7 / 5) * 5)
        high = max(balanced, round(balanced * 1.35 / 5) * 5)
        return _with_explanations({"quick_price": quick, "balanced_price": balanced, "price_first": high,
                "recommended_mode": disposal_goal,
                "reason": "演示规则参考：按同类历史标价或购入原价生成三档流转价格；请结合物品实际状况自行确认。",
                "source": "RULE_FALLBACK", "comparable_count": len(comparables)}, condition=condition,
                disposal_goal=disposal_goal, original_price=original_price, comparables=comparables,
                condition_source=condition_source)
