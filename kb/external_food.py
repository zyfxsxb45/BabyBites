"""
外部食材包装器。

当候选食材无法映射到内置知识库时，使用此模块将外部结构化字段
（如评测数据中的 contains_added_salt / is_choking_risk_candidate 等）
转换为规则引擎可消费的内部格式。

核心原则：不丢弃数据。KB 没有的食材，只要有元数据字段就能做安全判断。
"""

import math
from typing import Any, Optional

# 外部过敏原字段 → 内部过敏原名称
_EXTERNAL_ALLERGEN_MAP = {
    "contains_milk": "牛奶",
    "contains_egg": "鸡蛋",
    "contains_wheat": "小麦",
    "contains_soy": "大豆",
    "contains_peanut": "花生",
    "contains_tree_nut": "坚果",
    "contains_fish": "鱼类",
    "contains_shellfish": "虾",
}


def external_food_to_internal(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    将外部候选食材的原始字段转换为规则引擎可消费的内部格式。

    Args:
        raw: 外部候选数据，至少包含 food_name 或 food_name_zh

    Returns:
        内部格式的 food dict，可用于 RuleEngine.evaluate_food()
        如果信息不足以做任何判断，返回 None
    """
    name_zh = raw.get("food_name_zh") or raw.get("food_name") or raw.get("name_zh") or ""
    name_en = raw.get("food_name") or raw.get("name_en") or ""
    if not name_zh and not name_en:
        return None

    # 收集过敏原
    allergens = []
    for ext_key, internal_name in _EXTERNAL_ALLERGEN_MAP.items():
        if raw.get(ext_key):
            allergens.append(internal_name)

    food = {
        "id": raw.get("food_id") or f"ext_{hash(name_zh or name_en) & 0xFFFFFFFF:08x}",
        "name_zh": name_zh,
        "name_en": name_en,
        "category": raw.get("food_category") or raw.get("category") or "unknown",
        "allergen": allergens[0] if len(allergens) == 1 else None,
        "potential_allergen": len(allergens) > 0,
        "min_age_months": _safe_int(raw.get("typical_age_min_month"), 6),
        "texture_stage": raw.get("texture_stage") or "unknown",
        "iron_rich": bool(raw.get("is_iron_rich")),
        "nutrients": {},
        "tags": [],
        "notes_zh": "",
        "source": "外部数据（未收录于内置知识库）",
        # 外部特有字段：供规则引擎直接消费
        "_external": True,
        "_contains_added_salt": bool(raw.get("contains_added_salt")),
        "_contains_added_sugar": bool(raw.get("contains_added_sugar")),
        "_is_choking_risk": bool(raw.get("is_choking_risk_candidate")),
        "_sodium_mg": _safe_float(raw.get("sodium_mg")),
        "_allergen_flags": {k: bool(raw.get(k)) for k in _EXTERNAL_ALLERGEN_MAP},
        "_ingredient_text": "" if is_missing_value(raw.get("ingredient_text")) else str(raw.get("ingredient_text")).strip(),
    }

    # 补铁含量（如果有的话）
    if raw.get("iron_mg") is not None:
        food["nutrients"]["铁"] = {"value": float(raw["iron_mg"]), "unit": "mg/100g"}

    if raw.get("protein_g") is not None:
        food["nutrients"]["蛋白质"] = {"value": float(raw["protein_g"]), "unit": "g/100g"}

    return food


def is_external_food(food: dict[str, Any]) -> bool:
    """判断食材是否来自外部（非内置知识库）"""
    return bool(food.get("_external"))


def is_missing_value(value: Any) -> bool:
    """Return True for None, NaN, blank strings, and common missing markers."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().lower() in {"", "nan", "none", "null"}


def resolve_food(food_raw: dict[str, Any], kb=None) -> Optional[dict[str, Any]]:
    """
    通用食材解析入口：先查 KB，查不到就用外部字段构造。

    Args:
        food_raw: 可能是 KB 内部的 food dict，也可能是外部候选原始数据
        kb: 知识库实例（可选）

    Returns:
        内部格式的 food dict，或 None
    """
    name = food_raw.get("name_zh") or food_raw.get("food_name_zh") or ""

    # 尝试 KB 映射
    if kb:
        kb_food = kb.get_food_by_name(name)
        if kb_food:
            return kb_food

        # 尝试英文名
        en = food_raw.get("name_en") or food_raw.get("food_name") or ""
        if en:
            for f in kb.list_all_foods():
                if f.get("name_en", "").lower() == en.lower():
                    return f

    # KB 没有 → 外部包装
    return external_food_to_internal(food_raw)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> Optional[float]:
    try:
        v = float(value)
        return v if v == v else None  # NaN → None
    except (TypeError, ValueError):
        return None
