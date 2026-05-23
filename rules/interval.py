"""排敏间隔规则。确保新食材引入间隔满足观察期。"""

from datetime import date, timedelta
from .base import RuleResult, make_suitable
from config.settings import INTERVAL_DAYS_NEW_FOOD, MAX_NEW_FOODS_PER_WEEK


def check_new_food_interval(
    food: dict,
    feeding_history: list[dict],
    plan_date: date,
    kb=None,
) -> RuleResult:
    """
    检查计划中的某一日是否能安排新食材。

    规则：
    - 同一日只引入一种新食材
    - 上次新食材后需要等待 INTERVAL_DAYS_NEW_FOOD 天
    - 每周新食材不超过 MAX_NEW_FOODS_PER_WEEK 种
    """
    food_name = food.get("name_zh", "")

    if not feeding_history:
        return make_suitable("排敏间隔", "无历史记录，可以引入")

    # 按日期排序历史
    sorted_history = sorted(
        feeding_history,
        key=lambda x: x.get("date", date.today()),
    )

    # 找上次引入新食材的日期
    last_new_date = None
    week_new_count = 0
    plan_week_start = plan_date - timedelta(days=plan_date.weekday())

    for entry in sorted_history:
        entry_date = entry.get("date")
        if entry.get("is_new_food"):
            last_new_date = entry_date
            if entry_date and entry_date >= plan_week_start:
                week_new_count += 1

    # 检查间隔
    if last_new_date and (plan_date - last_new_date).days < INTERVAL_DAYS_NEW_FOOD:
        days_left = INTERVAL_DAYS_NEW_FOOD - (plan_date - last_new_date).days
        return RuleResult(
            tag="caution",
            reason=f"上次引入新食材仅过去{(plan_date - last_new_date).days}天，"
                   f"建议再等{days_left}天再引入{food_name}",
            rule_name="排敏间隔",
            severity="warning",
        )

    # 检查每周数量
    if week_new_count >= MAX_NEW_FOODS_PER_WEEK:
        return RuleResult(
            tag="caution",
            reason=f"本周已引入{week_new_count}种新食材（上限{MAX_NEW_FOODS_PER_WEEK}种），"
                   f"建议下周再引入{food_name}",
            rule_name="每周新食材上限",
            severity="warning",
        )

    return make_suitable("排敏间隔")
