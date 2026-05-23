"""pytest 共享 fixtures"""

import pytest
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def kb():
    """提供 JSON 后端知识库实例（测试用）"""
    from kb.json_backend import JSONKnowledgeBase
    return JSONKnowledgeBase()


@pytest.fixture
def sample_baby_profile():
    """测试用宝宝画像"""
    return {
        "age_months": 6,
        "allergies": ["鸡蛋"],
        "feeding_method": "breast",
        "tried_foods": ["胡萝卜", "南瓜"],
        "feeding_history": [],
    }


@pytest.fixture
def sample_food():
    """测试用食材：猪肝"""
    return {
        "id": "food_001",
        "name_zh": "猪肝",
        "category": "red_meat",
        "nutrients": {"铁": {"value": 22.6, "unit": "mg/100g"}},
        "allergen": None,
        "min_age_months": 6,
        "texture_stage": "puree",
        "iron_rich": True,
        "tags": ["高铁"],
    }


@pytest.fixture
def sample_allergen_food():
    """测试用食材：鸡蛋（过敏原）"""
    return {
        "id": "food_002",
        "name_zh": "鸡蛋",
        "category": "eggs",
        "nutrients": {"蛋白质": {"value": 13.3, "unit": "g/100g"}},
        "allergen": "鸡蛋",
        "min_age_months": 6,
        "texture_stage": "puree",
        "iron_rich": False,
        "tags": ["高蛋白"],
    }
