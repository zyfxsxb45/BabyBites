"""营养多样性规则。检查一周计划是否覆盖关键营养素。"""

from .base import RuleResult, make_suitable


def check_nutrient_coverage(
    weekly_plan: list[dict],
    age_months: int,
    kb=None,
) -> RuleResult:
    """
    检查周计划是否覆盖了当前阶段的关键营养素。

    Args:
        weekly_plan: [{day, food_id, food_data}, ...]
        age_months: 宝宝月龄

    Returns:
        suitable: 至少覆盖了关键营养素
        caution: 缺失某些关键营养素
    """
    if not kb:
        return make_suitable("营养覆盖", "无营养数据，跳过")

    stage = kb.get_age_stage(age_months)
    if not stage:
        return make_suitable("营养覆盖")

    key_nutrients = stage.get("key_nutrients", [])
    if not key_nutrients:
        return make_suitable("营养覆盖")

    # 统计计划中覆盖的营养素
    covered = set()
    for meal in weekly_plan:
        food = meal.get("food_data", {})
        for nutrient_name in key_nutrients:
            if nutrient_name in (food.get("nutrients") or {}):
                if food.get("nutrients", {}).get(nutrient_name, {}).get("value", 0) > 0:
                    covered.add(nutrient_name)

    missing = set(key_nutrients) - covered
    if missing:
        return RuleResult(
            tag="caution",
            reason=f"本周计划未覆盖关键营养素：{'、'.join(missing)}。"
                   f"建议补充富含这些营养素的食材。",
            rule_name="营养多样性检查",
            severity="warning",
            details={"covered": list(covered), "missing": list(missing)},
        )

    return make_suitable("营养覆盖", f"周计划覆盖全部关键营养素：{'、'.join(covered)}")

