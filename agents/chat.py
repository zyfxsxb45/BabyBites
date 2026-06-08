"""
Chat 智能问答智能体。

职责：回答用户关于婴儿辅食、营养、过敏、喂养技巧的自由提问。
与工作流智能体不同，Chat 是无固定流程的自由对话。

工作方式：
  1. 分析用户问题中的关键词（食材名、营养素名、过敏原名等）
  2. 从知识库检索相关知识片段
  3. 拼装上下文 → LLM 生成回答
  4. 标注信息来源
"""

from typing import Optional
from .base import LLMAgent

# Chat 专用系统提示词
SYSTEM_PROMPT = """你是一个婴儿辅食与喂养助手，名字是"宝宝巴适"。
你的知识来源于国际权威机构（CDC、WHO、FSANZ、Codex、EU法规）的指南和标准。

回答问题时请遵守以下原则：

1. **基于知识**：根据提供的知识库内容回答，引用具体数据和来源。
2. **不编造**：如果知识库没有相关信息，诚实告知"我目前没有这方面的资料"。
3. **不诊断**：涉及宝宝疾病、过敏反应、发育异常等问题，必须引导家长咨询儿科医生。
4. **温和专业**：语气温暖但不夸张，用家长能听懂的语言解释专业术语。
5. **简洁**：回答控制在 150 字左右，除非问题复杂需要详细解释。

以下是当前知识库中与用户问题相关的信息：
---
{context}
---

请根据以上信息回答用户问题。如果以上信息不足以回答，可以结合你的通用知识补充，
但要明确区分哪些来自知识库、哪些来自通用知识。"""

# 免责声明
MEDICAL_DISCLAIMER = "\n\n---\n⚠️ 以上内容仅供参考，不构成医疗建议。如有疑问请咨询儿科医生。"


