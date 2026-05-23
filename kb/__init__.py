"""
知识库抽象层。

核心导出：
  - KnowledgeBase Protocol（接口定义）
  - get_kb() 工厂函数（单行获取后端实例）

用法：
    from kb import get_kb
    kb = get_kb()
    foods = kb.list_foods_by_age(6)
"""

from .interface import KnowledgeBase
from .factory import get_kb
from .json_backend import JSONKnowledgeBase

__all__ = ["KnowledgeBase", "get_kb", "JSONKnowledgeBase"]
