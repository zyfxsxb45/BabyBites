"""统一初始化模块。

提供三个便捷初始化函数，封装配置、kb、llm 的创建逻辑。
app 入口只需调用 init_app() 即可获取所有核心组件。
"""

from config.settings import DEBUG, KB_BACKEND, LOG_LEVEL
from kb.factory import get_kb
from llm.openai_adapter import OpenAIAdapter


def init_kb():
    """初始化知识库（根据 .env 选择后端）"""
    kb = get_kb()
    if DEBUG:
        stats = kb.get_stats()
        print(f"[KB] backend={stats.get('backend', 'unknown')}, "
              f"foods={stats.get('foods_count', 0)}, "
              f"allergens={stats.get('allergens_count', 0)}")
    return kb


def init_llm():
    """初始化 LLM 接口"""
    llm = OpenAIAdapter()
    if DEBUG:
        print(f"[LLM] model={llm.model}, base_url={llm.base_url}")
    return llm


def init_app():
    """一键初始化全部核心组件。

    Returns:
        (kb, llm) 元组
    """
    print(f"BabyBites 启动中...")
    print(f"  KB 后端: {KB_BACKEND}")
    print(f"  Debug: {DEBUG}")
    print(f"  Log Level: {LOG_LEVEL}")

    kb = init_kb()
    llm = init_llm()
    return kb, llm
