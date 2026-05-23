"""
过敏拦截规则。

这是安全约束的最高优先级：已知过敏原 → avoid。
不依赖 LLM，纯粹的数据匹配。

数据来源：allergens.json 中定义的过敏原及其别名。
"""

from typing import Optional
from .base import RuleResult, make_suitable


def check_known_allergy(
    food: dict,
    baby_allergies: list[str],
    kb=None,
) -> RuleResult:
    """
    检查食材是否含有宝宝已知过敏原。

    Args:
        food: 食材数据（来自 foods.json 或 kb.get_food()）
        baby_allergies: 宝宝的过敏原 ID 列表，如 ['allergen_001', 'allergen_002']
        kb: 知识库实例（用于查询过敏原别名，可选但不需——此规则不依赖 KB）

    Returns:
        RuleResult: tag='avoid' 如果食材本身就是已知过敏原
                    tag='suitable' 如果无冲突
    """
    if not baby_allergies:
        return make_suitable("过敏原检查", "宝宝无已知过敏原")

    food_allergen = food.get("allergen")
    food_name = food.get("name_zh", food.get("id", "未知食材"))

    # 食材本身是过敏原（如"鸡蛋"→鸡蛋过敏）
    if food_allergen:
        # food.allergen 存的是过敏原名称，需匹配
        for allergy_id in baby_allergies:
            # 简单名称匹配（可直接扩展为查 allergens.json 的 aliases）
            if kb:
                allergen = kb.get_allergen(allergy_id)
                if allergen and food_allergen in allergen.get("aliases", []):
                    return RuleResult(
                        tag="avoid",
                        reason=f"{food_name}含有已知过敏原「{food_allergen}」，"
                               f"请避免使用。建议用其他同类食材替代。",
                        rule_name="已知过敏原拦截",
                        source="CDC指南 / WHO喂养原则",
                        severity="error",
                    )

    # 如果食物不是过敏原
    if food.get("potential_allergen", False):
        # 食物属于可能致敏的类别，但不在宝宝已知过敏列表中
        return RuleResult(
            tag="caution",
            reason=f"{food_name}是潜在致敏食材（过敏原类别：{food_allergen or '未指定'}），"
                   f"首日试行本可先给极少份量，观察宝宝反应",
            rule_name="潜在过敏原提示",
            source="CDC指南",
            severity="warning",
        )

    return make_suitable("过敏原检查", f"{food_name}不含已知过敏原")


def check_ingredient_allergen(
    ingredient: dict,
    baby_allergies: list[str],
    kb=None,
) -> RuleResult:
    """
    检查配料中是否含有过敏原（用于标签解析智能体）。

    Args:
        ingredient: 配料数据（来自 ingredients 表或 kb.get_ingredient()）
        baby_allergies: 宝宝过敏原 ID 列表

    Returns:
        如果配料是过敏原或含有过敏原 → avoid
    """
    ing_name = ingredient.get("name", "未知配料")

    # 配料本身标记为过敏原
    if ingredient.get("is_allergen"):
        ing_allergen_id = ingredient.get("allergen_id")
        if ing_allergen_id in baby_allergies:
            return RuleResult(
                tag="avoid",
                reason=f"配料「{ing_name}」是已知过敏原，该商品不建议使用",
                rule_name="配料过敏原拦截",
                severity="error",
            )

    # 通过别名再查一轮
    if kb:
        for allergy_id in baby_allergies:
            matched = kb.match_allergen_by_alias(ing_name)
            if matched == allergy_id:
                return RuleResult(
                    tag="avoid",
                    reason=f"配料「{ing_name}」匹配已知过敏原（别名匹配），"
                           f"该商品不建议使用",
                    rule_name="配料过敏原拦截(别名)",
                    severity="error",
                )

    return make_suitable("配料过敏原检查")
