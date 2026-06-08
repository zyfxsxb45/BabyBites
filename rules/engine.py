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
from kb.external_food import is_missing_value


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
        llm=None,
        strict_mode: bool = False,
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
                food, baby_profile.get("allergies", []), kb=self.kb, llm=llm,
            )
        )

        # 1.5. 外部食材特有检查：窒息风险（按年龄分级）
        if food.get("_is_choking_risk"):
            age = baby_profile.get("age_months", baby_profile.get("corrected_age_months", 6))
            if age < 12:
                results.append(RuleResult(
                    tag="avoid",
                    reason=f"{food.get('name_zh', '该食材')}是整颗圆形硬质食物，存在严重窒息风险，"
                           f"12月龄以内婴儿严格禁止",
                    rule_name="窒息风险拦截",
                    source="CDC窒息预防指南 / AAP安全喂养建议",
                    severity="error",
                ))
            else:
                results.append(RuleResult(
                    tag="caution",
                    reason=f"{food.get('name_zh', '该食材')}存在窒息风险（整颗圆形硬质食物），"
                           f"需切成小块或避免直接给整颗",
                    rule_name="窒息风险提示",
                    source="CDC窒息预防指南",
                    severity="warning",
                ))

        # 1.6. 外部食材特有检查：高钠
        sodium = food.get("_sodium_mg")
        if food.get("_contains_added_salt") or (sodium is not None and sodium > 200):
            results.append(RuleResult(
                tag="caution" if sodium and sodium <= 400 else "avoid",
                reason=f"{food.get('name_zh', '该食材')}含添加盐"
                       + (f"（钠含量 {sodium:.0f}mg/100g）" if sodium else "")
                       + "，1岁以下婴儿应避免额外摄入盐分",
                rule_name="添加盐/高钠拦截",
                source="WHO / CDC婴儿喂养指南",
                severity="warning" if sodium and sodium <= 400 else "error",
            ))

        # 1.7. 外部食材特有检查：添加糖
        if food.get("_contains_added_sugar"):
            results.append(RuleResult(
                tag="caution",
                reason=f"{food.get('name_zh', '该食材')}含添加糖，婴儿辅食不应额外加糖",
                rule_name="添加糖提示",
                source="WHO / CDC婴儿喂养指南",
                severity="warning",
            ))

        # 1.8. 外部食材特有检查：配料未知
        if food.get("_external") and food.get("category") == "unknown":
            ing_text = food.get("_ingredient_text", "")
            if is_missing_value(ing_text):
                results.append(RuleResult(
                    tag="caution",
                    reason=f"{food.get('name_zh', '该食材')}配料信息未知，无法评估过敏原和安全性，建议谨慎处理",
                    rule_name="配料信息不足",
                    source="CDC指南",
                    severity="warning",
                ))

        # 2. 月龄适龄
        results.append(
            check_age_appropriate(
                food, baby_profile.get("age_months", 0), kb=self.kb, strict_mode=strict_mode,
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

        # 6. 直接食材名匹配：过敏原列表可能直接包含食材名（如"山药"、"虾仁"）
        #    这是自定义过敏原的兜底——不依赖过敏原 ID 解析，直接按名称匹配
        allergy_set = set(baby_profile.get("allergies", []))
        if allergy_set:
            food_name = food.get("name_zh", "")
            food_aliases = set(
                food.get("aliases", [])
                if isinstance(food.get("aliases"), list)
                else []
            )
            food_aliases.add(food_name)
            if food_aliases & allergy_set:
                matched = list(food_aliases & allergy_set)
                results.append(
                    RuleResult(
                        tag="avoid",
                        reason=f"家长标注「{'、'.join(matched)}」为过敏原，自动排除",
                        rule_name="直接食材名过敏匹配",
                        source="用户标注",
                        severity="error",
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
