"""
反馈规则模块。

将用户反馈转换为推荐调整：
  - 有 moderate/severe 反应的食材 → avoid
  - 有 mild 反应的食材 → caution + 延长观察期
  - 同类/交叉过敏食材 → caution
  - 对某食材反馈"没问题" → 标记为 safe，降低观察期
"""

from .base import RuleResult, make_suitable


def apply_feedback_to_food(food: dict, feedback_store, kb=None) -> RuleResult:
    """
    根据用户反馈历史，调整食材的安全标签。

    Args:
        food: 食材数据
        feedback_store: FeedbackStore 实例
        kb: 知识库（用于查交叉过敏）

    Returns:
        RuleResult with adjusted tag
    """
    food_name = food.get("name_zh", "")
    if not food_name:
        return make_suitable("反馈规则")

    label = feedback_store.get_food_safety_label(food_name)

    if label == "avoid":
        records = feedback_store.get_by_food(food_name)
        latest = records[-1] if records else {}
        return RuleResult(
            tag="avoid",
            reason=f"「{food_name}」宝宝之前有过{latest.get('severity', '')}反应"
                   f"（{latest.get('reaction', '')}），建议暂时避免。",
            rule_name="反馈历史·避免",
            severity="error",
        )

    if label == "caution":
        records = feedback_store.get_by_food(food_name)
        latest = records[-1] if records else {}
        return RuleResult(
            tag="caution",
            reason=f"「{food_name}」宝宝之前有过轻微反应"
                   f"（{latest.get('reaction', '')}），建议观察更长时间。",
            rule_name="反馈历史·注意",
            severity="warning",
        )

    # 检查是否有"没问题"反馈 → 可以放宽
    records = feedback_store.get_by_food(food_name)
    if records and all(r.get("reaction") == "none" for r in records):
        return RuleResult(
            tag="suitable",
            reason=f"「{food_name}」之前尝试过，没有不良反应。",
            rule_name="反馈历史·安全",
            severity="info",
        )

    return make_suitable("反馈规则")


def check_cross_category_caution(food: dict, feedback_store, kb=None) -> RuleResult:
    """
    检查食材类别中是否有其他食材有过不良反应。
    如"猪肝"没问题但"鸡肝"有反应 → 同类食材提示 caution
    """
    food_name = food.get("name_zh", "")
    food_cat = food.get("category", "")

    if not food_cat or not kb:
        return make_suitable("交叉类别检查")

    # 找同类别中有过不良反应的食材
    avoid_foods = feedback_store.get_avoid_foods()
    caution_foods = feedback_store.get_caution_foods()

    # 查同类别食材
    same_cat_foods = kb.list_foods_by_category(food_cat) if kb else []
    same_cat_names = {f.get("name_zh", "") for f in same_cat_foods}

    problem_in_category = (avoid_foods | caution_foods) & same_cat_names
    problem_in_category.discard(food_name)  # 去掉自己

    if problem_in_category:
        return RuleResult(
            tag="caution",
            reason=f"同类食材中{'、'.join(list(problem_in_category)[:3])}有过不良反应，"
                   f"建议对「{food_name}」多加观察。",
            rule_name="交叉类别提示",
            severity="warning",
        )

    return make_suitable("交叉类别检查")


def get_feedback_adjusted_foods(
    foods: list[dict],
    feedback_store,
    kb=None,
) -> list[dict]:
    """
    根据反馈历史，为候选食材池打上调整后的标签。

    Returns:
        打了标签的食材列表 [{food_data, tag, reason}]
    """
    avoid_set = feedback_store.get_avoid_foods()
    caution_set = feedback_store.get_caution_foods()

    adjusted = []
    for item in foods:
        food_data = item.get("food_data", item)
        name = food_data.get("name_zh", "")

        entry = {"food_data": food_data}

        if name in avoid_set:
            entry["tag"] = "avoid"
            entry["reason"] = "宝宝之前有过不良反应"
        elif name in caution_set:
            entry["tag"] = "caution"
            entry["reason"] = "宝宝之前有过轻微反应"
        else:
            entry["tag"] = item.get("tag", "suitable")
            entry["reason"] = ""

        adjusted.append(entry)

    return adjusted
