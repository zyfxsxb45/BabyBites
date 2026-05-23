"""
阶段与安全边界智能体。

职责：判断宝宝是否进入辅食阶段，执行硬性安全拦截。
纯规则，无 LLM 参与——这是安全底线。

输入：宝宝画像
输出：阶段评估 + 安全拦截结果
"""

from .base import RuleAgent
from rules.engine import RuleEngine


class SafetyBoundaryAgent(RuleAgent):
    """阶段判断 + 安全拦截"""

    def __init__(self, kb=None, rule_engine=None):
        if rule_engine is None and kb is not None:
            rule_engine = RuleEngine(kb)
        super().__init__(kb=kb, rule_engine=rule_engine)

    def process(self, input_data: dict, **kwargs) -> dict:
        """
        执行阶段判断和安全拦截。

        Args:
            input_data:
                {
                    profile: {age_months, allergies, ...},
                    candidate_foods: [{...}, ...]  (可选)
                }

        Returns:
            {
                can_start: bool,
                stage: dict | None,
                readiness_signals: list[str],
                blocking_reasons: list[str],
                food_safety_results: {food_id: RuleOutput}  (如果有候选食材)
            }
        """
        profile = input_data.get("profile", {})
        age_months = profile.get("age_months", 0)

        # 1. 阶段判断
        can_start = self._check_readiness(profile)

        # 2. 获取当前阶段
        stage = self.kb.get_age_stage(age_months) if self.kb else None

        # 3. 对候选食材打安全标签
        food_results = {}
        candidate_foods = input_data.get("candidate_foods", [])
        for food in candidate_foods:
            result = self.rule_engine.evaluate_food(food, profile)
            food_results[food.get("id", food.get("name_zh", ""))] = {
                "tag": result.overall_tag,
                "reasons": result.reasons,
                "details": [r.__dict__ for r in result.results],
            }

        return {
            "can_start": can_start,
            "stage": stage,
            "age_months": age_months,
            "readiness_signals": self._get_readiness_signals(profile),
            "blocking_reasons": self._get_blocking_reasons(profile),
            "food_safety_results": food_results,
        }

    def _check_readiness(self, profile: dict) -> bool:
        """检查是否具备辅食条件"""
        age = profile.get("age_months", 0)
        # 矫正月龄优先
        corrected = profile.get("corrected_age_months")
        effective_age = corrected if corrected is not None else age

        if effective_age < 6:
            return False
        return True

    def _get_readiness_signals(self, profile: dict) -> list[str]:
        """收集发育就绪信号"""
        # TODO: 根据用户输入提取更丰富的信号
        return []

    def _get_blocking_reasons(self, profile: dict) -> list[str]:
        """收集不能开始辅食的原因"""
        reasons = []
        corrected = profile.get("corrected_age_months")
        age = profile.get("age_months", 0)
        effective_age = corrected if corrected is not None else age

        if effective_age < 4:
            reasons.append("宝宝月龄不足4个月，绝对不能开始辅食")
        elif effective_age < 6:
            reasons.append(
                f"宝宝月龄{effective_age}个月，"
                f"建议满6个月后再开始辅食。如有特殊需要请咨询儿科医生。"
            )
        return reasons
