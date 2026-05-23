"""
用户画像智能体。

职责：从自然语言输入中提取结构化的宝宝画像。
使用 LLM 做 NLP 提取，然后对关键字段做确定性校验。

输入：用户自然语言输入
输出：结构化宝宝画像
"""

from .base import LLMAgent


class UserProfileAgent(LLMAgent):
    """提取并校验宝宝画像"""

    PROFILE_SCHEMA = {
        "age_months": {"type": "int", "required": True, "range": [0, 36]},
        "corrected_age_months": {"type": "int", "optional": True},
        "allergies": {"type": "list[str]", "description": "过敏原中文名列表"},
        "feeding_method": {"type": "str", "options": ["breast", "formula", "mixed"]},
        "tried_foods": {"type": "list[str]", "description": "已尝试的食材"},
        "birth_weight_kg": {"type": "float", "optional": True},
        "preterm": {"type": "bool", "optional": True},
        "notes": {"type": "str", "optional": True},
    }

    SYSTEM_PROMPT = """你是一个婴儿辅食助手，负责从家长的描述中提取宝宝的喂养相关信息。
请严格按 JSON 格式返回，只返回 JSON，不要附加其他文字。
提取以下字段：
- age_months: 宝宝月龄（整数）
- allergies: 已知过敏原列表（如果家长说"对鸡蛋过敏"→ ["鸡蛋"]）
- feeding_method: 喂养方式（breast/formula/mixed）
- tried_foods: 已尝试过的食材列表
- 其他字段如果有提到就提取，没提到就写 null"""

    def process(self, input_data: dict, **kwargs) -> dict:
        """从用户输入中提取宝宝画像"""
        user_input = input_data.get("user_input", "")

        # LLM 提取结构化字段
        raw = self._ask_llm_structured(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_input,
            output_schema=self.PROFILE_SCHEMA,
        )

        # 确定性校验（未来实现更完善的校验）
        profile = self._validate_profile(raw)

        return {
            "profile": profile,
            "raw_input": user_input,
        }

    def _validate_profile(self, raw: dict) -> dict:
        """校验 LLM 提取的样本"""
        # TODO: 实现完整的格式校验和默认值填补
        return raw
