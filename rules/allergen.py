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
    llm=None,
    strict_mode: bool = False,
) -> RuleResult:
    """
    检查食材是否含有宝宝已知过敏原。支持语义匹配。

    Args:
        strict_mode: 严格模式。True 时，潜在过敏原仅在没有已知过敏命中时才标 caution，
                     且不会因为"该食物本身就是潜在过敏原"而过度保守。
                     False 时，保持现有行为（所有潜在过敏原都标 caution）。
    """
    if not baby_allergies:
        baby_allergies = []  # 确保不为 None

    food_name = food.get("name_zh", food.get("id", "未知食材"))
    food_allergen = food.get("allergen")

    # 解析宝宝的过敏原：用户输入的日常用语 → 标准过敏原 ID 列表（必须先做）
    resolved_allergy_ids = set()
    if kb and hasattr(kb, "resolve_allergen_query"):
        for term in baby_allergies:
            ids = kb.resolve_allergen_query(term, llm=llm)
            resolved_allergy_ids.update(ids)

    # 外部食材：检查 _allergen_flags
    if food.get("_external"):
        ext_flags = food.get("_allergen_flags", {})
        for ext_key, internal_name in [
            ("contains_milk", "牛奶"), ("contains_egg", "鸡蛋"),
            ("contains_wheat", "小麦"), ("contains_soy", "大豆"),
            ("contains_peanut", "花生"), ("contains_tree_nut", "坚果"),
            ("contains_fish", "鱼类"), ("contains_shellfish", "虾"),
        ]:
            if ext_flags.get(ext_key):
                # 检查宝宝是否对该过敏原有已知过敏
                if kb and hasattr(kb, "_find_allergen_id_by_name"):
                    aid = kb._find_allergen_id_by_name(internal_name)
                    if aid and aid in resolved_allergy_ids:
                        return RuleResult(
                            tag="avoid",
                            reason=f"{food_name}{'含' if food_allergen else '可能含'}{internal_name}，"
                                   f"与宝宝已知过敏原冲突",
                            rule_name="已知过敏原拦截（外部食材）",
                            source="外部数据 / CDC指南",
                            severity="error",
                        )
                # 食材含该过敏原但宝宝没被标记，标记为潜在过敏
                food_allergen = food_allergen or internal_name
    resolved_allergy_ids = set()
    if kb and hasattr(kb, "resolve_allergen_query"):
        for term in baby_allergies:
            ids = kb.resolve_allergen_query(term, llm=llm)
            resolved_allergy_ids.update(ids)

    if not food_allergen:
        if food.get("potential_allergen", False):
            return RuleResult(
                tag="caution",
                reason=f"{food_name}是潜在致敏食材（过敏原类别：{food_allergen or '未指定'}），"
                       f"首日试行本可先给极少份量，观察宝宝反应",
                rule_name="潜在过敏原提示",
                source="CDC指南",
                severity="warning",
            )
        return make_suitable("过敏原检查", f"{food_name}不含已知过敏原")

    # 解析食材的过敏原字段：可能是 umbrella term（如"海鲜"）
    food_allergen_ids = set()
    if kb and hasattr(kb, "resolve_allergen_query"):
        food_allergen_ids = set(kb.resolve_allergen_query(food_allergen, llm=llm))
    if not food_allergen_ids and kb:
        # fallback: 直接查找过敏原条目
        for aid_key, a in kb._allergens.items():
            if aid_key.startswith("_"):
                continue
            if aid_key == food_allergen or a.get("name_zh") == food_allergen:
                food_allergen_ids.add(a.get("id"))
                break

    # 匹配：宝宝的过敏原 ∩ 食材的过敏原
    if food_allergen_ids & resolved_allergy_ids:
        return RuleResult(
            tag="avoid",
            reason=f"{food_name}含有已知过敏原「{food_allergen}」，"
                   f"请避免使用。建议用其他同类食材替代。",
            rule_name="已知过敏原拦截",
            source="CDC指南 / WHO喂养原则",
            severity="error",
        )

    # 食材是潜在致敏物
    if food.get("potential_allergen", False):
        # strict_mode: 没有命中已知过敏原 + 用户也没有模糊提过敏 → safe
        if strict_mode:
            return make_suitable(
                "过敏原检查",
                f"{food_name}是潜在致敏食材，但宝宝无已知相关过敏，可谨慎引入"
            )
        return RuleResult(
            tag="caution",
            reason=f"{food_name}是潜在致敏食材（过敏原类别：{food_allergen}），"
                   f"首日试吃可先给极少份量，观察宝宝反应",
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
