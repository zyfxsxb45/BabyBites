"""质地匹配规则。

统一 canonical 三级质地：puree(0) < minced(1) < chunky(2)
所有中英文值归一化到这三层后，再与阶段期望比较。
更细腻可以通过，更粗糙需要 caution。
"""

from .base import RuleResult, make_suitable

# ===== 统一 canonical 质地映射 =====
# puree(0): 泥糊状、液体、糊状、酸奶状
CANONICAL_PUREE = {
    "泥糊状", "puree", "mashed", "soft", "liquid",
    "smooth_mixed",
}
# minced(1): 碎末状、指状食物、软颗粒
CANONICAL_MINCED = {
    "碎末状", "指状食物", "minced", "soft_lumps",
    "finger_food",
}
# chunky(2): 小块、家庭饮食、硬圆形
CANONICAL_CHUNKY = {
    "小块/家庭饮食", "chunky", "hard_round",
}

CANONICAL_LEVEL = {"puree": 0, "minced": 1, "chunky": 2}

CANONICAL_ZH = {"puree": "泥糊状", "minced": "碎末状", "chunky": "小块/家庭饮食"}


def _to_canonical(texture: str) -> tuple[str, int]:
    """将任意中英文纹理归一化为 canonical (name, level)"""
    if texture in CANONICAL_PUREE:
        return ("puree", 0)
    if texture in CANONICAL_MINCED:
        return ("minced", 1)
    if texture in CANONICAL_CHUNKY:
        return ("chunky", 2)
    return ("unknown", -1)


def _extract_stage_level(texture_str: str) -> int:
    """从阶段纹理字符串中提取 canonical level。
    如 '碎末状 / 指状食物' → 取第一部分 '碎末状' → minced(1)
    """
    first = texture_str.split("/")[0].strip()
    _, level = _to_canonical(first)
    return level


def check_texture_match(food: dict, age_months: int, kb=None) -> RuleResult:
    """检查食材质地是否匹配宝宝当前阶段"""
    food_texture = food.get("texture_stage", "unknown")
    food_name = food.get("name_zh", "未知食材")

    if not kb:
        return make_suitable("质地匹配")

    stage = kb.get_age_stage(age_months)
    if not stage:
        return make_suitable("质地匹配")

    expected = stage.get("texture", "")

    # 归一化食材纹理
    canonical_name, food_level = _to_canonical(food_texture)
    expected_level = _extract_stage_level(expected)
    canonical_zh = CANONICAL_ZH.get(canonical_name, food_texture)

    # 未知纹理 → 不触发规则（信息不足，不应误判）
    if canonical_name == "unknown":
        return make_suitable(
            "质地匹配",
            f"{food_name}纹理未知，不做质地限制"
        )

    # 硬圆形特殊处理：低于12月龄 → avoid
    if food_texture == "hard_round":
        if age_months < 12:
            return RuleResult(
                tag="avoid",
                reason=f"{food_name}是整颗硬质食物，存在严重窒息风险，12月龄以内禁止食用。",
                rule_name="质地检查",
                source="CDC窒息预防指南",
                severity="error",
            )
        return RuleResult(
            tag="caution",
            reason=f"{food_name}的质地({canonical_zh})需要切成小块以适合{expected}阶段",
            rule_name="质地检查",
            severity="warning",
        )

    # 阶段纹理未知 → 放行
    if expected_level < 0:
        return make_suitable("质地匹配")

    # 比较：更细腻可以通过，更粗糙需要 caution
    if food_level <= expected_level:
        return make_suitable(
            "质地匹配",
            f"{food_name}的质地({canonical_zh})适合{expected}阶段"
        )

    return RuleResult(
        tag="caution",
        reason=f"{food_name}的质地({canonical_zh})需要进一步处理以适合{expected}阶段",
        rule_name="质地检查",
        severity="warning",
    )
