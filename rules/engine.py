"""
规则引擎调度器。

负责编排所有规则模块，对单个食材或计划执行完整的安全检查。
支持两类调度模式：
  1. 单食材模式：对候选食材执行全部规则 → 输出标签
  2. 计划模式：对整个周计划执行校验 → 输出违纪列表
"""

from typing import Optional
from .base import RuleResult, RuleOutput
from .allergen import check_known_allergy
from .age import check_age_appropriate, check_strictly_avoided
from .texture import check_texture_match
from .interval import check_new_food_interval
from .nutrition import check_nutrient_coverage


class RuleEngine:
    """规则引擎调度器。

    用法：
        engine = RuleEngine(kb)
        result = engine.evaluate_food(food, baby_profile)
        if result.overall_tag == "avoid":
            # 食材不可用
    """

    def __init__(self, kb=None):
        self.kb = kb

    def evaluate_food(
        self,
        food: dict,
        baby_profile: dict,
        plan_date: Optional["date"] = None,
    ) -> RuleOutput:
        """
        对单个食材执行全部单食材规则。

        Args:
            food: 食材数据（来自 foods.json 或 kb.get_food()）
            baby_profile: 宝宝画像
                {
                    age_months: int,
                    allergies: list[str],      # 过敏原 ID 列表
                    feeding_history: list,     # [{date, food_id, is_new_food}, ...]
                }
            plan_date: 计划日期（用于排敏间隔计算，可选）

        Returns:
            RuleOutput: 包含每条规则的结果和综合标签
        """
        results: list[RuleResult] = []

        # 1. 已知过敏原 —— 最高优先级
        results.append(
            check_known_allergy(
                food, baby_profile.get("allergies", []), kb=self.kb,
            )
        )

        # 2. 月龄适龄
        results.append(
            check_age_appropriate(
                food, baby_profile.get("age_months", 0), kb=self.kb,
            )
        )

        # 3. 严格禁止食物
        results.append(
            check_strictly_avoided(
                food, baby_profile.get("age_months", 0), kb=self.kb,
            )
        )

        # 4. 质地匹配
        results.append(
            check_texture_match(
                food, baby_profile.get("age_months", 0), kb=self.kb,
            )
        )

        # 5. 排敏间隔（只对计划中的某一天）
        if plan_date and baby_profile.get("feeding_history"):
            results.append(
                check_new_food_interval(
                    food, baby_profile["feeding_history"], plan_date, kb=self.kb,
                )
            )

        return RuleOutput(results=results)

    def validate_plan(
        self,
        weekly_plan: list[dict],
        baby_profile: dict,
    ) -> dict:
        """
        对整个周计划做校验（校验智能体的核心逻辑）。

        Args:
            weekly_plan: [{day, date, food_id, food_data}, ...]
            baby_profile: 宝宝画像

        Returns:
            {
                passed: bool,
                violations: [{day, food, rule, severity}, ...],
                warnings: [{...}],
            }
        """
        violations = []
        warnings = []

        for meal in weekly_plan:
            food = meal.get("food_data", {})
            plan_date = meal.get("date")

            # 单食材检查 — 每个规则函数用不同的参数
            food = meal.get("food_data", {})
            plan_date = meal.get("date")
            age_months = baby_profile.get("age_months", 6)
            allergies = baby_profile.get("allergies", [])

            # 过敏拦截
            result = check_known_allergy(food, allergies, kb=self.kb)
            if result.tag == "avoid":
                violations.append({
                    "day": meal.get("day"),
                    "food": food.get("name_zh"),
                    "rule": result.rule_name,
                    "severity": "error",
                    "reason": result.reason,
                })
            elif result.tag == "caution":
                warnings.append({
                    "day": meal.get("day"),
                    "food": food.get("name_zh"),
                    "rule": result.rule_name,
                    "reason": result.reason,
                })

            # 月龄适龄
            result = check_age_appropriate(food, age_months, kb=self.kb)
            if result.tag == "avoid":
                violations.append({
                    "day": meal.get("day"),
                    "food": food.get("name_zh"),
                    "rule": result.rule_name,
                    "severity": "error",
                    "reason": result.reason,
                })
            elif result.tag == "caution":
                warnings.append({
                    "day": meal.get("day"),
                    "food": food.get("name_zh"),
                    "rule": result.rule_name,
                    "reason": result.reason,
                })

            # 严格禁止
            result = check_strictly_avoided(food, age_months, kb=self.kb)
            if result.tag == "avoid":
                violations.append({
                    "day": meal.get("day"),
                    "food": food.get("name_zh"),
                    "rule": result.rule_name,
                    "severity": "error",
                    "reason": result.reason,
                })
            elif result.tag == "caution":
                warnings.append({
                    "day": meal.get("day"),
                    "food": food.get("name_zh"),
                    "rule": result.rule_name,
                    "reason": result.reason,
                })

        # 营养覆盖检查
        nutrient_result = check_nutrient_coverage(
            weekly_plan, baby_profile.get("age_months", 6), kb=self.kb,
        )
        if nutrient_result.tag == "caution":
            warnings.append({
                "day": "整体",
                "food": "",
                "rule": nutrient_result.rule_name,
                "reason": nutrient_result.reason,
            })

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
        }
