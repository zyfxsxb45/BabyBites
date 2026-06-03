"""
规则引擎补充测试：质地/排敏/营养/添加剂/成本

可直接运行，不依赖 pytest。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kb.json_backend import JSONKnowledgeBase
from datetime import date, timedelta


kb = JSONKnowledgeBase()
passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except AssertionError as e:
        print(f"  ❌ {name}: {e}")
        failed += 1
    except Exception as e:
        print(f"  💥 {name}: {e}")
        failed += 1


# ============================================================
# 质地匹配规则
# ============================================================
from rules.texture import check_texture_match

def test_texture_match():
    food = kb.get_food_by_name("猪肝")  # texture_stage="puree"
    result = check_texture_match(food, 7, kb=kb)
    assert result.tag == "suitable", f"猪肝(puree)应适合7月龄(puree): {result.tag}"

def test_texture_mismatch():
    # 9-11月是碎末状，如果食物仍是泥糊状，应该通过或caution（可降级处理）
    food = kb.get_food_by_name("猪肝")
    result = check_texture_match(food, 10, kb=kb)
    assert result.tag in ("suitable", "caution"), f"不应该 avoid: {result.tag}"


# ============================================================
# 排敏间隔规则
# ============================================================
from rules.interval import check_new_food_interval

def test_no_history_ok():
    food = kb.get_food_by_name("猪肝")
    result = check_new_food_interval(food, [], date.today(), kb=kb)
    assert result.tag == "suitable"

def test_interval_too_soon():
    food = kb.get_food_by_name("苹果")
    history = [{"date": date.today() - timedelta(days=1), "is_new_food": True, "food_id": "food_010"}]
    result = check_new_food_interval(food, history, date.today(), kb=kb)
    assert result.tag == "caution", f"间隔不足应 caution: {result.tag}"

def test_interval_ok():
    food = kb.get_food_by_name("苹果")
    history = [{"date": date.today() - timedelta(days=4), "is_new_food": True, "food_id": "food_010"}]
    result = check_new_food_interval(food, history, date.today(), kb=kb)
    assert result.tag == "suitable", f"间隔4天应通过: {result.tag}"


# ============================================================
# 营养多样性规则
# ============================================================
from rules.nutrition import check_nutrient_coverage

def test_nutrient_coverage_insufficient():
    plan = [
        {"food_data": kb.get_food_by_name("苹果") or {}},
        {"food_data": kb.get_food_by_name("香蕉") or {}},
    ]
    result = check_nutrient_coverage(plan, 6, kb=kb)
    # 只吃水果 → 缺铁缺锌
    assert result.tag == "caution", f"只吃水果应提示缺营养: {result.tag}"

def test_nutrient_coverage_rich():
    plan = [
        {"food_data": kb.get_food_by_name("猪肝") or {}},
        {"food_data": kb.get_food_by_name("西兰花") or {}},
        {"food_data": kb.get_food_by_name("鸡肉") or {}},
    ]
    result = check_nutrient_coverage(plan, 6, kb=kb)
    assert result.tag == "suitable", f"丰富饮食应通过: {result.reason if hasattr(result, 'reason') else result.tag}"


# ============================================================
# 添加剂规则
# ============================================================
from rules.additive import check_added_sugar, check_added_salt

def test_sugar_check():
    ing = {"name": "白砂糖", "is_added_sugar": True}
    result = check_added_sugar(ing, 6)
    assert result.tag == "avoid", f"6月龄添加糖应 avoid: {result.tag}"

def test_sugar_12m():
    ing = {"name": "白砂糖", "is_added_sugar": True}
    result = check_added_sugar(ing, 13)
    assert result.tag == "caution", f"12月龄以上应 caution: {result.tag}"

def test_salt_check():
    ing = {"name": "食用盐", "is_added_salt": True}
    result = check_added_salt(ing)
    assert result.tag == "avoid", f"添加盐应 avoid: {result.tag}"


# ============================================================
# 成本规则
# ============================================================
from rules.cost import score_cost_nutrient_ratio

def test_cost_ranking():
    foods = [
        {"id": "a", "name_zh": "贵肉", "nutrients": {"铁": {"value": 1.0}}, "price_per_100g": 10.0},
        {"id": "b", "name_zh": "便宜肉", "nutrients": {"铁": {"value": 2.0}}, "price_per_100g": 5.0},
    ]
    ranked = score_cost_nutrient_ratio(foods, "铁")
    assert ranked[0]["name_zh"] == "便宜肉", f"便宜但高铁应排第一: {ranked[0]['name_zh']}"
    assert ranked[1]["name_zh"] == "贵肉"


# ============================================================
# 规则引擎单食材评估
# ============================================================
from rules.engine import RuleEngine

def test_engine_safe_food():
    engine = RuleEngine(kb)
    baby = {"age_months": 7, "allergies": []}
    food = kb.get_food_by_name("猪肝")
    result = engine.evaluate_food(food, baby)
    assert result.is_safe
    assert result.overall_tag == "suitable"

def test_engine_egg_allergy():
    engine = RuleEngine(kb)
    baby = {"age_months": 7, "allergies": ["鸡蛋"]}
    food = kb.get_food_by_name("鸡蛋")
    result = engine.evaluate_food(food, baby)
    assert result.overall_tag in ("avoid", "caution"), f"鸡蛋过敏应触发: {result.overall_tag}"


# ============================================================
# 知识库边缘case
# ============================================================

def test_kb_food_not_found():
    assert kb.get_food("nonexistent_999") is None

def test_kb_food_by_name_not_found():
    assert kb.get_food_by_name("不存在的食材") is None

def test_kb_allergen_list():
    allergens = kb.list_allergens()
    assert len(allergens) >= 8

def test_kb_nutrients_list():
    nutrients = kb.list_nutrients()
    assert len(nutrients) >= 7

def test_kb_substitutes():
    subs = kb.find_substitutes("猪肝")
    assert len(subs) > 0

def test_kb_match_allergen_whey():
    aid = kb.match_allergen_by_alias("whey")
    if aid:
        assert aid == "牛奶", f"whey应匹配牛奶: {aid}"

def test_kb_match_allergen_nonexistent():
    aid = kb.match_allergen_by_alias("zzz_nonexistent_zzz")
    assert aid is None


# ============================================================
# Run
# ============================================================
test("质地匹配", test_texture_match)
test("质地降级", test_texture_mismatch)
test("排敏无历史", test_no_history_ok)
test("排敏间隔不足", test_interval_too_soon)
test("排敏间隔OK", test_interval_ok)
test("营养缺失提示", test_nutrient_coverage_insufficient)
test("营养丰富通过", test_nutrient_coverage_rich)
test("添加糖block", test_sugar_check)
test("添加糖12m+", test_sugar_12m)
test("添加盐block", test_salt_check)
test("成本排序", test_cost_ranking)
test("引擎安全食材", test_engine_safe_food)
test("引擎鸡蛋过敏", test_engine_egg_allergy)
test("KB食材未找到", test_kb_food_not_found)
test("KB名称未找到", test_kb_food_by_name_not_found)
test("KB过敏原列表", test_kb_allergen_list)
test("KB营养素列表", test_kb_nutrients_list)
test("KB替代食材", test_kb_substitutes)
test("KB过敏原匹配whey", test_kb_match_allergen_whey)
test("KB过敏原无匹配", test_kb_match_allergen_nonexistent)

print(f"\n  {passed} passed, {failed} failed, {passed+failed} total")
