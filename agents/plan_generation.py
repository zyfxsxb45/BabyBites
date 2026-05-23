"""
计划生成与优化智能体。

职责：在安全候选食材池中做约束满足 + 多目标排序，生成周度计划。
混合模式：规则约束 + LLM 灵活排序和解释。

输入：候选食材池（已打标签）+ 宝宝画像
输出：周度喂食计划表
"""

from datetime import date, timedelta
from .base import LLMAgent
from rules.cost import score_cost_nutrient_ratio


class PlanGenerationAgent(LLMAgent):
    """生成周度辅食计划"""

    SYSTEM_PROMPT = """你是一个婴儿辅食计划生成助手。
根据提供的安全食材列表和宝宝信息，生成一周的辅食计划。

规则：
1. 每天1-2种食材
2. 新食材优先安排在周一/周二（留足观察时间）
3. 同类食材不连续两天重复
4. 确保一周内红肉、蔬菜、水果、谷物都有覆盖
5. 输出的计划格式为 JSON 数组

输出格式：
[
  {"day": "周一", "date": "2026-05-18", "foods": ["猪肝泥", "米粉"], "is_new_food": true},
  ...
]"""

    def process(self, input_data: dict, **kwargs) -> dict:
        """
        生成周度计划。

        Args:
            input_data:
                {
                    profile: {...},
                    safe_foods: [{food_data, tag}, ...],   # 安全食材池
                    stage: {...},                          # 当前月龄阶段
                    preferences: {budget: str, ...}        # 可选偏好
                }
        """
        profile = input_data.get("profile", {})
        safe_foods = input_data.get("safe_foods", [])
        stage = input_data.get("stage", {})

        # 1. 规则引擎做约束排序
        sorted_foods = self._constraint_rank(safe_foods, profile)

        # 2. 确定本周新食材
        new_foods = self._select_new_foods(sorted_foods, profile)

        # 3. LLM 生成每日安排
        plan = self._generate_daily_plan(
            sorted_foods, new_foods, profile, stage,
        )

        return {
            "plan": plan,
            "new_foods_this_week": new_foods,
            "stage": stage.get("label", ""),
            "nutrition_notes": self._get_nutrition_notes(plan),
        }

    def _constraint_rank(self, foods: list, profile: dict) -> list:
        """规则约束排序：过敏已排、适龄已排，这里做营养优先级排序"""
        age_months = profile.get("age_months", 6)
        stage = self.kb.get_age_stage(age_months) if self.kb else None

        if not stage:
            return foods

        key_nutrients = stage.get("key_nutrients", [])
        if not key_nutrients:
            return foods

        # 按覆盖关键营养素数量排序
        for food in foods:
            food_data = food.get("food_data", {})
            nutrients = food_data.get("nutrients", {})
            food["_key_nutrient_count"] = sum(
                1 for n in key_nutrients if n in nutrients
            )

        foods.sort(key=lambda f: f.get("_key_nutrient_count", 0), reverse=True)
        return foods

    def _select_new_foods(self, foods: list, profile: dict) -> list:
        """选择本周引入的新食材"""
        tried = set(profile.get("tried_foods", []))
        return [
            f for f in foods[:3]  # 最多3种新食材
            if f.get("food_data", {}).get("name_zh") not in tried
        ]

    def _generate_daily_plan(
        self, foods: list, new_foods: list, profile: dict, stage: dict,
    ) -> list:
        """生成7天逐日计划"""
        meals_per_day_str = (stage or {}).get("meals_per_day", "2-3次")
        plan = []
        start_date = self._next_monday()

        for i in range(7):
            day_foods = self._pick_foods_for_day(foods, i, new_foods, profile)
            plan.append({
                "day": ["周一","周二","周三","周四","周五","周六","周日"][i],
                "date": (start_date + timedelta(days=i)).isoformat(),
                "foods": day_foods,
                "is_new_food": any(
                    f in [nf.get("food_data", {}).get("name_zh") for nf in new_foods]
                    for f in day_foods
                ),
                "serving_note": f"{meals_per_day_str}，从少量开始",
            })

        return plan

    def _pick_foods_for_day(
        self, foods: list, day_index: int, new_foods: list, profile: dict,
    ) -> list[str]:
        """为每天挑选1-2种食材（简化版，后续用 LLM 增强）"""
        # TODO: 替换为 LLM 驱动的灵活选择
        # 当前版本：线性轮询食材池
        idx = day_index % max(len(foods), 1)
        picked = [foods[idx].get("food_data", {}).get("name_zh", "")]
        if day_index < len(foods) - 1:
            alt_idx = (idx + 1) % max(len(foods), 1)
            if alt_idx != idx:
                picked.append(foods[alt_idx].get("food_data", {}).get("name_zh", ""))
        return [p for p in picked if p]

    def _get_nutrition_notes(self, plan: list) -> list[str]:
        """生成营养说明"""
        # TODO: 调用 nutrition_rules 生成具体缺口提醒
        return ["本周尝试覆盖多种颜色的蔬菜和肉类，确保营养均衡。"]

    @staticmethod
    def _next_monday() -> date:
        """获取下一个周一的日期"""
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        return today + timedelta(days=days_until_monday)
