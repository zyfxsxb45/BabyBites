"""
标签解析智能体。

职责：解析用户输入的食材/商品配料表，识别成分和风险标签。
策略：优先 LLM 切分 + 正则 fallback + 数据库匹配 + 规则引擎校验。

输入：{"ingredient_text": str, "age_months": int}
输出：{"parsed": [...], "summary": {...}}
"""

import re
from typing import Optional
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
1. 按逗号、顿号、分号、括号切分
2. 括号内是主成分的补充说明（含量/类别/INS编号），合并为一个条目
   例："柠檬酸(330)"→ 柠檬酸，"(含乳清蛋白)"→ 提取乳清蛋白
3. 去掉"食品添加剂"等分类标签词
4. 去掉序号、百分比、"(含...)"等无关信息
5. 只返回成分列表，每行一个，不要附加解释

示例输入：大米(85%), 乳清蛋白, 白砂糖, 柠檬酸(330), 碳酸钙
示例输出：
大米
乳清蛋白
白砂糖
柠檬酸
碳酸钙"""

    def process(self, input_data: dict, **kwargs) -> dict:
        """
        解析配料表。

        Args:
            input_data: {
                "ingredient_text": "大米(85%)、乳清蛋白、白砂糖...",
                "age_months": 6
            }

        Returns:
            {
                "parsed": [{raw_name, matched, ingredient, tags}],
                "risk_summary": {allergens, added_sugars, unknown},
                "total_count": int,
                "matched_count": int,
            }
        """
        ingredient_text = input_data.get("ingredient_text", "")
        age_months = input_data.get("age_months", 6)

        # 1. 切分配料表（LLM 优先，正则 fallback）
        raw_ingredients = self._split_ingredients(ingredient_text)

        # 2. 数据库匹配 + 过敏原别名匹配
        parsed = []
        allergens_found = []
        sugars_found = []

        for name in raw_ingredients:
            entry = {"raw_name": name, "matched": False, "ingredient": None, "tags": []}

            # 数据库精确匹配
            if self.kb:
                entry["ingredient"] = self.kb.match_ingredient_by_name(name)
                if entry["ingredient"]:
                    entry["matched"] = True
                    entry["tags"] = self._check_ingredient(entry["ingredient"], age_months)

            # 过敏原别名匹配（即使数据库没收录，也通过 allergens.json 匹配）
            if not entry["matched"] and self.kb:
                allergen_id = self.kb.match_allergen_by_alias(name)
                if allergen_id:
                    allergen = self.kb.get_allergen(allergen_id) if hasattr(self.kb, 'get_allergen') else None
                    if allergen:
                        entry["matched"] = True
                        entry["ingredient"] = {
                            "name": name,
                            "is_allergen": True,
                            "allergen_id": allergen_id,
                        }
                        entry["tags"] = [{
                            "tag": "avoid" if allergen.get("severity") == "high" else "caution",
                            "reason": f"配料「{name}」是已知过敏原「{allergen_id}」",
                            "rule": "过敏原别名匹配",
                        }]
                        allergens_found.append(name)

            # 添加糖关键字检测（即使数据库没收录）
            if not entry["matched"]:
                if self._looks_like_added_sugar(name):
                    entry["tags"].append({
                        "tag": "avoid" if age_months < 12 else "caution",
                        "reason": f"「{name}」疑似添加糖，婴幼儿应避免",
                        "rule": "添加糖关键词检测",
                    })
                    sugars_found.append(name)

            # 数据库没收录也没匹配到任何规则
            if not entry["tags"]:
                entry["tags"] = [{"tag": "unknown", "reason": f"未收录成分: {name}"}]

            parsed.append(entry)

        # 3. 汇总风险
        risk_items = []
        for p in parsed:
            for t in p["tags"]:
                if t.get("tag") in ("avoid", "caution"):
                    risk_items.append(f"{p['raw_name']}: {t['reason']}")

        return {
            "parsed": parsed,
            "total_count": len(parsed),
            "matched_count": sum(1 for p in parsed if p["matched"]),
            "raw_input": ingredient_text,
            "risk_summary": {
                "allergens": allergens_found,
                "added_sugars": sugars_found,
                "unknown": [p["raw_name"] for p in parsed if not p["matched"]],
                "has_avoid": any(
                    t.get("tag") == "avoid"
                    for p in parsed
                    for t in p["tags"]
                ),
            },
            "risk_items": risk_items,
        }

    # ===== 配料切分 =====

    def _split_ingredients(self, text: str) -> list[str]:
        """
        切分配料表。LLM 优先，失败时回退到正则。

        正则策略：
          1. 去除括号内含量标注（如 "(85%)"）但保留非数字括号内容
          2. 按常见分隔符切分
          3. 清洗噪声词
        """
        # 先试 LLM（如果有 llm 实例）
        if self.llm:
            try:
                response = self._ask_llm(
                    system_prompt=self.SYSTEM_PROMPT,
                    user_message=text,
                )
                if response and len(response.split("\n")) >= 2:
                    return [
                        line.strip()
                        for line in response.strip().split("\n")
                        if line.strip()
                    ]
            except Exception:
                pass  # LLM 不可用，回退到正则

        # 正则 fallback
        return self._split_by_regex(text)

    def _split_by_regex(self, text: str) -> list[str]:
        """纯正则切分配料表，不依赖 LLM"""
        # Step 1: 去掉括号内的数字/百分比标注 "大米(85%)" → "大米"
        text = re.sub(r'\(\s*\d+(?:\.\d+)?\s*%?\s*\)', '', text)

        # Step 2: 按分隔符号切分
        # 中文逗号、顿号、英文逗号、分号、空格逗号组合
        parts = re.split(r'[,，、;；]\s*', text)

        # Step 3: 清洗每个部分
        cleaned = []
        noise_words = {
            "食品添加剂", "食用香料", "营养强化剂", "含有", "含",
            "本品", "本产品", "可能含有", "过敏原信息", "配料",
            "成分", "原料", "添加",
        }

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 去括号内非数字补充说明（如 INS 编号）
            # "柠檬酸(330)" → "柠檬酸"
            # "维生素C(L-抗坏血酸)" → "维生素C"
            part = re.sub(r'\([^)]*\)$', '', part).strip()

            # 跳过纯数字/百分比/空格
            if re.match(r'^[\d.%\s]+$', part):
                continue

            # 跳过噪声词
            if part in noise_words or len(part) <= 1:
                continue

            # 去句号
            part = part.rstrip('.。')

            if part:
                cleaned.append(part)

        return cleaned

    # ===== 配料风险检查 =====

    def _check_ingredient(self, ingredient: dict, age_months: int) -> list[dict]:
        """对单一配料执行规则引擎检查"""
        results = []

        # 数据库标记的规则检查
        for check_fn in [check_added_sugar, check_added_salt, check_artificial_additive]:
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

    # ===== 添加糖关键词检测 =====

    @staticmethod
    def _looks_like_added_sugar(name: str) -> bool:
        """检查名称是否像添加糖（即使数据库未收录也能检测）"""
        sugar_keywords = [
            "白砂糖", "蔗糖", "果糖", "葡萄糖", "麦芽糖", "冰糖", "红糖",
            "糖浆", "蜂蜜", "枫糖", "糖醇", "果汁浓缩", "浓缩果汁",
        ]
        name_lower = name.lower().replace(" ", "")
        return any(kw in name_lower for kw in sugar_keywords)
