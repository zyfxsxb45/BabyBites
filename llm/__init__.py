"""LLM 抽象接口。"""

from .base import BaseLLM
from .openai_adapter import OpenAIAdapter

__all__ = ["BaseLLM", "OpenAIAdapter"]
