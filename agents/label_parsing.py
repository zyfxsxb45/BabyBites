"""
标签解析智能体。

职责：解析用户输入的食材/商品配料表，识别成分和风险标签。
LLM 做文字切分，数据库做精确匹配。
"""

from .base import LLMAgent
from rules.additive import (
    check_added_sugar,
    check_added_salt,
    check_artificial_additive,
    check_ingredient_risk_level,
)


class LabelParsingAgent(LLMAgent):
    """解析配料表，输出成分风险标签"""

    SYSTEM_PROMPT = """你是一个婴幼儿食品配料分析助手。
请将输入的商品配料表切分成独立的成分项，每项一行。
注意规则：
1. 按逗号、顿号、括号切分
2. 括号内的内容视为主成分的修饰，合并为一个条目
3. 去掉序号、百分比、"(含...)"等无关信息
4. 只返回成分列表，每行一个，不要附加解释

示例输入：大米(85%), 乳清蛋白, 白砂糖, 柠檬酸(330), 碳酸钙
示例输出：
大米
乳清蛋白
白砂糖
柠檬酸
碳酸钙"""

    def process(self, input_data: dict, **kwargs) -> dict:
        """解析配料表"""
        ingredient_text = input_data.get("ingredient_text", "")
        age_months = input_data.get("age_months", 6)

        # 1. LLM 切分配料表
        raw_ingredients = self._split_ingredients(ingredient_text)

        # 2. 数据库匹配（通过 kb）
        parsed = []
        for name in raw_ingredients:
            matched = self.kb.match_ingredient_by_name(name) if self.kb else None
            entry = {
                "raw_name": name,
                "matched": matched is not None,
            }
            if matched:
                entry["ingredient"] = matched
                # 规则检查
                entry["tags"] = self._check_ingredient(matched, age_months)
            else:
                entry["ingredient"] = None
                entry["tags"] = [{"tag": "unknown", "reason": f"未收录成分: {name}"}]
            parsed.append(entry)

        return {
            "parsed": parsed,
            "total_count": len(parsed),
            "matched_count": sum(1 for p in parsed if p["matched"]),
            "raw_input": ingredient_text,
        }

    def _split_ingredients(self, text: str) -> list[str]:
        """LLM 切分配料表"""
        response = self._ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=text,
        )
        return [
            line.strip()
            for line in response.strip().split("\n")
            if line.strip()
        ]

    def _check_ingredient(self, ingredient: dict, age_months: int) -> list[dict]:
        """对单一配料执行规则检查"""
        results = []
        for check_fn in [
            check_added_sugar,
            check_added_salt,
            check_artificial_additive,
        ]:
            result = check_fn(ingredient, age_months)
            if result.tag != "suitable":
                results.append({
                    "tag": result.tag,
                    "reason": result.reason,
                    "rule": result.rule_name,
                })

        risk_result = check_ingredient_risk_level(ingredient, age_months)
        if risk_result.tag != "suitable":
            results.append({
                "tag": risk_result.tag,
                "reason": risk_result.reason,
                "rule": risk_result.rule_name,
            })

        if not results:
            results.append({"tag": "suitable", "reason": "安全"})
        return results
