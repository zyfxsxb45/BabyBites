"""
月龄适龄规则。

执行"宝宝月龄 < 食材最低月龄 → avoid"的可否决规则。
所有月龄数据来自 foods.json 的 min_age_months 字段。
"""

from .base import RuleResult, make_suitable


def check_age_appropriate(
    food: dict,
    age_months: int,
    kb=None,
) -> RuleResult:
    """
    检查食材是否适龄。

    6月龄以下不能吃任何辅食（由安全边界智能体统一拦截），
    此规则检查食材的内部月龄下限。

    Args:
        food: 食材数据
        age_months: 宝宝月龄

    Returns:
        avoid: 食材有明确的最低月龄要求且宝宝未达标
        suitable: 满足最低月龄要求
    """
    min_age = food.get("min_age_months")
    food_name = food.get("name_zh", "未知食材")

    if min_age is None:
        return make_suitable("月龄适龄", f"{food_name}无月龄限制")

    if age_months < min_age:
        return RuleResult(
            tag="avoid",
            reason=(f"{food_name}建议{min_age}月龄以后引入，"
                    f"当前宝宝{age_months}月龄尚不达标。"),
            rule_name="月龄适龄检查",
            source="CDC指南 / WHO补充喂养原则",
            severity="error",
        )

    return make_suitable("月龄适龄", f"{food_name}适龄({min_age}m+)")


def check_strictly_avoided(
    food: dict,
    age_months: int,
    kb=None,
) -> RuleResult:
    """
    检查是否为"严格禁止食物"。

    某些食物在任何情况下都不该给特定月龄的宝宝吃（如蜂蜜）。
    由 age_stages.json 中每个阶段的 strictly_avoid 列表驱动。

    Args:
        food: 食材数据
        age_months: 宝宝月龄

    Returns:
        avoid: 食材在该月龄段被严格禁止
        suitable: 不在禁止列表
    """
    if kb:
        stage = kb.get_age_stage(age_months)
        if stage:
            avoid_list = stage.get("strictly_avoid", [])
            food_name = food.get("name_zh", "")
            if food_name in avoid_list:
                return RuleResult(
                    tag="avoid",
                    reason=f"{food_name}在{stage.get('label', '')}"
                           f"({stage.get('age_range', '')})阶段禁止食用。",
                    rule_name="严格禁止食材检查",
                    source=stage.get("source", "CDC指南"),
                    severity="error",
                )

    return make_suitable("禁止食材检查")