class ChatAgent(LLMAgent):
    """智能问答智能体"""

    def __init__(self, kb=None, llm=None, rag=None):
        super().__init__(kb=kb, llm=llm)
        self.rag = rag

        # 工具定义：名称 → (关键词列表, 处理函数)
        self._tools: dict[str, tuple[list[str], callable]] = {
            "查食材": (
                ["是什么", "能吃", "可以吃", "能不能", "营养", "含", "食材", "食物", "介绍"],
                lambda name: self._tool_lookup_food(name),
            ),
            "查过敏原": (
                ["过敏", "致敏", "过敏原"],
                lambda name: self._tool_lookup_allergen(name),
            ),
            "查适龄食材": (
                ["适龄", "可以吃哪些", "推荐", "适合", "月龄"],
                lambda age: self._tool_list_by_age(age),
            ),
            "评估食材": (
                ["能不能吃", "可以吃吗", "安全吗", "能不能喂"],
                lambda name, profile=None: self._tool_evaluate_food(name, profile),
            ),
        }

    def _dispatch_tools(self, message: str, profile: dict = None) -> str:
        """
        根据消息内容自动调用合适的工具，返回工具执行结果文本。
        匹配策略：同时命中工具名关键词 + 消息包含食材/过敏原名 → 才触发。
        """
        tool_results = []

        # 提取消息中可能的实体名
        food_names = self._extract_food_names(message)
        allergen_names = self._extract_allergen_names(message)
        age_match = self._extract_age(message)

        for tool_name, (keywords, handler) in self._tools.items():
            if not any(kw in message for kw in keywords):
                continue

            if tool_name in ("查食材", "评估食材"):
                for name in food_names[:3]:  # 最多查3个
                    try:
                        result = handler(name) if tool_name == "查食材" else handler(name, profile)
                        if result:
                            tool_results.append(f"[{tool_name}] {name}:\n{result}")
                    except Exception:
                        pass

            elif tool_name == "查过敏原":
                for name in allergen_names[:2]:
                    try:
                        result = handler(name)
                        if result:
                            tool_results.append(f"[{tool_name}] {name}:\n{result}")
                    except Exception:
                        pass

            elif tool_name == "查适龄食材" and age_match:
                try:
                    result = handler(age_match)
                    if result:
                        tool_results.append(f"[{tool_name}] {age_match}月龄:\n{result}")
                except Exception:
                    pass

        return "\n\n".join(tool_results) if tool_results else ""

    def _extract_food_names(self, text: str) -> list[str]:
        """从消息中提取食材名"""
        if not self.kb:
            return []
        found = []
        for food in self.kb.list_all_foods():
            name = food.get("name_zh", "")
            if name and name in text:
                found.append(name)
        return found

    def _extract_allergen_names(self, text: str) -> list[str]:
        """从消息中提取过敏原名"""
        if not self.kb:
            return []
        found = []
        for a in self.kb.list_allergens():
            for alias in a.get("aliases", [])[:3]:
                if alias and alias in text:
                    found.append(alias)
                    break
        return list(set(found))

    def _extract_age(self, text: str) -> int | None:
        """从消息中提取月龄"""
        import re
        m = re.search(r'(\d+)\s*个?\s*月', text)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)\s*岁', text)
        if m:
            return int(m.group(1)) * 12
        return None

    def _tool_lookup_food(self, name: str) -> str:
        food = self.kb.get_food_by_name(name)
        if not food:
            return "未收录该食材"
        parts = [
            f"{food.get('name_zh', '')}（{food.get('category', '')}）",
            f"适合月龄: {food.get('min_age_months', '?')}月起",
            f"铁含量: {'高铁' if food.get('iron_rich') else '普通'}",
        ]
        nutrients = food.get("nutrients", {})
        if nutrients:
            parts.append("营养成分: " + ", ".join(
                f"{k}{v.get('value', '')}{v.get('unit', '')}"
                for k, v in list(nutrients.items())[:3]
            ))
        if food.get("notes_zh"):
            parts.append(f"注意事项: {food['notes_zh']}")
        return "\n".join(parts)

    def _tool_lookup_allergen(self, name: str) -> str:
        aid = self.kb.match_allergen_by_alias(name)
        if not aid:
            return "未收录该过敏原"
        a = self.kb.get_allergen(aid)
        if not a:
            return "未收录"
        parts = [
            f"{name}: {a.get('severity', '')}风险",
            f"常见来源: {', '.join(a.get('hidden_sources', []))}"
        ]
        if a.get("cross_reactive"):
            parts.append(f"交叉过敏: {', '.join(a['cross_reactive'])}")
        return "\n".join(parts)

    def _tool_list_by_age(self, age: int) -> str:
        foods = self.kb.list_foods_by_age(age)
        if not foods:
            return "无适龄食材"
        return f"共 {len(foods)} 种适龄食材: " + "、".join(
            f.get("name_zh", "") for f in foods[:10]
        ) + ("..." if len(foods) > 10 else "")

    def _tool_evaluate_food(self, name: str, profile: dict = None) -> str:
        from rules.engine import RuleEngine
        engine = RuleEngine(self.kb)
        food = self.kb.get_food_by_name(name)
        if not food:
            return f"未收录「{name}」"
        result = engine.evaluate_food(food, profile or {})
        return f"判定: {result.overall_tag} | {'; '.join(result.reasons[:3])}"

    def extract_profile_insights(self, message: str, current_profile: dict = None) -> dict:
        """
        从用户的对话消息中提取可能影响 profile 的信息。
        返回结构化的 profile 增量更新，供调用方合并。
        """
        if not self.llm:
            return {}

        known_allergens = ["鸡蛋", "牛奶", "花生", "鱼类", "虾", "大豆", "小麦", "坚果", "芝麻"]
        prompt = f"""用户说："{message}"

从用户的话中判断是否提到了以下信息。只返回 JSON：
- new_allergies: 用户新提到的过敏原（从已知列表选：{', '.join(known_allergens)}）
- new_tried_foods: 用户新提到的已尝试食材
- age_update: 用户提到的月龄变化（数字）

如果某项没有新信息，字段留空数组或 null。
只返回 JSON，不要解释。"""
        try:
            result = self._ask_llm_structured(
                system_prompt="你是结构化提取助手。只返回JSON。",
                user_message=prompt,
                output_schema={"new_allergies": [], "new_tried_foods": [], "age_update": None},
                max_tokens=200,
            )
            insights = {}
            if isinstance(result, dict):
                if result.get("new_allergies"):
                    insights["allergies"] = list(set(
                        (current_profile or {}).get("allergies", []) + result["new_allergies"]
                    ))
                if result.get("new_tried_foods"):
                    insights["tried_foods"] = list(set(
                        (current_profile or {}).get("tried_foods", []) + result["new_tried_foods"]
                    ))
                if result.get("age_update"):
                    insights["age_months"] = int(result["age_update"])
            return insights
        except Exception:
            return {}

    def process(self, input_data: dict, **kwargs) -> dict:
        """
        处理用户问题。

        Args:
            input_data: {
                "message": str,
                "history": list[dict],
                "candidates": list[dict] (可选, 候选食材列表, 传入后Chat会逐项覆盖),
                "current_profile": dict (可选),
            }

        Returns:
            {"answer": str, "sources": list[str], "profile_insights": dict}
        """
        message = input_data.get("message", "").strip()
        if not message:
            return {"answer": "请告诉我你的问题。", "sources": [], "profile_insights": {}}

        # 1. 检索知识库
        context, sources = self._retrieve_knowledge(message)

        # 1.5. 工具调度：检测用户意图，自动调用工作流
        tool_context = self._dispatch_tools(message, input_data.get("current_profile"))
        if tool_context:
            context = (context or "") + "\n\n[工具查询结果]\n" + tool_context

        # 2. RAG 检索标准/指南原文
        rag_context = ""
        if self.rag and self.rag.is_loaded:
            rag_context = self.rag.search_formatted(message, top_k=3)
            if rag_context:
                context = (context or "") + "\n\n" + rag_context
                sources.add("标准/指南原文（RAG检索）")

        # 2. 检查是否为医疗问题 → 附加警告
        is_medical = self._is_medical_question(message)

        # 3. 拼装 prompt
        prompt = SYSTEM_PROMPT.format(context=context or "暂无直接相关的知识库条目。")
        current_profile = input_data.get("current_profile") or {}
        if current_profile:
            prompt += (
                "\n\n当前宝宝画像（用于个性化回答；其中“其他过敏/忌口原文”"
                "未经标准过敏原匹配，只能作为家长偏好或待确认信息处理）：\n"
                f"- 月龄：{current_profile.get('age_months', '未提供')}\n"
                f"- 已知过敏原：{', '.join(current_profile.get('allergies', [])) or '无'}\n"
                f"- 其他过敏/忌口原文：{current_profile.get('other_restrictions') or '无'}\n"
                f"- 已尝试食材：{', '.join(current_profile.get('tried_foods', [])) or '无'}\n"
                f"- 备注：{current_profile.get('notes') or '无'}"
            )

        # 4. 如果有对话历史，拼接
        history = input_data.get("history", [])
        if history:
            history_text = "\n".join(
                f"用户：{h.get('question', '')}\n助手：{h.get('answer', '')}"
                for h in history[-5:]  # 只保留最近5轮
            )
            prompt += f"\n\n对话历史：\n{history_text}"

        # 4.5. 候选食材注入：如果传入了候选列表，要求LLM逐项覆盖
        candidates = input_data.get("candidates", [])
        if candidates:
            cand_lines = []
            for c in candidates:
                name = c.get("food_name_zh") or c.get("food_name") or ""
                # 简短的食材元信息
                flags = []
                if c.get("contains_milk"): flags.append("含牛奶")
                if c.get("contains_egg"): flags.append("含鸡蛋")
                if c.get("contains_added_salt"): flags.append("高钠")
                if c.get("contains_added_sugar"): flags.append("含添加糖")
                if c.get("is_choking_risk_candidate"): flags.append("窒息风险")
                flag_str = f"（{', '.join(flags)}）" if flags else ""
                cand_lines.append(f"- {name}{flag_str}")
            prompt += (
                f"\n\n以下候选食材需要逐一分析：\n"
                + "\n".join(cand_lines)
                + "\n\n请在回答中逐项覆盖以上所有候选食材，给出个性化选择建议、风险提醒和理由。"
            )

        # 5. 调用 LLM
        answer = self._ask_llm(system_prompt=prompt, user_message=message)

        # 6. 医疗问题加免责声明
        if is_medical:
            answer += MEDICAL_DISCLAIMER

        # 7. 提取 profile 增量信息
        profile_insights = self.extract_profile_insights(message, input_data.get("current_profile"))

        return {
            "answer": answer,
            "sources": list(sources),
            "profile_insights": profile_insights,
        }

    def _retrieve_knowledge(self, text: str) -> tuple[str, set[str]]:
        """
        从知识库中检索与用户问题相关的知识片段。

        策略：关键词匹配（食材名、营养素名、过敏原名、食品类别等）
        """
        if not self.kb:
            return "", set()

        fragments = []
        sources = set()

        # 1. 匹配食材名称
        foods = self._find_foods_in_text(text)
        for food in foods:
            fragments.append(self._format_food_knowledge(food))
            sources.add(f"食材库: {food.get('name_zh', '')}")

        # 2. 匹配营养素名称
        nutrients = self._find_nutrients_in_text(text)
        for name, info in nutrients.items():
            fragments.append(self._format_nutrient_knowledge(name, info))
            sources.add(f"营养素库: {name}")

        # 3. 匹配过敏原
        allergens = self._find_allergens_in_text(text)
        for name, info in allergens.items():
            fragments.append(self._format_allergen_knowledge(name, info))
            sources.add(f"过敏原库: {name}")

        # 4. 匹配月龄相关
        import re
        age_match = re.search(r'(\d+)\s*个?\s*月', text)
        if age_match:
            age = int(age_match.group(1))
            if 4 <= age <= 12:
                foods_at_age = self.kb.list_foods_by_age(age)
                stage = self.kb.get_age_stage(age)
                if stage:
                    fragments.append(
                        f"【{age}月龄阶段】{stage.get('label', '')}（{stage.get('age_range', '')}）\n"
                        f"质地要求：{stage.get('texture', '')}\n"
                        f"每日餐次：{stage.get('meals_per_day', '')}\n"
                        f"关键营养素：{', '.join(stage.get('key_nutrients', []))}\n"
                        f"严格禁止：{', '.join(stage.get('strictly_avoid', []))}"
                    )
                    sources.add(f"月龄阶段: {stage.get('label', '')}")
                if foods_at_age:
                    food_names = [f.get('name_zh', '') for f in foods_at_age[:8]]
                    fragments.append(f"{age}月龄可尝试的食材：{'、'.join(food_names)}等")
                    sources.add("食材库: 月龄筛选")

        context = "\n\n".join(fragments) if fragments else ""
        return context, sources

    # ===== 文本分析 =====

    def _find_foods_in_text(self, text: str) -> list[dict]:
        """在问题文本中匹配食材名"""
        found = []
        # 遍历食材库关键词做匹配
        all_food_keywords = [
            "猪肝", "鸡蛋", "三文鱼", "菠菜", "胡萝卜",
            "牛肉", "猪肉", "鸡肉", "鳕鱼", "南瓜",
            "西兰花", "豆腐", "苹果", "香蕉", "番茄",
            "土豆", "牛油果", "燕麦", "鸡肝", "小米",
        ]
        for keyword in all_food_keywords:
            if keyword in text:
                food = self.kb.get_food_by_name(keyword)
                if food:
                    found.append(food)
        return found

    def _find_nutrients_in_text(self, text: str) -> dict:
        """匹配营养素名称"""
        nutrient_keywords = {
            "铁": "nutrient_iron", "锌": "nutrient_zinc", "钙": "nutrient_calcium",
            "维生素D": "nutrient_vitd", "VD": "nutrient_vitd", "DHA": "nutrient_dha",
            "蛋白质": "nutrient_protein", "维生素C": "nutrient_vitc", "VC": "nutrient_vitc",
        }
        found = {}
        for keyword, nid in nutrient_keywords.items():
            if keyword.lower() in text.lower():
                info = self.kb.get_nutrient_info(nid) if hasattr(self.kb, 'get_nutrient_info') else None
                if info:
                    found[keyword] = info
        return found

    def _find_allergens_in_text(self, text: str) -> dict:
        """匹配过敏原名称"""
        allergen_keywords = [
            "鸡蛋", "牛奶", "花生", "鱼类", "大豆", "小麦", "坚果", "芝麻",
            "过敏", "过敏原",
        ]
        found = {}
        if self.kb:
            for aid in ["allergen_001", "allergen_002", "allergen_003",
                        "allergen_004", "allergen_005", "allergen_006",
                        "allergen_007", "allergen_008"]:
                allergen = self.kb.get_allergen(aid)
                if not allergen:
                    continue
                for alias in allergen.get("aliases", []):
                    if alias in text:
                        found[allergen.get("id", aid)] = allergen
                        break
        return found

    def _find_nutrient(self, name: str) -> Optional[dict]:
        """按名称查营养素"""
        if not self.kb:
            return None
        for n in self.kb.list_nutrients():
            if n.get("name_zh") == name:
                return n
        return None

    def _find_allergen(self, name: str) -> Optional[dict]:
        if not self.kb:
            return None
        aid = self.kb.match_allergen_by_alias(name)
        return self.kb.get_allergen(aid) if aid else None

    # ===== 格式化知识片段 =====

    def _format_food_knowledge(self, food: dict) -> str:
        """格式化食材知识"""
        name = food.get("name_zh", "")
        category = food.get("category", "")
        min_age = food.get("min_age_months", "")
        allergen = food.get("allergen", "")
        iron = "✅ 高铁食材" if food.get("iron_rich") else ""
        tags = "、".join(food.get("tags", []))
        note = food.get("notes_zh", "")

        nutrients_str = ""
        for n, v in (food.get("nutrients") or {}).items():
            nutrients_str += f"  {n}: {v.get('value', '')}{v.get('unit', '')}\n"

        lines = [f"【{name}】"]
        if category:
            lines.append(f"类别：{category}")
        if min_age:
            lines.append(f"适合月龄：{min_age}月龄+")
        if iron:
            lines.append(iron)
        if tags:
            lines.append(f"标签：{tags}")
        if allergen:
            lines.append(f"⚠️ 过敏原：{allergen}")
        if nutrients_str:
            lines.append("营养成分（每100g）：")
            lines.append(nutrients_str.rstrip())
        if note:
            lines.append(f"建议：{note}")

        return "\n".join(lines)

    def _format_nutrient_knowledge(self, name: str, info: dict) -> str:
        """格式化营养素知识"""
        lines = [f"【{name}】"]
        if info.get("importance_zh"):
            lines.append(f"作用：{info['importance_zh']}")
        if info.get("daily_needs"):
            needs = info["daily_needs"]
            lines.append(f"每日需要量：6-8月 {needs.get('stage_6_8', '?')}{info.get('unit', '')}，"
                         f"9-11月 {needs.get('stage_9_11', '?')}{info.get('unit', '')}，"
                         f"12月+ {needs.get('stage_12_plus', '?')}{info.get('unit', '')}")
        if info.get("rich_sources"):
            lines.append(f"富含来源：{'、'.join(info['rich_sources'])}")
        if info.get("special_notes"):
            lines.append(f"提示：{info['special_notes']}")
        return "\n".join(lines)

    def _format_allergen_knowledge(self, name: str, info: dict) -> str:
        """格式化过敏原知识"""
        lines = [f"【{name}过敏】"]
        if info.get("category"):
            lines.append(f"分类：{info['category']}")
        if info.get("hidden_sources"):
            lines.append(f"常见隐藏来源：{'、'.join(info['hidden_sources'])}")
        if info.get("cross_reactive"):
            lines.append(f"交叉反应：{'、'.join(info['cross_reactive'])}")
        if info.get("notes_zh"):
            lines.append(f"提示：{info['notes_zh']}")
        return "\n".join(lines)

    # ===== 安全边界 =====

    def _is_medical_question(self, text: str) -> bool:
        """判断是否为需要引导就医的医疗问题"""
        medical_keywords = [
            "发烧", "呕吐", "腹泻", "皮疹", "湿疹", "便秘", "拉肚子",
            "过敏了", "长红点", "呼吸困难", "发烧了", "体重不增", "不长个",
            "要不要吃药", "吃什么药", "贫血", "缺钙", "佝偻",
        ]
        return any(kw in text for kw in medical_keywords)
