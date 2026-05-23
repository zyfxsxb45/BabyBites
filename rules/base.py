"""
规则引擎基础类型。

所有规则函数返回 RuleResult，由规则调度器 engine.py 汇总。
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class RuleResult:
    """单条规则的判定结果。

    Attributes:
        tag: suitable | caution | avoid | pending
        reason: 给家长看的解释文字
        source: 规则来源，便于可追溯
        severity: info | warning | error
        rule_name: 规则名称（用于日志和调试）
    """
    tag: Literal["suitable", "caution", "avoid", "not_applicable"]
    reason: str
    rule_name: str
    source: str = ""
    severity: Literal["info", "warning", "error"] = "info"
    details: dict = field(default_factory=dict)


@dataclass
class RuleOutput:
    """多维规则检验的汇总结果。

    Attributes:
        results: 每条规则的结果列表
        overall_tag: 综合标签
            avoid 优先：任一条 avoid → overall avoid
            caution 其次：无 avoid 但有条 caution → overall caution
            suitable：全部 suitable
        reasons: 合并后的解释列表
    """
    results: list[RuleResult]
    overall_tag: str = "suitable"
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self):
        self._compute_overall()

    def _compute_overall(self):
        """计算综合标签和原因"""
        tags = [r.tag for r in self.results]

        # avoid 最高优先级
        if "avoid" in tags:
            self.overall_tag = "avoid"
        elif "caution" in tags:
            self.overall_tag = "caution"
        elif any(t == "not_applicable" for t in tags):
            self.overall_tag = "not_applicable"
        else:
            self.overall_tag = "suitable"

        # 收集所有原因
        self.reasons = [r.reason for r in self.results if r.tag != "suitable"]

    @property
    def is_safe(self) -> bool:
        """是否全部通过"""
        return self.overall_tag == "suitable"

    @property
    def has_blocker(self) -> bool:
        """是否有不可通过的规则"""
        return self.overall_tag == "avoid"


def make_suitable(name: str, reason: str = "通过检验", source: str = "") -> RuleResult:
    """快捷创建通过结果"""
    return RuleResult(
        tag="suitable",
        reason=reason,
        rule_name=name,
        source=source,
        severity="info",
    )
