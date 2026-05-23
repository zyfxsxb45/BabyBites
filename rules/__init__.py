"""规则引擎。

包含全部安全规则（硬编码、不依赖 LLM）和规则调度器。

用法：
    from rules import RuleEngine
    from kb import get_kb

    engine = RuleEngine(get_kb())
    result = engine.evaluate_food(food, baby_profile)
    if result.has_blocker:
        print(f"食材不可用: {result.reasons}")
"""

from .engine import RuleEngine
from .base import RuleResult, RuleOutput, make_suitable

__all__ = ["RuleEngine", "RuleResult", "RuleOutput", "make_suitable"]
