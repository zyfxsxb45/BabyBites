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
    if food_texture == expected:
        return make_suitable("质地匹配", f"{food_name}质地匹配{expected}")

    # 食物质地允许降级（更细腻可以）
    # 但不允许升级（太粗不适合）
    order = {"puree": 0, "minced": 1, "chunky": 2}
    if order.get(food_texture, 99) < order.get(expected, 99):
        return make_suitable("质地匹配",
            f"{food_name}质地({food_texture})适合，"
            f"如需要可制备成{expected}")

    return RuleResult(
        tag="caution",
        reason=f"{food_name}的质地({food_texture})可能需要进一步处理"
               f"以适合{expected}阶段",
        rule_name="质地检查",
        severity="warning",
    )
