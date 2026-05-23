"""格式化工具"""


def format_nutrient(value: float, unit: str) -> str:
    """格式化营养素数值"""
    if value >= 10:
        return f"{value:.0f} {unit}"
    elif value >= 1:
        return f"{value:.1f} {unit}"
    else:
        return f"{value:.2f} {unit}"


def safe_tag_emoji(tag: str) -> str:
    """标签→emoji"""
    emojis = {
        "suitable": "✅",
        "caution": "⚠️",
        "avoid": "🚫",
        "not_applicable": "—",
        "unknown": "❓",
    }
    return emojis.get(tag, "•")


def food_summary(food: dict) -> str:
    """生成食材单行摘要"""
    name = food.get("name_zh", "?")
    category = food.get("category", "")
    iron = "高铁" if food.get("iron_rich") else ""
    allergen = "⚠过敏原" if food.get("allergen") else ""
    return f"{name}({category}) {iron} {allergen}".strip()
