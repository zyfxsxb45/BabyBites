"""OpenAI API 适配器。

支持 OpenAI 兼容 API（DeepSeek / OpenAI / 硅基流动 / 阿里百炼 等）。
通过 .env 配置。

改进：
  - 错误处理 + 重试（网络瞬断自动重试 2 次）
  - max_tokens 最低保底 50（某些 API 不接受极短值）
  - response.content 为 None 时返回空字符串
  - 超时设置 30s
"""

import json, time
from typing import Optional
from .base import BaseLLM
from config.settings import LLM_CONFIG

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class OpenAIAdapter(BaseLLM):
    """OpenAI 兼容 API 适配器"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        if not HAS_OPENAI:
            raise ImportError("openai package required. pip install openai")
        self.api_key = api_key or LLM_CONFIG["api_key"]
        self.base_url = base_url or LLM_CONFIG["base_url"]
        self.model = model or LLM_CONFIG["model"]

        if not self.api_key or self.api_key.startswith("sk-your-"):
            raise RuntimeError(
                f"API Key 未配置或仍为占位符。请在 .env 中设置 OPENAI_API_KEY。\n"
                f"当前值: {self.api_key[:8]}..."
            )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=30.0,
            max_retries=2,
        )

    def chat(self, system_prompt: str, user_message: str, **kwargs) -> str:
        """发送对话，返回文本。带重试和错误处理。

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息
            **kwargs: model, temperature, max_tokens 等

        Returns:
            LLM 回复文本，失败返回空字符串
        """
        last_error = None
        for attempt in range(3):  # 最多重试 3 次
            try:
                response = self.client.chat.completions.create(
                    model=kwargs.get("model", self.model),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=kwargs.get("temperature", 0.3),
                    max_tokens=max(kwargs.get("max_tokens", 1024), 50),  # 最低 50
                )

                content = None
                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content

                return content or ""

            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 2 ** attempt  # 1s, 2s 退避
                    time.sleep(wait)
                else:
                    # 最后一次失败，打印但不崩溃
                    err_msg = str(e)[:200]
                    print(f"[LLM Error] attempt {attempt+1}/3: {err_msg}")
                    return ""

        return ""

    def chat_structured(
        self, system_prompt: str, user_message: str, schema: dict, **kwargs
    ) -> dict:
        """发送对话，返回结构化的 dict。

        自动处理几种 LLM 常见输出格式:
          - 纯 JSON
          - ```json ... ```
          - ``` ... ```

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息
            schema: 期望的输出 schema（备用，暂未用于校验）
            **kwargs: 传递给 chat() 的额外参数

        Returns:
            解析后的 dict，解析失败返回 {"raw": text}
        """
        # 强制要求 JSON 输出（如果 prompt 没提的话）
        if "json" not in system_prompt.lower() and "JSON" not in system_prompt:
            system_prompt = system_prompt + "\n只返回JSON，不要其他文字。"

        text = self.chat(system_prompt, user_message, **kwargs)

        if not text:
            return {"raw": "", "error": "LLM returned empty"}

        text = text.strip()

        # 1. 纯 JSON
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # 2. ```json 代码块
        if "```json" in text:
            try:
                start = text.index("```json") + 7
                end = text.index("```", start)
                return json.loads(text[start:end].strip())
            except (ValueError, json.JSONDecodeError):
                pass

        # 3. ``` 代码块
        if "```" in text:
            try:
                start = text.index("```") + 3
                end = text.index("```", start)
                return json.loads(text[start:end].strip())
            except (ValueError, json.JSONDecodeError):
                pass

        return {"raw": text}
