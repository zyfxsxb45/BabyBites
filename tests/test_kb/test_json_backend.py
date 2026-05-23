"""知识库 JSON 后端测试"""

import pytest


class TestJSONKnowledgeBase:
    """测试 JSON 知识库的基本查询"""

    def test_get_food_exists(self, kb):
        food = kb.get_food("food_001")
        assert food is not None
        assert food["name_zh"] == "猪肝"

    def test_get_food_not_found(self, kb):
        assert kb.get_food("nonexistent") is None

    def test_list_foods_by_age(self, kb):
        foods = kb.list_foods_by_age(6)
        assert len(foods) >= 1
        # 所有食材的 min_age_month <= 6
        for f in foods:
            assert f["min_age_months"] <= 6

    def test_list_foods_by_category(self, kb):
        foods = kb.list_foods_by_category("red_meat")
        assert len(foods) >= 1
        for f in foods:
            assert f["category"] == "red_meat"

    def test_get_age_stage(self, kb):
        stage = kb.get_age_stage(6)
        assert stage is not None
        assert "6" in stage.get("age_range", "")

    def test_match_allergen_by_alias(self, kb):
        aid = kb.match_allergen_by_alias("whey")
        # whey 是牛奶的别名
        if aid:
            allergen = kb.get_allergen(aid)
            assert allergen is not None

    def test_get_stats(self, kb):
        stats = kb.get_stats()
        assert stats["foods_count"] > 0
        assert stats["backend"] == "JSON + SQLite"
