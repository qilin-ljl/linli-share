"""Vision provider adapter. Describes visible evidence only; pricing stays separate."""

import base64
import json
import os
from io import BytesIO

from openai import OpenAI
from PIL import Image, ImageOps


def _prepared_image(data: bytes) -> tuple[bytes, str]:
    with Image.open(BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2048, 2048))
        output = BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=84, optimize=True)
        return output.getvalue(), "image/jpeg"


def _vision_json(prompt: str, images: list[tuple[bytes, str]]) -> dict:
    key = os.getenv("VISION_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv("VISION_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    if not key or not model:
        raise RuntimeError("Vision API is not configured")
    client = OpenAI(api_key=key, base_url=os.getenv("VISION_BASE_URL") or "https://api.deepseek.com",
                    timeout=40.0, max_retries=0)
    content = [{"type": "text", "text": prompt}]
    for image, mime_type in images:
        image, mime_type = _prepared_image(image)
        url = f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"
        content.append({"type": "image_url", "image_url": {"url": url}})
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"}, max_tokens=min(8000, 1500 + len(images) * 350),
        **({"extra_body": {"thinking": {"type": "disabled"}}}
           if "api.deepseek.com" in str(client.base_url) else {}),
    )
    text = response.choices[0].message.content
    if not text:
        raise ValueError("empty vision response")
    data = json.loads(text)
    if isinstance(data, dict) and data.get("type") == "json_object" and isinstance(data.get("content"), dict):
        return data["content"]
    return data


def _visible_analysis(raw: dict) -> dict:
    condition = raw.get("condition") if raw.get("condition") in {"NEW", "GOOD", "FAIR", "WORN", "UNKNOWN"} else "UNKNOWN"
    score = raw.get("condition_score")
    score = score if type(score) is int and 1 <= score <= 5 else None
    def strings(key: str) -> list[str]:
        value = raw.get(key)
        return [entry.strip()[:100] for entry in value if isinstance(entry, str) and entry.strip()][:8] if isinstance(value, list) else []
    def short(key: str) -> str | None:
        value = raw.get(key)
        return value.strip()[:60] if isinstance(value, str) and value.strip() else None
    category = short("category")
    category = {"家居照明": "家居", "厨房电器": "家电", "厨房家电": "家电",
                "厨房小家电": "家电", "盆栽": "绿植"}.get(category, category)
    return {"product_type": short("product_type"), "category": category,
            "brand": short("brand"), "model": short("model"), "condition": condition,
            "condition_score": score, "visible_defects": strings("visible_defects"),
            "visible_accessories": strings("visible_accessories"), "unknowns": strings("unknowns")}


def analyze_item(images: list[tuple[bytes, str]]) -> dict:
    prompt = (
        "观察这些照片，它们属于同一件物品。只报告照片可见的事实，用中文返回 JSON 对象："
        "product_type, category, brand, model, condition(NEW/GOOD/FAIR/WORN/UNKNOWN),"
        "condition_score(1-5或null), visible_defects 数组, visible_accessories 数组, unknowns 数组。"
        "看不出的品牌型号、购买年份、原价、功能状态、维修历史和隐藏损坏必须放入 unknowns，绝不能猜测。"
        "不要给价格、置信度或百分比。示例 JSON 输出："
        '{"product_type":"台灯","category":"家居","brand":null,"model":null,'
        '"condition":"GOOD","condition_score":4,"visible_defects":["灯罩轻微划痕"],'
        '"visible_accessories":["电源线"],"unknowns":["功能状态","购买年份","原价","隐藏故障"]}。'
        "示例只是格式，不得把示例内容当作照片事实。"
    )
    try:
        analysis = _visible_analysis(_vision_json(prompt, images))
        if not analysis["product_type"]:
            raise ValueError("missing product type")
        return {**analysis, "source": "VISION_API"}
    except Exception:
        return {"product_type": None, "category": None, "brand": None, "model": None,
                "condition": "UNKNOWN", "condition_score": None,
                "visible_defects": [], "visible_accessories": [],
                "unknowns": ["物品类型", "外观成色", "品牌型号", "功能状态", "购买年份", "原价", "隐藏损坏"],
                "source": "MANUAL_REVIEW_REQUIRED"}


def analyze_batch(images: list[tuple[bytes, str]]) -> dict:
    prompt = (
        "观察这些照片，判断其中可见的独立物品。照片按输入顺序从 0 编号。"
        "只基于可见事实返回 JSON 对象 {items:[{photo_indices:[0],product_type,category,brand,model,"
        "condition,condition_score,visible_defects,visible_accessories,unknowns}]}。"
        "condition 只能是 NEW/GOOD/FAIR/WORN/UNKNOWN。不同照片若是同一物品，合并 photo_indices。"
        "每张照片只识别最主要的一件待流转物品。不要把背景中的花瓶、绿植、笔、书、窗帘、地毯等陪衬单独列为待发布物品，"
        "除非该照片明显以它为主角。若多张照片是同一物品，可合并。"
        "不确定时单独列出并将事实放入 unknowns；不要编造功能、购买时间、原价、隐藏损坏。"
        "不要给价格或置信度。示例 JSON 输出："
        '{"items":[{"photo_indices":[0],"product_type":"台灯","category":"家居",'
        '"brand":null,"model":null,"condition":"GOOD","condition_score":4,'
        '"visible_defects":[],"visible_accessories":["电源线"],"unknowns":["功能状态"]}]}。'
        "示例只表示格式，不得照抄示例作为识别结论。"
    )
    try:
        raw = _vision_json(prompt, images)
        entries = raw.get("items")
        if not isinstance(entries, list) or not entries:
            raise ValueError("no items")
        results = []
        claimed: set[int] = set()
        for entry in entries[:20]:
            if not isinstance(entry, dict):
                continue
            indices = entry.get("photo_indices")
            indices = [index for index in indices if type(index) is int and 0 <= index < len(images)] if isinstance(indices, list) else []
            new_indices = [index for index in indices if index not in claimed]
            if new_indices:
                results.append({**_visible_analysis(entry), "photo_indices": list(dict.fromkeys(new_indices))})
                claimed.update(new_indices)
        if not results:
            raise ValueError("no valid items")
        for index in range(len(images)):
            if index not in claimed:
                results.append({"photo_indices": [index], "product_type": None, "category": None,
                                "brand": None, "model": None, "condition": "UNKNOWN",
                                "condition_score": None, "visible_defects": [], "visible_accessories": [],
                                "unknowns": ["物品类型", "成色", "功能状态"]})
        return {"items": results, "source": "VISION_API"}
    except Exception:
        return {"items": [{"photo_indices": [index], "product_type": None, "category": None,
                           "brand": None, "model": None, "condition": "UNKNOWN", "condition_score": None,
                           "visible_defects": [], "visible_accessories": [],
                           "unknowns": ["物品类型", "成色", "功能状态"]}
                          for index in range(len(images))], "source": "MANUAL_REVIEW_REQUIRED"}
