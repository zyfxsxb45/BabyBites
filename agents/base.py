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
        """调用 LLM 并解析为结构化输出"""
        response = self._ask_llm(system_prompt, user_message, **kwargs)
        # 子类可 override 做更复杂的解析
        return {"raw": response, "schema": output_schema}


class RuleAgent(BaseAgent):
    """纯规则智能体基类（不需要 LLM）。

    处理逻辑全部由 Python 代码和规则引擎完成。
    """

    def __init__(self, kb=None, rule_engine=None):
        super().__init__(kb=kb, llm=None)
        self.rule_engine = rule_engine
