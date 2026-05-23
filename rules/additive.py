"""添加糖/盐/添加剂检测规则。用于标签解析后的风险判定。"""

from .base import RuleResult, make_suitable


def check_added_sugar(ingredient: dict, age_months: int) -> RuleResult:
    """检测配料是否为添加糖。

    12月龄以下严格避免，12月龄以上限制。
    """
    ing_name = ingredient.get("name", "未知成分")
    if not ingredient.get("is_added_sugar"):
        return make_suitable("添加糖检查")

    if age_months < 12:
        return RuleResult(
            tag="avoid",
            reason=f"配料「{ing_name}」属于添加糖，12月龄以下宝宝不建议摄入。",
            rule_name="添加糖检测",
            source="WHO指南 / 美国膳食指南",
            severity="error",
        )
    else:
        return RuleResult(
            tag="caution",
            reason=f"配料「{ing_name}」属于添加糖，12月龄以上应限制。",
            rule_name="添加糖检测",
            severity="warning",
        )


def check_added_salt(ingredient: dict) -> RuleResult:
    """检测配料是否为添加盐/钠。"""
    ing_name = ingredient.get("name", "未知成分")
    if not ingredient.get("is_added_salt"):
        return make_suitable("添加盐检查")

    return RuleResult(
        tag="avoid",
        reason=f"配料「{ing_name}」属于添加盐/钠，婴幼儿食品不应额外添加盐。",
        rule_name="添加盐检测",
        source="WHO指南",
        severity="error",
    )


def check_artificial_additive(ingredient: dict, age_months: int) -> RuleResult:
    """检测人工添加剂。"""
    ing_name = ingredient.get("name", "未知成分")
    if not ingredient.get("is_artificial"):
        return make_suitable("添加剂检查")

    return RuleResult(
        tag="caution",
        reason=f"配料「{ing_name}」是人工添加剂（INS {ingredient.get('ins_code', '未知')}）。",
        rule_name="人工添加剂检测",
        source="Codex Stan 73 / FSANZ 2.9.2",
        severity="warning",
    )


def check_ingredient_risk_level(ingredient: dict, age_months: int) -> RuleResult:
    """根据配料表中预设的风险等级做检查。"""
    ing_name = ingredient.get("name", "未知成分")
    risk = ingredient.get("risk_level", "safe")

    if risk == "safe":
        return make_suitable("配料风险")

    reason_map = {
        "caution": f"配料「{ing_name}」需注意，建议少量观察",
        "avoid_under_12m": f"配料「{ing_name}」不建议12月龄以下摄入",
    }
    tag_map = {
        "caution": "caution",
        "avoid_under_12m": "avoid" if age_months < 12 else "caution",
    }

    return RuleResult(
        tag=tag_map.get(risk, "caution"),
        reason=reason_map.get(risk, f"配料「{ing_name}」风险等级：{risk}"),
        rule_name="配料风险等级检查",
        severity="warning",
    )
