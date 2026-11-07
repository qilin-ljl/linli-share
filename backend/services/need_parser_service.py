"""Parse a neighbor's explicit request, with an honestly labelled rules fallback."""

import re
from typing import Callable


CATEGORY_TERMS = {
    "家电": ["电磁炉", "电饭锅", "电饭煲", "微波炉", "冰箱", "洗衣机", "热水壶"],
    "家居": ["台灯", "书架", "椅子", "沙发", "桌子", "床头柜"],
    "图书": ["书", "教材", "考研", "资料"],
    "绿植": ["绿萝", "多肉", "花盆", "植物"],
    "运动": ["自行车", "瑜伽", "球拍", "哑铃"],
    "母婴": ["婴儿", "推车", "儿童", "积木"],
    "数码": ["电脑", "显示器", "键盘", "手机"],
}


def category_from_terms(raw_text: str) -> tuple[str | None, list[str]]:
    matches = [(category, [term for term in terms if term in raw_text])
               for category, terms in CATEGORY_TERMS.items()]
    category, keywords = max(matches, key=lambda pair: len(pair[1]))
    if keywords:
        return category, keywords[:8]
    named = next((name for name in CATEGORY_TERMS if name in raw_text), None)
    return named, []


def explicit_budget_max(raw_text: str) -> int | None:
    budget = re.search(r"(\d{1,6})\s*(?:元|块)\s*(?:以内|以下|之内|内|左右)", raw_text)
    if not budget:
        budget = re.search(r"(?:预算|不超过|最多)\s*(\d{1,6})", raw_text)
    return int(budget.group(1)) if budget else None


def with_guidance(result: dict, raw_text: str) -> dict:
    if result["category"] or result["keywords"]:
        return {**result, "needs_clarification": False,
                "message": "已按文字中的物品线索整理草稿，请核对后发布。", "next_action": None,
                "inferred": False, "suggestions": [{"category": result["category"],
                    "keywords": result["keywords"], "budget_min": result["budget_min"],
                    "budget_max": result["budget_max"], "reason": "来自你明确提到的物品", "inferred": False}]}
    wants_to_browse = any(phrase in raw_text for phrase in ("看看", "逛逛", "有什么", "都可以", "能用的"))
    return {**result, "needs_clarification": True,
            "message": ("你似乎想先看看附近有哪些好物。可以去市集浏览；如果要发布需求，请补充具体物品或类别。"
                        if wants_to_browse else "还没有找到具体物品线索。请补充想找的物品或类别，例如台灯、绿萝或图书。"),
            "next_action": "BROWSE" if wants_to_browse else "CLARIFY",
            "inferred": False, "suggestions": []}


def parse_need(raw_text: str, invoke_json: Callable[[str, str], dict] | None = None) -> dict:
    if invoke_json:
        try:
            data = invoke_json(
                "你是社区闲置需求助手。用户可以随意描述处境、用途或愿望。"
                "从原话推测最多3种可能想找的具体物品；即使没有明确物品，也可以根据场景给出合理候选，"
                "但每条必须标明 inferred=true 和推测理由，绝不能把推测说成用户确定的需求。"
                "如果用户明确提到了物品，优先整理明确需求并设 inferred=false。"
                "预算、品牌、型号、功能状态不得凭空编造；未明确写出的预算填 null。"
                '只输出JSON对象，格式：{"suggestions":[{"category":"家居","keywords":["台灯"],'
                '"budget_min":null,"budget_max":null,"reason":"刚搬家可能需要照明","inferred":true}]}。'
                "示例只是格式，不要照抄示例结论。",
                raw_text,
            )
            if data.get("type") == "json_object" and isinstance(data.get("content"), dict):
                data = data["content"]
            entries = data.get("suggestions") if isinstance(data.get("suggestions"), list) else [data]
            explicit_category, explicit_keywords = category_from_terms(raw_text)
            budget_max = explicit_budget_max(raw_text)
            suggestions = []
            for entry in entries[:3]:
                if not isinstance(entry, dict):
                    continue
                category = entry.get("category") if isinstance(entry.get("category"), str) else None
                category = category.strip()[:30] if category and category.strip() else None
                keywords = entry.get("keywords") if isinstance(entry.get("keywords"), list) else []
                keywords = [word.strip() for word in keywords if isinstance(word, str)
                            and 1 < len(word.strip()) <= 30][:8]
                if not category and not keywords:
                    continue
                grounded = bool((category and category in raw_text) or any(word in raw_text for word in keywords))
                inferred = bool(entry.get("inferred")) or not grounded
                reason = entry.get("reason") if isinstance(entry.get("reason"), str) else ""
                suggestions.append({"category": category or explicit_category,
                                    "keywords": keywords or explicit_keywords,
                                    "budget_min": None, "budget_max": budget_max,
                                    "reason": reason.strip()[:120] or ("根据你的描述推测，发布前请确认" if inferred else "来自你明确提到的物品"),
                                    "inferred": inferred})
            if not suggestions:
                raise ValueError("no usable suggestions")
            first = suggestions[0]
            return {"category": first["category"], "keywords": first["keywords"],
                    "budget_min": first["budget_min"], "budget_max": first["budget_max"],
                    "source": "DEEPSEEK", "inferred": first["inferred"], "suggestions": suggestions,
                    "needs_clarification": False,
                    "message": ("AI 根据你的描述推测了几种可能需要的物品。请选择或修改后再发布；未提到的预算不会代填。"
                                if any(item["inferred"] for item in suggestions)
                                else "AI 已整理出你明确提到的物品，请核对后发布。"),
                    "next_action": None}
        except Exception:
            pass
    category, keywords = category_from_terms(raw_text)
    return with_guidance({"category": category, "keywords": keywords[:8], "budget_min": None,
                          "budget_max": explicit_budget_max(raw_text),
                          "source": "RULE_FALLBACK"}, raw_text)
