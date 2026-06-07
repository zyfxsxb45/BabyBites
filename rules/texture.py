"""质地匹配规则。"""

from .base import RuleResult, make_suitable


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

    # 英文 → 中文纹理映射
    TEXTURE_EN_TO_ZH = {
        "puree": "泥糊状",
        "mashed": "碎末状",
        "soft": "软烂",
        "finger_food": "手指食物",
        "liquid": "液体",
        "hard_round": "硬圆形",
        "unknown": "未知",
        "smooth_mixed": "泥糊状",
        "soft_lumps": "碎末状",
    }
    food_texture_zh = TEXTURE_EN_TO_ZH.get(food_texture, food_texture)

    # 中文 → 难度等级映射
    TEXTURE_LEVEL = {
        "泥糊状": 0, "液体": 0, "软烂": 1, "碎末状": 1,
        "手指食物": 2, "小块/家庭饮食": 3, "硬圆形": 3, "未知": -1,
    }
    expected_level = TEXTURE_LEVEL.get(
        _pick_first_texture(expected), -1
    )
    food_level = TEXTURE_LEVEL.get(food_texture_zh, 99)

    # 未知纹理 → 放行（可能是外部食材，纹理不明确不应作为硬阻）
    if food_texture == "unknown" or food_texture_zh == "未知":
        return make_suitable(
            "质地匹配",
            f"{food_name}纹理未知，不做质地限制"
        )

    # 硬圆形 / 整颗食物 → 特殊警告
    if food_texture == "hard_round":
        if age_months < 12:
            return RuleResult(
                tag="avoid",
                reason=f"{food_name}在咀嚼期(9-11月龄)阶段禁止食用。",
                rule_name="质地检查",
                source="CDC窒息预防指南",
                severity="error",
            )
        return RuleResult(
            tag="caution",
            reason=f"{food_name}的质地({food_texture_zh})可能需要切碎处理以适合{expected}阶段",
            rule_name="质地检查",
            severity="warning",
        )

    # 匹配：允许降级（更细腻可以），不允许升级
    if expected_level < 0:
        return make_suitable("质地匹配")
    if food_level <= expected_level:
        return make_suitable(
            "质地匹配",
            f"{food_name}质地({food_texture_zh})适合{expected}阶段"
        )

    return RuleResult(
        tag="caution",
        reason=f"{food_name}的质地({food_texture_zh})可能需要进一步处理"
               f"以适合{expected}阶段",
        rule_name="质地检查",
        severity="warning",
    )


def _pick_first_texture(texture_str: str) -> str:
    """从阶段纹理字符串中取第一个（如 '碎末状 / 指状食物' → '碎末状'）"""
    return texture_str.split("/")[0].strip()
