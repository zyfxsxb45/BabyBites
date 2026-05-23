"""
校验智能体。

职责：二次验证生成的计划是否违反所有硬约束。
纯规则引擎，不受 LLM 影响。计划生成智能体的安全冗余层。

输入：周计划 + 宝宝画像
输出：{passed, violations, warnings}
"""

from .base import RuleAgent
from rules.engine import RuleEngine


class ValidationAgent(RuleAgent):
    """二次规则验证"""

    def __init__(self, kb=None, rule_engine=None):
        if rule_engine is None and kb is not None:
            rule_engine = RuleEngine(kb)
        super().__init__(kb=kb, rule_engine=rule_engine)

    def process(self, input_data: dict, **kwargs) -> dict:
        """
        对生成的周计划进行二次规则验证。

        Args:
            input_data:
                {
                    plan: [{day, date, foods: [str], ...}, ...],
                    profile: {age_months, allergies, ...},
                }

        Returns:
            {
                passed: bool,
                violations: [{day, food, rule, severity, reason}, ...],
                warnings: [{...}],
                action: 'approve' | 'reject_and_retry'
            }
        """
        plan = input_data.get("plan", [])
        profile = input_data.get("profile", {})

        # 展开计划为食材列表供规则引擎校验
        weekly_plan = []
        for day_plan in plan:
            for food_name in day_plan.get("foods", []):
                # 从 kb 中获取完整食材数据
                food_data = (
                    self.kb.get_food_by_name(food_name)
                    if self.kb else {}
                )
                from datetime import date as dt
                try:
                    plan_date = dt.fromisoformat(day_plan.get("date", ""))
                except (ValueError, TypeError):
                    plan_date = None

                weekly_plan.append({
                    "day": day_plan.get("day", ""),
                    "date": plan_date,
                    "food_id": food_data.get("id", "") if food_data else "",
                    "food_data": food_data or {"name_zh": food_name},
                })

        # 规则引擎校验
        result = self.rule_engine.validate_plan(weekly_plan, profile)

        # 决定是否通过
        action = "approve" if result["passed"] else "reject_and_retry"

        return {
            **result,
            "action": action,
            "message": (
                "✅ 计划通过所有安全校验"
                if result["passed"]
                else f"❌ 计划存在 {len(result['violations'])} 条违规，需重新生成"
            ),
        }
