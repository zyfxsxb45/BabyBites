"""
知识库工厂。

根据 .env 中的 KB_BACKEND 配置选择后端。
上层代码只需调用 `get_kb()` 即可获得知识库实例，
不关心底层用的是 JSON 还是 Neo4j。
"""

from config.settings import KB_BACKEND


def get_kb():
    """
    返回知识库实例。

    Returns:
        一个实现了 KnowledgeBase 协议的对象（JSONKnowledgeBase 或 Neo4jKnowledgeBase）

    用法：
        kb = get_kb()
        foods = kb.list_foods_by_age(6)
        # 不管后端是什么，上层代码都一样
    """
    if KB_BACKEND == "neo4j":
        from .neo4j_backend import Neo4jKnowledgeBase
        return Neo4jKnowledgeBase()
    else:
        from .json_backend import JSONKnowledgeBase
        return JSONKnowledgeBase()
