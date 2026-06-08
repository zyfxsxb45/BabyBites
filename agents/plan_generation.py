"""
计划生成与优化智能体。

职责：在安全候选食材池中做约束满足 + 多目标排序，生成周度计划。
混合模式：规则约束 + （可选）LLM 灵活排序。
不依赖 LLM 也能生成基本计划。

输入：候选食材池（已打标签）+ 宝宝画像
输出：周度喂食计划
"""

from datetime import date, timedelta
from typing import Optional
from .base import LLMAgent
from rules.cost import score_cost_nutrient_ratio


class PlanGenerationAgent(LLMAgent):
    """生成周度辅食计划"""

    SYSTEM_PROMPT = """你是一个婴儿辅食计划生成助手。
根据提供的安全食材列表和宝宝信息，生成一周的辅食计划。

规则：
1. 每天1-2种食材
2. 新食材优先安排在周一/周二（留足观察时间）
3. 同类食材不连续两天重复（今天红肉→明天蔬菜→后天谷物）
4. 确保一周内红肉、蔬菜、水果、谷物都有覆盖
5. 输出格式为 JSON 数组：[{"day": "周一", "foods": ["猪肝泥", "米粉"], "is_new_food": true}, ...]
6. 只返回 JSON，不要附加解释"""

    def __init__(self, kb=None, llm=None):
        super().__init__(kb=kb, llm=llm)
        # 食材类别轮换顺序（优先级从高到低）
        self._category_rotation = [
            "red_meat", "vegetables", "grains", "poultry",
            "fish", "fruits", "legumes", "eggs",
        ]

    def process(self, input_data: dict, **kwargs) -> dict:
        """
        生成周度计划或候选评估。

        Args:
            input_data: {
                profile: {age_months, allergies, tried_foods, ...},
                safe_foods: [{food_data, tag}, ...],
                stage: {...},
                mode: "recommend" | "evaluate"  (default: recommend)
            }

            recommend 模式: 从 safe_foods 中生成7天周计划
            evaluate 模式:  对 safe_foods 做逐项评估，返回带标签的候选列表
        """
        profile = input_data.get("profile", {})
        safe_foods = input_data.get("safe_foods", [])
        stage = input_data.get("stage", {})
        mode = input_data.get("mode", "recommend")

        if not safe_foods:
            return {"plan": [], "new_foods_this_week": [], "error": "无可用的安全食材"}

        # evaluate 模式：只做逐项评估，不生成计划
        if mode == "evaluate":
            return self._evaluate_candidates(safe_foods, profile, stage)

        # recommend 模式：生成周计划
        use_llm = input_data.get("use_llm", False) and self.llm is not None
        if use_llm:
            return self._generate_llm_plan(safe_foods, profile, stage)

        ranked = self._constraint_rank(safe_foods, profile)
        new_foods = self._select_new_foods(ranked, profile)
        plan = self._generate_weekly_plan(ranked, new_foods, profile, stage)

        return {
            "plan": plan,
            "new_foods_this_week": [f.get("name_zh", "") for f in new_foods],
            "stage_label": stage.get("label", ""),
            "nutrition_notes": self._get_nutrition_notes(plan),
            "total_foods_available": len(safe_foods),
            "mode": "rule",
        }

    def _generate_llm_plan(self, foods: list, profile: dict, stage: dict) -> dict:
        """
        LLM 模式：让大模型根据安全食材池 + 完整画像生成周计划。
        规则负责安全过滤，LLM 负责排序、多样化、解释。
        """
        age = profile.get("age_months", 6)
        allergies = profile.get("allergies", [])
        tried = profile.get("tried_foods", [])
        notes = profile.get("notes", "")

        # 构建食材清单
        food_lines = []
        for item in foods[:15]:
            fd = item.get("food_data", item)
            name = fd.get("name_zh", "")
            cat = fd.get("category", "")
            iron = "高铁" if fd.get("iron_rich") else ""
            min_age = fd.get("min_age_months", "")
            food_lines.append(f"- {name}（{cat}）{iron}  {min_age}月龄起" if min_age else f"- {name}（{cat}）{iron}")
        food_list = "\n".join(food_lines) if food_lines else "（无可选食材）"

        prompt = f"""你是婴儿辅食周计划生成助手。根据安全食材池和宝宝信息，生成7天辅食计划。

宝宝信息：
- 月龄：{age}个月
- 过敏原：{', '.join(allergies) if allergies else '无'}
- 已尝试食材：{', '.join(tried) if tried else '无'}
- 备注：{notes}
- 阶段：{stage.get('label', '')}（{stage.get('texture', '')}）

安全食材池（只能从这里选，不能加入其他食材）：
{food_list}

要求：
1. 返回纯 JSON 对象，格式为：
{{"plan": [{{"day": "周一", "foods": ["猪肝泥", "米粉"], "is_new_food": true, "serving_note": "从少量开始"}}, ...], "new_foods_this_week": ["猪肝"], "nutrition_notes": ["✅ 高铁食材：猪肝", "✅ 食材类别丰富"]}}
2. 每天安排1-2种食材
3. 新食材优先放周一/周二（留足观察时间）
4. 同类食材不连续两天重复
5. 一周内蔬菜、肉类、谷物、水果都覆盖
6. 避开过敏原
7. 鼓励多样性和逐日变化
8. 只返回 JSON，不附加解释"""

        try:
            result = self._ask_llm_structured(
                system_prompt="你是婴儿辅食计划生成助手。只返回JSON。",
                user_message=prompt,
                output_schema={"plan": [], "new_foods_this_week": [], "nutrition_notes": []},
                max_tokens=1200,
            )
            if isinstance(result, dict) and result.get("plan"):
                # 为 LLM 生成的计划补上 food_details
                llm_plan = result["plan"]
                for day in llm_plan:
                    day["food_details"] = self._build_food_details(
                        day.get("foods", []), stage
                    )
                return {
                    "plan": llm_plan,
                    "new_foods_this_week": result.get("new_foods_this_week", []),
                    "stage_label": stage.get("label", ""),
                    "nutrition_notes": result.get("nutrition_notes", []),
                    "total_foods_available": len(foods),
                    "mode": "llm",
                }
        except Exception:
            pass

        # LLM 失败 → fallback 到规则模式
        ranked = self._constraint_rank(foods, profile)
        new_foods = self._select_new_foods(ranked, profile)
        plan = self._generate_weekly_plan(ranked, new_foods, profile, stage)
        return {
            "plan": plan,
            "new_foods_this_week": [f.get("name_zh", "") for f in new_foods],
            "stage_label": stage.get("label", ""),
            "nutrition_notes": self._get_nutrition_notes(plan),
            "total_foods_available": len(foods),
            "mode": "rule_fallback",
        }

    def _evaluate_candidates(self, foods: list, profile: dict, stage: dict) -> dict:
        """evaluate 模式：逐候选返回评估结果"""
        ranked = self._constraint_rank(foods, profile)
        items = []
        for f in ranked:
            fd = f.get("food_data", f)
            items.append({
                "food_name": fd.get("name_zh", ""),
                "food_name_en": fd.get("name_en", ""),
                "food_id": fd.get("id", ""),
                "score": f.get("_score", 0),
                "category": fd.get("category", ""),
                "iron_rich": fd.get("iron_rich", False),
                "min_age": fd.get("min_age_months"),
                "external": fd.get("_external", False),
            })
        return {
            "mode": "evaluate",
            "items": items,
            "total": len(items),
            "stage_label": stage.get("label", ""),
        }

    # ===== 约束排序 =====

    def _constraint_rank(self, foods: list, profile: dict) -> list:
        """
        多目标排序：
          1. 铁含量高优先（含铁食材置顶）
          2. 按关键营养素覆盖数降序
          3. 同类别分散排列
        """
        age_months = profile.get("age_months", 6)
        stage = self.kb.get_age_stage(age_months) if self.kb else None
        key_nutrients = stage.get("key_nutrients", ["铁"]) if stage else ["铁"]

        # 提取食物数据
        ranked = []
        for item in foods:
            food = item.get("food_data", {}) if isinstance(item, dict) else item
            nutrients = food.get("nutrients", {})

            # 关键营养素覆盖数
            key_count = sum(1 for n in key_nutrients if n in nutrients)

            # 高铁加分
            iron_rich = 2 if food.get("iron_rich") else 0

            ranked.append({
                "food_data": food,
                "_score": iron_rich + key_count,
                "_category": food.get("category", ""),
                "_iron_rich": food.get("iron_rich", False),
            })

        # 按分数降序排序
        ranked.sort(key=lambda x: x["_score"], reverse=True)

        # 同类别不连续：将同类食材分散
        ranked = self._distribute_categories(ranked)

        return ranked

    def _distribute_categories(self, foods: list) -> list:
        """将同类食材分散排列：轮转各类别，避免同类连续出现"""
        by_category = {}
        for f in foods:
            cat = f["_category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(f)

        result = []
        cat_keys = list(by_category.keys())

        # 按轮转顺序排列类别
        ordered_cats = [c for c in self._category_rotation if c in cat_keys]
        ordered_cats += [c for c in cat_keys if c not in self._category_rotation]

        max_len = max(len(by_category.get(c, [])) for c in ordered_cats)

        for i in range(max_len):
            for cat in ordered_cats:
                items = by_category.get(cat, [])
                if i < len(items):
                    result.append(items[i])

        return result

    # ===== 新食材选择 =====

    def _select_new_foods(self, foods: list, profile: dict) -> list:
        """选择本周引入的新食材（已尝试过的优先排除）。支持中英文名。"""
        tried = set(profile.get("tried_foods", []))
        tried_lower = {t.lower() for t in tried}
        result = []
        for f in foods[:10]:
            fd = f.get("food_data", f)
            name_zh = fd.get("name_zh", "")
            name_en = fd.get("name_en", "")
            if name_zh in tried or name_en.lower() in tried_lower:
                continue
            result.append(fd)
            if len(result) >= 3:
                break
        return result

    # ===== 周计划生成 =====

    def _generate_weekly_plan(
        self, foods: list, new_foods: list, profile: dict, stage: dict,
    ) -> list:
        """生成7天逐日计划——从今天开始，day name 对应当天实际星期"""
        meals_per_day = (stage or {}).get("meals_per_day", "2-3次")
        start_date = self._start_date()
        new_food_names = {f.get("name_zh", "") for f in new_foods}
        age_months = profile.get("age_months", 6)
        day_names = ["周一","周二","周三","周四","周五","周六","周日"]

        # 食材队列：新食材在前，已知食材在后
        queue = new_foods + [
            f["food_data"] for f in foods
            if f["food_data"].get("name_zh") not in new_food_names
        ]

        plan = []
        food_idx = 0  # 队列游标
        last_category = None

        for i in range(7):
            day_foods = []
            for _ in range(2):  # 每天挑1-2种
                if food_idx >= len(queue):
                    food_idx = 0  # 循环使用

                candidate = queue[food_idx]
                name = candidate.get("name_zh", "")
                cat = candidate.get("category", "")

                # 跳过今天刚用过的类别（保证多样性）
                if cat == last_category:
                    food_idx += 1
                    if food_idx >= len(queue):
                        food_idx = 0
                    candidate = queue[food_idx]
                    name = candidate.get("name_zh", "")

                if name and name not in day_foods:
                    day_foods.append(name)
                    last_category = cat
                food_idx += 1

            # 新食材优先放前两天
            is_new = any(n in day_foods for n in new_food_names)

            plan_date = start_date + timedelta(days=i)
            plan.append({
                "day": day_names[plan_date.weekday()],
                "date": plan_date.isoformat(),
                "foods": day_foods,
                "is_new_food": is_new,
                "serving_note": f"{meals_per_day}，从少量开始" + (
                    " 🆕新食材，观察3-5天" if is_new else ""
                ),
                "food_details": self._build_food_details(day_foods, stage),
            })

        return plan

    def _build_food_details(self, food_names: list[str], stage: dict) -> dict:
        """为每天的食物构建详情：做法、质地、营养、注意事项"""
        details = {}
        texture_map = {
            "puree": "泥糊状", "mashed": "碎末状",
            "finger_food": "手指食物", "soft": "软烂",
        }
        stage_texture = stage.get("texture", "泥糊状") if stage else "泥糊状"

        for name in food_names:
            food = self.kb.get_food_by_name(name) if self.kb else None
            if not food:
                details[name] = {"notes": "该食材未收录详细信息"}
                continue

            texture = food.get("texture_stage", "")
            texture_zh = texture_map.get(texture, texture)
            notes = food.get("notes_zh", "")
            nutrients = food.get("nutrients", {})
            nutrient_summary = ", ".join(
                f"{k} {v.get('value', '')}{v.get('unit', '')}"
                for k, v in list(nutrients.items())[:4]
            ) if nutrients else ""

            # 组装做法建议
            preparation = notes  # notes_zh 已包含做法和注意事项

            details[name] = {
                "notes": preparation,
                "texture": texture_zh,
                "nutrients": nutrient_summary,
                "stage_note": f"当前阶段建议{stage_texture}，该食材质地为{texture_zh}",
            }
        return details

    def _get_nutrition_notes(self, plan: list) -> list[str]:
        """生成营养说明"""
        notes = []
        all_foods = set()
        for day in plan:
            for f in day.get("foods", []):
                all_foods.add(f)

        # 检查高铁食材是否覆盖
        if self.kb:
            iron_rich_in_plan = [
                n for n in all_foods
                if (food := self.kb.get_food_by_name(n)) and food.get("iron_rich")
            ]
            if iron_rich_in_plan:
                notes.append(f"✅ 本周高铁食材：{'、'.join(iron_rich_in_plan)}")
            else:
                notes.append("⚠️ 本周缺少高铁食材，建议补充猪肝或牛肉")

        # 类别覆盖度
        categories = set()
        for name in all_foods:
            food = self.kb.get_food_by_name(name) if self.kb else None
            if food and food.get("category"):
                categories.add(food["category"])

        if len(categories) >= 4:
            notes.append(f"✅ 食材类别丰富（{'、'.join(sorted(categories))}）")
        elif categories:
            notes.append(f"💡 可增加类别多样性，当前仅覆盖 {len(categories)} 类")

        return notes

    @staticmethod
    def _start_date() -> date:
        """计划起始日期：从今天开始"""
        return date.today()
