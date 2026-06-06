"""
阶段与安全边界智能体。

职责：判断宝宝是否进入辅食阶段，执行硬性安全拦截。
混合模式：规则兜底 + LLM 增强（备注理解）。

输入：宝宝画像
输出：阶段评估 + 安全拦截结果 + 候选食材标签
"""

import re
import json as _json
from .base import RuleAgent
from rules.engine import RuleEngine


class SafetyBoundaryAgent(RuleAgent):
    """阶段判断 + 安全拦截 + 发育信号提取 + 备注过敏理解"""

    # 发育就绪信号关键词
    READINESS_KEYWORDS = {
        "head_control": ["能抬头", "能控制头", "头稳", "脖子有劲", "能坐着"],
        "sits_supported": ["能坐", "能靠着坐", "能倚坐", "坐得稳"],
        "interest_in_food": ["看大人吃饭", "伸手抓", "张嘴", "对食物感兴趣", "流口水"],
        "tongue_thrust_gone": ["不顶舌", "不往外推", "能吞咽", "会咽"],
        "doubled_birth_weight": ["体重翻倍", "体重是出生", "长得快"],
    }

    # 备注中暗示过敏/不耐受的关键词（规则 fallback 用）
    NOTES_ALLERGY_KEYWORDS = [
        "过敏", "不能吃", "不吃", "起疹", "拉肚子", "腹泻", "呕吐",
        "反应", "不舒服", "避免", "忌口", "出疹", "红肿", "湿疹",
        "不耐受", "拉稀", "便秘", "吃了就", "一吃就", "碰不得",
    ]

    # LLM 备注解析的 system prompt
    NOTES_LLM_SYSTEM_PROMPT = """你是婴儿辅食过敏原识别助手。家长在备注中描述了宝宝的饮食情况，你需要从中提取可能过敏或不耐受的食材。

规则：
1. 只返回 JSON 数组，包含需要避免的食材名称，如 ["山药", "鸡蛋"]
2. 注意识别各种自然语言表达：
   - "对XX过敏" → 提取 XX
   - "吃完XX起红疹/拉肚子/呕吐/出疹子" → 提取 XX
   - "XX不能吃/不吃XX/要避免XX" → 提取 XX
   - "XX有反应/XX不耐受/XX吃了不舒服" → 提取 XX
   - "尝试了XX，起了…" → 提取 XX
3. 只从提供的食材列表中选择，不要编造食材名
4. 如果家长说的是"尝试了XX没问题/XX可以吃/XX耐受"，不要加入
5. 如果没有发现任何过敏或不耐受的食材，返回 []
6. 只返回 JSON 数组，不要附加任何解释文字"""

    def __init__(self, kb=None, rule_engine=None, llm=None):
        if rule_engine is None and kb is not None:
            rule_engine = RuleEngine(kb)
        super().__init__(kb=kb, rule_engine=rule_engine)
        self._llm = llm

    def process(self, input_data: dict, **kwargs) -> dict:
        profile = input_data.get("profile", {})
        age_months = profile.get("age_months", 0)
        corrected = profile.get("corrected_age_months")
        effective_age = corrected if corrected is not None else age_months

        # 1. 阶段判断
        can_start, blocking = self._check_readiness(profile)

        # 2. 阶段定义
        stage = self.kb.get_age_stage(effective_age) if self.kb else None

        # 3. 发育信号
        notes = profile.get("notes", "")
        signals = self._extract_readiness_signals(notes)

        # 4. 候选食材安全标签（规则引擎）
        food_results = {}
        candidate_foods = input_data.get("candidate_foods", [])
        for food in candidate_foods:
            food_data = food.get("food_data", food)
            if not food_data:
                continue
            result = self.rule_engine.evaluate_food(food_data, profile, llm=self._llm)
            food_id = food_data.get("id", food_data.get("name_zh", ""))
            food_results[food_id] = {
                "tag": result.overall_tag,
                "reasons": result.reasons,
            }

        # 5. 构建食物名→ID 映射（后续步骤共用）
        food_name_to_ids = {}  # name_zh → [fid, ...]
        for item in candidate_foods:
            fd = item.get("food_data", item)
            fid = fd.get("id", fd.get("name_zh", ""))
            name = fd.get("name_zh", "")
            if name:
                food_name_to_ids.setdefault(name, []).append(fid)
            # 也收录别名
            aliases = fd.get("aliases", []) if isinstance(fd.get("aliases"), list) else []
            for alias in aliases:
                food_name_to_ids.setdefault(alias, []).append(fid)

        # 6. 直接食材名匹配：过敏原列表可能直接包含食材名（如"山药"、"虾仁"）
        allergy_set = set(profile.get("allergies", []))
        direct_avoid_names = set()
        for name in food_name_to_ids:
            if name in allergy_set:
                direct_avoid_names.add(name)
                for fid in food_name_to_ids[name]:
                    fr = food_results.get(fid)
                    if fr and fr["tag"] != "avoid":
                        fr["tag"] = "avoid"
                        fr["reasons"] = fr.get("reasons", []) + [
                            f"家长标注「{name}」为过敏原，自动排除"
                        ]

        # 7. 从备注中提取过敏/不耐受食材（LLM + 规则 fallback）
        notes_avoid_names = set()

        # 7a. LLM 语义理解（优先）
        llm_avoid = self._llm_extract_allergies_from_notes(
            notes, candidate_foods=candidate_foods
        )
        notes_avoid_names.update(llm_avoid)

        # 7b. 关键词规则（LLM 的补充 / LLM 不可用时的 fallback）
        keyword_avoid = self._extract_avoid_foods_from_notes(
            notes, candidate_foods=candidate_foods
        )
        notes_avoid_names.update(keyword_avoid)

        # 应用备注提取的避免食材
        for name in notes_avoid_names:
            for fid in food_name_to_ids.get(name, []):
                fr = food_results.get(fid)
                if fr and fr["tag"] != "avoid":
                    fr["tag"] = "avoid"
                    fr["reasons"] = fr.get("reasons", []) + [
                        f"家长备注中提到宝宝对「{name}」过敏或不耐受，自动排除"
                    ]

        # 合并所有来源的 avoid 食材名
        all_avoid_names = direct_avoid_names | notes_avoid_names

        return {
            "can_start": can_start,
            "stage": stage,
            "age_months": age_months,
            "effective_age_months": effective_age,
            "is_preterm_corrected": corrected is not None and corrected != age_months,
            "readiness_signals": signals,
            "readiness_score": len(signals),
            "blocking_reasons": blocking,
            "food_safety_results": food_results,
            "notes_avoid_foods": list(all_avoid_names),  # 包含直接匹配+备注提取
            "direct_avoid_foods": list(direct_avoid_names),  # 直接过敏原匹配
            "recommendation": self._generate_recommendation(
                can_start, effective_age, stage, signals, blocking
            ),
        }

    def _check_readiness(self, profile: dict) -> tuple[bool, list[str]]:
        """
        检查是否具备辅食条件。

        条件：
          1. 矫正月龄 ≥ 6 个月 → 可以开始
          2. 矫正月龄 4-5 个月 → 需有明显发育信号 + 医生建议
          3. 矫正月龄 < 4 个月 → 绝对不能
        """
        age = profile.get("age_months", 0)
        corrected = profile.get("corrected_age_months")
        effective = corrected if corrected is not None else age
        blocking = []

        if effective < 4:
            blocking.append(
                f"宝宝矫正月龄仅 {effective} 个月，远未到辅食添加标准（≥6个月）。任何情况下4月龄以内不应添加辅食。"
            )
            return False, blocking

        if effective < 6:
            # 4-5 月龄：需有明显就绪信号
            notes = profile.get("notes", "")
            signals = self._extract_readiness_signals(notes)
            if len(signals) < 3:
                blocking.append(
                    f"宝宝矫正月龄 {effective} 个月，尚未满 6 个月。"
                    f"只有在宝宝具备明显发育就绪信号（能坐、对食物感兴趣、不顶舌等）"
                    f"且经儿科医生评估后才可考虑提前添加辅食。"
                )
                return False, blocking
            # 有足够信号但月龄偏早：给 caution 但仍允许
            blocking.append(
                f"宝宝矫正月龄 {effective} 个月，接近但未满 6 个月。"
                f"检测到 {len(signals)} 个发育就绪信号，可谨慎尝试，"
                f"建议咨询儿科医生确认。"
            )
            return True, blocking

        # ≥6 个月：可以开始
        return True, blocking

    def _extract_readiness_signals(self, notes: str) -> list[dict]:
        """从家长备注中提取发育就绪信号"""
        if not notes:
            return []

        found = []
        for category, keywords in self.READINESS_KEYWORDS.items():
            for kw in keywords:
                if kw in notes:
                    found.append({
                        "category": category,
                        "keyword": kw,
                        "label": {
                            "head_control": "能控制头部",
                            "sits_supported": "能靠着坐",
                            "interest_in_food": "对食物感兴趣",
                            "tongue_thrust_gone": "能吞咽不顶舌",
                            "doubled_birth_weight": "体重增长良好",
                        }.get(category, category),
                    })
                    break  # 每类只取第一个匹配

        return found

    # ===== 备注过敏提取（LLM + 规则）=====

    def _llm_extract_allergies_from_notes(
        self, notes: str, candidate_foods: list = None
    ) -> set[str]:
        """
        使用 LLM 从备注中提取过敏/不耐受食材。

        LLM 能理解自然语言描述，如"吃完山药起红疹"→山药过敏，
        这是纯关键词匹配做不到的。
        """
        if not notes or not self._llm:
            return set()

        # 收集食材名（优先 candidate_foods，fallback 到 KB 全部食材）
        all_names = set()
        if candidate_foods:
            for item in candidate_foods:
                fd = item.get("food_data", item)
                name = fd.get("name_zh", "")
                if name:
                    all_names.add(name)
        if not all_names and self.kb:
            try:
                all_names = {f.get("name_zh", "") for f in self.kb.list_all_foods() if f.get("name_zh")}
            except Exception:
                pass

        if not all_names:
            return set()

        food_list = "、".join(sorted(all_names))

        user_message = (
            f"可选的食材列表（只能从这里选）：\n{food_list}\n\n"
            f"家长的备注内容：\n{notes}\n\n"
            f"请分析备注中提到了哪些食材可能导致过敏或不耐受，返回 JSON 数组。"
        )

        try:
            response = self._llm.chat(self.NOTES_LLM_SYSTEM_PROMPT, user_message)
            response = response.strip()

            # 清理 markdown 代码块
            if "```" in response:
                parts = response.split("```")
                response = parts[1] if len(parts) > 1 else parts[0]
                if response.startswith("json"):
                    response = response[4:]
                response = response.strip()

            result = _json.loads(response)
            if isinstance(result, list):
                # 只保留在已知食材名中的结果
                return {item for item in result if isinstance(item, str) and item in all_names}
        except Exception:
            pass

        return set()

    def _extract_avoid_foods_from_notes(
        self, notes: str, candidate_foods: list = None
    ) -> set[str]:
        """
        规则 fallback：从家长备注中关键词匹配过敏/不耐受食材。

        策略：扫描备注中出现的所有已知食材名，检查其附近是否
        有过敏/不耐受相关关键词。若匹配，则将该食材加入需避免清单。
        """
        if not notes:
            return set()

        found = set()
        all_food_names = set()
        if candidate_foods:
            for item in candidate_foods:
                fd = item.get("food_data", item)
                name = fd.get("name_zh", "")
                if name:
                    all_food_names.add(name)

        if not all_food_names and self.kb:
            try:
                all_food_names = {f.get("name_zh", "") for f in self.kb.list_all_foods() if f.get("name_zh")}
            except Exception:
                pass

        # 按长度降序，优先匹配长名称
        sorted_names = sorted(all_food_names, key=len, reverse=True)

        for name in sorted_names:
            if name not in notes:
                continue
            idx = notes.find(name)
            start = max(0, idx - 20)
            end = min(len(notes), idx + len(name) + 20)
            context = notes[start:end]
            if any(kw in context for kw in self.NOTES_ALLERGY_KEYWORDS):
                found.add(name)

        return found

    # ===== 建议生成 =====

    def _generate_recommendation(
        self, can_start: bool, age: int, stage: dict,
        signals: list, blocking: list,
    ) -> str:
        """生成人类可读的建议"""
        if can_start and len(blocking) == 0:
            return (
                f"✅ 宝宝（矫正月龄 {age} 个月）已具备辅食添加条件。"
                f"当前阶段：{stage.get('label', '')}（{stage.get('age_range', '')}）。"
                f"质地以 {stage.get('texture', '')} 为主。"
            )
        elif can_start and blocking:
            return f"⚠️ 可以尝试辅食，但需注意：{' '.join(blocking)}"
        else:
            return f"🚫 暂不建议添加辅食。{' '.join(blocking)}"
