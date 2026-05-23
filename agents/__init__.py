"""智能体层。

6 个智能体各司其职，通过依赖注入共享 kb 和 llm 实例。

用法：
    from kb import get_kb
    from llm import get_llm
    from agents import SafetyBoundaryAgent, PlanGenerationAgent

    kb = get_kb()
    llm = get_llm()

    safety = SafetyBoundaryAgent(kb=kb)
    result = safety.process({"profile": baby_profile, "candidate_foods": foods})
"""

from .user_profile import UserProfileAgent
from .label_parsing import LabelParsingAgent
from .safety_boundary import SafetyBoundaryAgent
from .plan_generation import PlanGenerationAgent
from .validation import ValidationAgent
from .dialogue import DialogueAgent

__all__ = [
    "UserProfileAgent",
    "LabelParsingAgent",
    "SafetyBoundaryAgent",
    "PlanGenerationAgent",
    "ValidationAgent",
    "DialogueAgent",
]
