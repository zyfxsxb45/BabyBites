"""
用户画像智能体。

职责：从自然语言输入中提取结构化的宝宝画像，并进行字段校验。
使用 LLM 做 NLP 提取，关键字段做确定性校验。

输入：自然语言 or 直接的结构化字段
输出：校验后的结构化宝宝画像
"""

from .base import LLMAgent


class UserProfileAgent(LLMAgent):
    """提取并校验宝宝画像"""

    PROFILE_SCHEMA = {
        "age_months": {"type": "int", "required": True, "range": [0, 36]},
        "corrected_age_months": {"type": "int", "optional": True, "range": [0, 36]},
        "allergies": {"type": "list[str]", "description": "过敏原中文名列表"},
        "feeding_method": {
            "type": "str",
            "options": {"breast": "纯母乳", "formula": "配方奶", "mixed": "混合喂养"},
        },
        "tried_foods": {"type": "list[str]", "description": "已尝试的食材"},
        "birth_weight_kg": {"type": "float", "optional": True},
        "preterm": {"type": "bool", "optional": True},
        "notes": {"type": "str", "optional": True},
    }

    SYSTEM_PROMPT = """你是一个婴儿辅食助手，负责从家长的描述中提取宝宝的喂养相关信息。
请严格按 JSON 格式返回，只返回 JSON，不要附加其他文字。

提取规则：
- age_months: 宝宝月龄（整数，如"6个月"→6，"一岁"→12）
- corrected_age_months: 如果家长提到早产/矫正月龄才填，否则不填
- allergies: 已知过敏原列表（"对鸡蛋过敏"→["鸡蛋"]）
- feeding_method: 喂养方式（母乳/配方奶/混合）
- tried_foods: 已尝试过的食材列表
- preterm: 是否早产（true/false）
- notes: 家长备注（关于发育就绪信号的描述）
- 没提到的字段就不要填"""

    def process(self, input_data: dict, **kwargs) -> dict:
        """提取并校验宝宝画像"""
        user_input = input_data.get("user_input", "")

        # 如果已经给了结构化字段，直接校验
        if input_data.get("profile"):
            profile = self._validate_profile(input_data["profile"])
            return {
                "profile": profile,
                "valid": True,
                "warnings": [],
            }

        # 否则用 LLM 提取
        if self.llm and user_input:
            raw = self._ask_llm_structured(
                system_prompt=self.SYSTEM_PROMPT,
                user_message=user_input,
                output_schema=self.PROFILE_SCHEMA,
            )
            profile = self._validate_profile(raw)
        else:
            # 无 LLM：返回空画像
            profile = {"age_months": 6, "allergies": [], "feeding_method": "breast"}
            return {
                "profile": profile,
                "valid": True,
                "warnings": ["使用默认画像（无LLM输入）"],
            }

        return {
            "profile": profile,
            "valid": True,
            "warnings": [],
        }

    def _validate_profile(self, raw: dict) -> dict:
        """确定性校验 + 默认值填补"""
        profile = {}

        # age_months: 必填，范围 0-36
        age = raw.get("age_months", 0)
        if isinstance(age, str):
            age = self._parse_age_from_text(str(age))
        profile["age_months"] = max(0, min(36, int(age or 6)))

        # allergies: 标准化为列表
        allergies = raw.get("allergies", [])
        if isinstance(allergies, str):
            allergies = [a.strip() for a in allergies.replace("，", ",").split(",") if a.strip()]
        profile["allergies"] = allergies or []

        # feeding_method: 标准化
        fm = raw.get("feeding_method")
        if fm in ("纯母乳", "母乳"):
            profile["feeding_method"] = "breast"
        elif fm in ("配方", "奶粉", "配方奶"):
            profile["feeding_method"] = "formula"
        elif fm in ("混合",):
            profile["feeding_method"] = "mixed"
        elif fm:
            profile["feeding_method"] = fm
        # 没有提供喂养方式 → 不填，保持未知

        # tried_foods
        tried = raw.get("tried_foods", [])
        if isinstance(tried, str):
            tried = [t.strip() for t in tried.replace("，", ",").split(",") if t.strip()]
        profile["tried_foods"] = tried or []

        # corrected_age_months
        corrected = raw.get("corrected_age_months")
        if corrected is not None:
            profile["corrected_age_months"] = int(corrected)

        # preterm
        profile["preterm"] = bool(raw.get("preterm")) or "corrected_age_months" in raw

        # notes
        profile["notes"] = raw.get("notes", "")

        # birth_weight
        if raw.get("birth_weight_kg"):
            try:
                profile["birth_weight_kg"] = float(raw["birth_weight_kg"])
            except (ValueError, TypeError):
                pass

        return profile

    @staticmethod
    def _parse_age_from_text(text: str) -> int:
        """从文本中解析月龄"""
        import re

        # "6个月" → 6
        m = re.search(r'(\d+)\s*个?\s*月', text)
        if m:
            return int(m.group(1))

        # "1岁" → 12
        m = re.search(r'(\d+)\s*岁', text)
        if m:
            return int(m.group(1)) * 12

        # "1岁2个月" → 14
        m = re.search(r'(\d+)\s*岁\s*(\d+)\s*个?\s*月', text)
        if m:
            return int(m.group(1)) * 12 + int(m.group(2))

        # 纯数字
        m = re.search(r'\d+', text)
        if m:
            return int(m.group(0))

        return 6
