"""
LLM API 配置与适配器。

提供统一的 LLM 调用接口，内部适配 OpenAI 兼容 API。
切换模型只需改 .env 中的 LLM_MODEL。
"""

from .settings import LLM_CONFIG


def get_llm_config() -> dict:
    """返回当前 LLM 配置"""
    return LLM_CONFIG


def validate_config() -> bool:
    """检查 LLM 配置是否就绪"""
    return bool(LLM_CONFIG.get("api_key"))
