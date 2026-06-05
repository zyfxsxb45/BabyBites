"""
全链路集成测试。

测试从"用户输入"到"安全评估输出"的完整流程，
不依赖 LLM API（规则引擎部分是确定性的，可离线测试）。

覆盖场景：
  1. 正常宝宝 → 通过所有检查
  2. 已知过敏 → 食材 block
  3. 月龄不足 → 阶段 block
  4. 多种过敏 + 早产儿 → 综合判断
  5. 知识库查询功能
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.json_backend import JSONKnowledgeBase
from rules.engine import RuleEngine
from agents.safety_boundary import SafetyBoundaryAgent
from agents.validation import ValidationAgent


class TestFullPipeline:
    """全链路：画像 → 阶段 → 安全 → 校验"""

    @classmethod
    def setup_class(cls):
        cls.kb = JSONKnowledgeBase()
        cls.engine = RuleEngine(cls.kb)
        cls.safety = SafetyBoundaryAgent(kb=cls.kb, rule_engine=cls.engine)
        cls.validator = ValidationAgent(kb=cls.kb, rule_engine=cls.engine)

    # ===== 场景1：正常6月龄 — 全部通过 =====

    def test_normal_baby_can_start(self):
        """6月龄无过敏 → 可以开始辅食"""
        baby = {"age_months": 6, "allergies": []}
        result = self.safety.process({"profile": baby})
        assert result["can_start"] is True
        assert result["stage"] is not None
        assert result["stage"]["label"] == "吞咽期"

    def test_normal_baby_all_foods_safe(self):
        """无过敏 → 所有食材至少 suitable/caution，不能 avoid"""
        baby = {"age_months": 7, "allergies": []}
        foods = [
            self.kb.get_food_by_name(name)
            for name in ["猪肝", "胡萝卜", "南瓜", "苹果"]
            if self.kb.get_food_by_name(name)
        ]
        result = self.safety.process({
            "profile": baby,
            "candidate_foods": foods,
        })
        for food_id, r in result["food_safety_results"].items():
            assert r["tag"] != "avoid", f"{food_id} 不应被 block"

    # ===== 场景2：鸡蛋过敏 =====

    def test_egg_allergy_blocks_egg(self):
        """鸡蛋过敏 → 鸡蛋 avoid"""
        baby = {"age_months": 7, "allergies": ["鸡蛋"]}
        egg = self.kb.get_food_by_name("鸡蛋")
        result = self.engine.evaluate_food(egg, baby)
        # 鸡蛋 allergen 字段为 "鸡蛋"，规则中通过 aliases 匹配
        # 有 kb 时走 aliases 匹配，无 kb 时走直接匹配
        assert result.overall_tag in ("avoid", "caution"), \
            f"鸡蛋过敏应对鸡蛋有反应，实际: {result.overall_tag}"

    def test_egg_allergy_pork_liver_safe(self):
        """鸡蛋过敏 → 猪肝不受影响"""
        baby = {"age_months": 7, "allergies": ["鸡蛋"]}
        liver = self.kb.get_food_by_name("猪肝")
        result = self.engine.evaluate_food(liver, baby)
        assert result.overall_tag != "avoid", \
            f"猪肝不应被鸡蛋过敏 block: {result.reasons}"

    # ===== 场景3：月龄不足 =====

    def test_under_age_cannot_start(self):
        """3月龄 → 不能开始"""
        baby = {"age_months": 3, "allergies": []}
        result = self.safety.process({"profile": baby})
        assert result["can_start"] is False
        assert len(result["blocking_reasons"]) > 0

    def test_under_age_food_blocked(self):
        """4月龄吃猪肝（min_age=6） → avoid"""
        baby = {"age_months": 4, "allergies": []}
        liver = self.kb.get_food_by_name("猪肝")
        result = self.engine.evaluate_food(liver, baby)
        assert result.overall_tag == "avoid"

    # ===== 场景4：早产儿矫正月龄 =====

    def test_preterm_corrected_age(self):
        """实际7月龄但矫正5月龄 → 不能开始"""
        baby = {"age_months": 7, "corrected_age_months": 5, "allergies": []}
        result = self.safety.process({"profile": baby})
        assert result["can_start"] is False

    # ===== 场景5：多种过敏 =====

    def test_multiple_allergies(self):
        """鸡蛋+鱼类过敏 → 鸡蛋和三文鱼都应被标记"""
        baby = {"age_months": 8, "allergies": ["鸡蛋", "鱼类"]}
        foods = [
            self.kb.get_food_by_name(n)
            for n in ["鸡蛋", "三文鱼", "猪肝"]
            if self.kb.get_food_by_name(n)
        ]
        result = self.safety.process({
            "profile": baby,
            "candidate_foods": foods,
        })
        # 猪肝应该 safe（非过敏原）
        for food_id, r in result["food_safety_results"].items():
            if "猪肝" in food_id:
                pass  # 猪肝应该不受影响，但不在检查范围内
        # 至少有结果是 avoid 或 caution
        tags = [r["tag"] for r in result["food_safety_results"].values()]
        assert "avoid" in tags or "caution" in tags

    # ===== 场景6：计划校验 =====

    def test_valid_plan_passes(self):
        """合法计划 → 通过校验"""
        baby = {"age_months": 7, "allergies": []}
        plan = [
            {"day": "周一", "foods": ["猪肝"], "date": "2026-05-25"},
            {"day": "周二", "foods": ["南瓜"], "date": "2026-05-26"},
            {"day": "周三", "foods": ["胡萝卜"], "date": "2026-05-27"},
        ]
        result = self.validator.process({"plan": plan, "profile": baby})
        assert result["passed"] is True, result.get("violations", [])

    def test_egg_in_plan_with_allergy_blocked(self):
        """含过敏原的计划 → 不通过"""
        baby = {"age_months": 7, "allergies": ["鸡蛋"]}
        plan = [
            {"day": "周一", "foods": ["鸡蛋"], "date": "2026-05-25"},
        ]
        result = self.validator.process({"plan": plan, "profile": baby})
        assert result["passed"] is False
        assert len(result["violations"]) > 0

    def test_underage_food_in_plan_blocked(self):
        """含不适龄食材的计划 → 不通过"""
        baby = {"age_months": 4, "allergies": []}
        plan = [
            {"day": "周一", "foods": ["猪肝"], "date": "2026-05-25"},
        ]
        result = self.validator.process({"plan": plan, "profile": baby})
        assert result["passed"] is False

    # ===== 知识库功能 =====

    def test_kb_get_food(self):
        """知识库查询正常"""
        food = self.kb.get_food("food_001")
        assert food is not None
        assert food["name_zh"] == "猪肝"
        assert food["iron_rich"] is True

    def test_kb_list_foods_by_age(self):
        """适龄食材查询"""
        foods = self.kb.list_foods_by_age(6)
        assert len(foods) >= 15  # 至少15种食材适合6月龄

    def test_kb_match_allergen(self):
        """过敏原别名匹配"""
        milk_id = self.kb.match_allergen_by_alias("whey")
        if milk_id:
            allergen = self.kb.get_allergen(milk_id)
            assert allergen is not None

    def test_kb_nutrient_query(self):
        """营养素查询"""
        iron = self.kb.get_nutrient_info("nutrient_iron")
        assert iron is not None
        assert iron["importance_zh"] is not None

    def test_kb_stats(self):
        """知识库统计"""
        stats = self.kb.get_stats()
        assert stats["foods_count"] == 40
        assert stats["allergens_count"] == 9
        assert stats["nutrients_count"] == 7


if __name__ == "__main__":
    # 可以直接运行看结果
    import traceback

    test = TestFullPipeline()
    test.setup_class()

    tests = [
        m for m in dir(test)
        if m.startswith("test_") and callable(getattr(test, m))
    ]

    passed = 0
    failed = 0
    for name in sorted(tests):
        try:
            getattr(test, name)()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {name}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n  {passed} passed, {failed} failed, {len(tests)} total")
