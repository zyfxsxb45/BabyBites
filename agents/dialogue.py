"""
对话记忆与解释智能体。

职责：记录用户反馈、生成可读解释、管理对话上下文。
纯 LLM，接收结构化输入生成自然语言。

这是唯一一个"不参与决策"的智能体，只管表达。
"""

from .base import LLMAgent


class DialogueAgent(LLMAgent):
    """自然语言解释和对话记忆"""

    SYSTEM_PROMPT = """你是一个温和耐心的婴儿辅食助手，名字叫"宝宝巴适"。
你会收到系统生成的喂养建议（结构化数据），你的职责是用家长容易理解
语言重新表达。

要求：
- 语气温暖亲切但不夸张
- 解释每个建议的原因（"因为猪肝含铁高，6月龄宝宝正需要补铁"）
- 如果宝宝有过敏史，温和提醒
- 专业信息来源可以提及（"根据CDC指南..."），但不要长篇大论
- 鼓励家长观察和反馈"""

    def process(self, input_data: dict, **kwargs) -> dict:
        """
        生成自然语言回应。

        Args:
            input_data:
                {
                    plan: [...],              # 计划数据
                    stage_result: {...},      # 阶段判断结果
                    validation_result: {...}, # 校验结果
                    user_feedback: str,       # 用户反馈（如果有）
                    conversation_history: [...],  # 历史
                }
        """
        # 构建给 LLM 的消息
        message = self._build_message(input_data)
        response = self._ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=message,
        )

        return {
            "message": response,
            "input_summary": self._summarize_input(input_data),
        }

    def _build_message(self, data: dict) -> str:
        """构建给 LLM 的结构化消息"""
        parts = []

        # 阶段结果
        stage = data.get("stage_result", {})
        if stage:
            can_start = "可以" if stage.get("can_start") else "不可以"
            parts.append(f"辅食评估结果：{can_start}开始辅食")

            if stage.get("blocking_reasons"):
                parts.append("不能开始的原因：")
                for r in stage["blocking_reasons"]:
                    parts.append(f"  - {r}")

        # 计划
        plan = data.get("plan", [])
        if plan:
            parts.append("本周辅食计划：")
            for day in plan:
                foods = "、".join(day.get("foods", []))
                note = " 🆕新食材" if day.get("is_new_food") else ""
                parts.append(f"  {day.get('day', '')}：{foods}{note}")

        # 校验结果
        validation = data.get("validation_result", {})
        if validation:
            if not validation.get("passed"):
                parts.append("⚠️ 以下项目未通过安全校验：")
                for v in validation.get("violations", []):
                    parts.append(f"  - {v.get('day')}：{v.get('food')} - {v.get('reason')}")

        # 用户反馈
        feedback = data.get("user_feedback", "")
        if feedback:
            parts.append(f"用户反馈：{feedback}")

        return "\n".join(parts)

    def _summarize_input(self, data: dict) -> str:
        """记录对话摘要"""
        plan = data.get("plan", [])
        return f"生成了{len(plan)}天的计划"
