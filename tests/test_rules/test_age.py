"""月龄适龄规则单元测试"""

import pytest
from rules.age import check_age_appropriate, check_strictly_avoided


class TestAgeAppropriate:
    """月龄适龄判断"""

    def test_above_min_age(self, sample_food):
        """月龄大于最低要求 → 通过"""
        result = check_age_appropriate(sample_food, 7)
        assert result.tag == "suitable"

    def test_exact_min_age(self, sample_food):
        """月龄等于最低要求 → 通过"""
        result = check_age_appropriate(sample_food, 6)
        assert result.tag == "suitable"

    def test_below_min_age(self, sample_food):
        """月龄低于最低要求 → avoid"""
        result = check_age_appropriate(sample_food, 4)
        assert result.tag == "avoid"
        assert "4月龄" in result.reason.lower() or "4月" in result.reason

    def test_no_min_age(self):
        """食材无 min_age_months → 通过"""
        food = {"id": "test", "name_zh": "测试"}
        result = check_age_appropriate(food, 0)
        assert result.tag == "suitable"


class TestStrictlyAvoided:
    """严格禁止食物检查"""

    def test_no_kb(self, sample_food):
        """无 KB → 跳过检查"""
        result = check_strictly_avoided(sample_food, 6)
        assert result.tag == "suitable"
