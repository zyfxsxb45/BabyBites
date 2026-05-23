"""OpenAI API 适配器。

支持 OpenAI 兼容 API（可替换为任何兼容的 API endpoint）。
通过 .env 中的 OPENAI_BASE_URL 配置。
"""

import json
from typing import Optional
from .base import BaseLLM
from config.settings import LLM_CONFIG

# 延迟导入，避免没有装 openai 库时 import 报错
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class OpenAIAdapter(BaseLLM):
    """OpenAI 兼容 API 适配器"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        if not HAS_OPENAI:
            raise ImportError("openai package required. pip install openai")
        self.api_key = api_key or LLM_CONFIG["api_key"]
        self.base_url = base_url or LLM_CONFIG["base_url"]
        self.model = model or LLM_CONFIG["model"]
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(self, system_prompt: str, user_message: str, **kwargs) -> str:
        """发送对话，返回文本"""
        response = self.client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 1024),
        )
        return response.choices[0].message.content or ""

    def chat_structured(self, system_prompt: str, user_message: str, schema: dict, **kwargs) -> dict:
        """发送对话，返回结构化的 dict"""
        text = self.chat(system_prompt, user_message, **kwargs)
        try:
            # 尝试直接解析 JSON
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            if "```json" in text:
                start = text.index("```json") + 7
                end = text.index("```", start)
                return json.loads(text[start:end])
            elif "```" in text:
                start = text.index("```") + 3
                end = text.index("```", start)
                return json.loads(text[start:end])
            return {"raw": text}
