"""
阶段与安全边界智能体。

职责：判断宝宝是否进入辅食阶段，执行硬性安全拦截。
纯规则，无 LLM 参与——这是安全底线。

输入：宝宝画像
输出：阶段评估 + 安全拦截结果 + 候选食材标签
"""

import re
from .base import RuleAgent
from rules.engine import RuleEngine


class SafetyBoundaryAgent(RuleAgent):
    """阶段判断 + 安全拦截 + 发育信号提取"""

    # 发育就绪信号关键词
    READINESS_KEYWORDS = {
        "head_control": ["能抬头", "能控制头", "头稳", "脖子有劲", "能坐着"],
        "sits_supported": ["能坐", "能靠着坐", "能倚坐", "坐得稳"],
        "interest_in_food": ["看大人吃饭", "伸手抓", "张嘴", "对食物感兴趣", "流口水"],
        "tongue_thrust_gone": ["不顶舌", "不往外推", "能吞咽", "会咽"],
        "doubled_birth_weight": ["体重翻倍", "体重是出生", "长得快"],
    }

    def __init__(self, kb=None, rule_engine=None, llm=None):
        if rule_engine is None and kb is not None:
            rule_engine = RuleEngine(kb)
        super().__init__(kb=kb, rule_engine=rule_engine)
        self._llm = llm

    def process(self, input_data: dict, **kwargs) -> dict:
        profile = input_data.get("profile", {})
        age_months = profile.get("age_months", 0)
        corrected = profile.get("corrected_age_months")
        effective_age = corrected if corrected is not None else age_months

        # 1. 阶段判断
        can_start, blocking = self._check_readiness(profile)

        # 2. 阶段定义
        stage = self.kb.get_age_stage(effective_age) if self.kb else None

        # 3. 发育信号
        notes = profile.get("notes", "")
        signals = self._extract_readiness_signals(notes)

        # 4. 候选食材安全标签
        food_results = {}
        candidate_foods = input_data.get("candidate_foods", [])
        for food in candidate_foods:
            food_data = food.get("food_data", food)
            if not food_data:
                continue
            result = self.rule_engine.evaluate_food(food_data, profile, llm=self._llm)
            food_id = food_data.get("id", food_data.get("name_zh", ""))
            food_results[food_id] = {
                "tag": result.overall_tag,
                "reasons": result.reasons,
            }

        return {
            "can_start": can_start,
            "stage": stage,
            "age_months": age_months,
            "effective_age_months": effective_age,
            "is_preterm_corrected": corrected is not None and corrected != age_months,
            "readiness_signals": signals,
            "readiness_score": len(signals),
            "blocking_reasons": blocking,
            "food_safety_results": food_results,
            "recommendation": self._generate_recommendation(
                can_start, effective_age, stage, signals, blocking
            ),
        }

    def _check_readiness(self, profile: dict) -> tuple[bool, list[str]]:
        """
        检查是否具备辅食条件。

        条件：
          1. 矫正月龄 ≥ 6 个月 → 可以开始
          2. 矫正月龄 4-5 个月 → 需有明显发育信号 + 医生建议
          3. 矫正月龄 < 4 个月 → 绝对不能
        """
        age = profile.get("age_months", 0)
        corrected = profile.get("corrected_age_months")
        effective = corrected if corrected is not None else age
        blocking = []

        if effective < 4:
            blocking.append(
                f"宝宝矫正月龄仅 {effective} 个月，远未到辅食添加标准（≥6个月）。任何情况下4月龄以内不应添加辅食。"
            )
            return False, blocking

        if effective < 6:
            # 4-5 月龄：需有明显就绪信号
            notes = profile.get("notes", "")
            signals = self._extract_readiness_signals(notes)
            if len(signals) < 3:
                blocking.append(
                    f"宝宝矫正月龄 {effective} 个月，尚未满 6 个月。"
                    f"只有在宝宝具备明显发育就绪信号（能坐、对食物感兴趣、不顶舌等）"
                    f"且经儿科医生评估后才可考虑提前添加辅食。"
                )
                return False, blocking
            # 有足够信号但月龄偏早：给 caution 但仍允许
            blocking.append(
                f"宝宝矫正月龄 {effective} 个月，接近但未满 6 个月。"
                f"检测到 {len(signals)} 个发育就绪信号，可谨慎尝试，"
                f"建议咨询儿科医生确认。"
            )
            return True, blocking

        # ≥6 个月：可以开始
        return True, blocking

    def _extract_readiness_signals(self, notes: str) -> list[dict]:
        """从家长备注中提取发育就绪信号"""
        if not notes:
            return []

        found = []
        for category, keywords in self.READINESS_KEYWORDS.items():
            for kw in keywords:
                if kw in notes:
                    found.append({
                        "category": category,
                        "keyword": kw,
                        "label": {
                            "head_control": "能控制头部",
                            "sits_supported": "能靠着坐",
                            "interest_in_food": "对食物感兴趣",
                            "tongue_thrust_gone": "能吞咽不顶舌",
                            "doubled_birth_weight": "体重增长良好",
                        }.get(category, category),
                    })
                    break  # 每类只取第一个匹配

        return found

    def _generate_recommendation(
        self, can_start: bool, age: int, stage: dict,
        signals: list, blocking: list,
    ) -> str:
        """生成人类可读的建议"""
        if can_start and len(blocking) == 0:
            return (
                f"✅ 宝宝（矫正月龄 {age} 个月）已具备辅食添加条件。"
                f"当前阶段：{stage.get('label', '')}（{stage.get('age_range', '')}）。"
                f"质地以 {stage.get('texture', '')} 为主。"
            )
        elif can_start and blocking:
            return f"⚠️ 可以尝试辅食，但需注意：{' '.join(blocking)}"
        else:
            return f"🚫 暂不建议添加辅食。{' '.join(blocking)}"
