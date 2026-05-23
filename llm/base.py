"""LLM 接口基类"""

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """LLM 抽象基类"""

    @abstractmethod
    def chat(self, system_prompt: str, user_message: str, **kwargs) -> str:
        """发送对话并返回文本"""
        ...

    @abstractmethod
    def chat_structured(self, system_prompt: str, user_message: str, schema: dict, **kwargs) -> dict:
        """发送对话并解析为结构化输出"""
        ...
