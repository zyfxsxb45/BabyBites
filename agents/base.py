"""
智能体基类。

所有智能体统一接口：接收输入 → 处理 → 返回输出。
每个智能体的 __init__ 接收 kb（知识库）和 llm（如果需要），
通过依赖注入实现解耦。
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseAgent(ABC):
    """智能体基类"""

    def __init__(self, kb=None, llm=None):
        self.kb = kb
        self.llm = llm

    @abstractmethod
    def process(self, input_data: dict, **kwargs) -> dict:
        """处理输入，返回结构化输出"""
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class LLMAgent(BaseAgent):
    """需要 LLM 的智能体基类。

    llm 可以为 None——此时智能体走纯规则/正则 fallback。
    """

    def __init__(self, kb=None, llm=None):
        super().__init__(kb=kb, llm=llm)

    def _ask_llm(self, system_prompt: str, user_message: str, **kwargs) -> str:
        """调用 LLM 并返回文本"""
        if self.llm is None:
            raise RuntimeError("LLM not configured")
        return self.llm.chat(system_prompt, user_message, **kwargs)

    def _ask_llm_structured(
        self,
        system_prompt: str,
        user_message: str,
        output_schema: dict,
        **kwargs,
    ) -> dict:
        """调用 LLM 并解析为结构化 dict。

        自动处理常见 LLM 输出格式：
          - 纯 JSON: {"age_months": 6}
          - ```json ... ``` 代码块
          - 带前后文字的 JSON
        """
        import json
        response = self._ask_llm(system_prompt, user_message, **kwargs)
        if not response:
            return _default_profile(output_schema)

        text = response.strip()

        # 尝试多种解析策略
        for strategy in [
            lambda t: json.loads(t),                          # 纯 JSON
            lambda t: json.loads(_extract_code_block(t)),      # ```json ... ```
            lambda t: json.loads(_extract_code_block(t, "")),  # ``` ... ```
            lambda t: json.loads(_extract_first_json(t)),      # 提取第一个 {}
        ]:
            try:
                return strategy(text)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

        # 所有策略失败，返回 raw
        return {"raw": response, "schema": output_schema}


def _extract_code_block(text: str, tag: str = "json") -> str:
    """提取 ```lang ... ``` 代码块内容"""
    marker = f"```{tag}" if tag else "```"
    if marker not in text:
        raise ValueError("no code block")
    start = text.index(marker) + len(marker)
    end = text.index("```", start)
    return text[start:end].strip()


def _extract_first_json(text: str) -> str:
    """提取文本中第一个完整 JSON 对象"""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object")
    # 简单的括号计数找闭合
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    raise ValueError("unclosed JSON")


def _default_profile(schema: dict) -> dict:
    """根据 schema 生成默认值"""
    return {k: v.get("type", "") for k, v in schema.items() if isinstance(v, dict)}


class RuleAgent(BaseAgent):
    """纯规则智能体基类（不需要 LLM）。

    处理逻辑全部由 Python 代码和规则引擎完成。
    """

    def __init__(self, kb=None, rule_engine=None):
        super().__init__(kb=kb, llm=None)
        self.rule_engine = rule_engine
