"""成本-营养性价比排序规则。非安全规则，用于计划优化。"""

from .base import RuleResult, make_suitable


def score_cost_nutrient_ratio(
    candidate_foods: list[dict],
    target_nutrient: str = "铁",
) -> list[dict]:
    """
    按 营养素含量/价格 比率对候选食材排序。

    这不是一个"通过/不通过"规则，而是给计划生成智能体提供排序依据。
    返回带排序分数的食材列表。

    Args:
        candidate_foods: 食材列表
        target_nutrient: 目标营养素（默认铁）

    Returns:
        按性价比降序排列的食材列表，每项附加 score 字段
    """
    scored = []
    for food in candidate_foods:
        nutrients = food.get("nutrients", {})
        nutrient_data = nutrients.get(target_nutrient, {})
        nutrient_value = nutrient_data.get("value", 0)

        price = food.get("price_per_100g")

        if price and price > 0 and nutrient_value > 0:
            score = nutrient_value / price
        else:
            score = nutrient_value  # 无价格数据时只看营养

        scored.append({**food, "_score": score, "_scored_by": target_nutrient})

    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored
