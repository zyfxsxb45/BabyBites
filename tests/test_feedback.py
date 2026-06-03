"""反馈闭环测试"""
import sys, tempfile, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.feedback_store import FeedbackStore
from rules.feedback import apply_feedback_to_food, get_feedback_adjusted_foods

# 临时文件
tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
tmp_path = tmp.name
tmp.close()

store = FeedbackStore(tmp_path)
passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        failed += 1

def test_add_and_query():
    store.add("鸡蛋", "rash", "moderate", notes="脸上红点")
    records = store.get_by_food("鸡蛋")
    assert len(records) == 1
    assert records[0]["severity"] == "moderate"

def test_avoid_foods():
    avoids = store.get_avoid_foods()
    assert "鸡蛋" in avoids

def test_caution_foods():
    store.add("三文鱼", "diarrhea", "mild")
    cautions = store.get_caution_foods()
    assert "三文鱼" in cautions

def test_safe_food():
    label = store.get_food_safety_label("猪肝")
    assert label == "suitable"

def test_avoid_label():
    label = store.get_food_safety_label("鸡蛋")
    assert label == "avoid"

def test_caution_label():
    label = store.get_food_safety_label("三文鱼")
    assert label == "caution"

def test_summary():
    s = store.summary
    assert s["total"] == 2
    assert s["foods_tracked"] == 2

def test_apply_feedback_avoid():
    food = {"name_zh": "鸡蛋"}
    result = apply_feedback_to_food(food, store)
    assert result.tag == "avoid"

def test_apply_feedback_caution():
    food = {"name_zh": "三文鱼"}
    result = apply_feedback_to_food(food, store)
    assert result.tag == "caution"

def test_apply_feedback_safe():
    food = {"name_zh": "猪肝"}
    store.add("猪肝", "none", "mild")
    result = apply_feedback_to_food(food, store)
    assert result.tag == "suitable"

def test_adjusted_foods():
    foods = [
        {"food_data": {"name_zh": "猪肝"}},
        {"food_data": {"name_zh": "鸡蛋"}},
        {"food_data": {"name_zh": "三文鱼"}},
    ]
    adjusted = get_feedback_adjusted_foods(foods, store)
    tags = {a["food_data"]["name_zh"]: a["tag"] for a in adjusted}
    assert tags["鸡蛋"] == "avoid"
    assert tags["三文鱼"] == "caution"
    assert tags["猪肝"] == "suitable"

def test_delete():
    records = store.get_by_food("鸡蛋")
    store.delete(records[0]["id"])
    remaining = store.get_by_food("鸡蛋")
    assert len(remaining) == 0


test("添加并查询", test_add_and_query)
test("避免食材", test_avoid_foods)
test("注意食材", test_caution_foods)
test("安全食材", test_safe_food)
test("标签=avoid", test_avoid_label)
test("标签=caution", test_caution_label)
test("汇总统计", test_summary)
test("反馈规则·避免", test_apply_feedback_avoid)
test("反馈规则·注意", test_apply_feedback_caution)
test("反馈规则·安全", test_apply_feedback_safe)
test("批量调整食材", test_adjusted_foods)
test("删除反馈", test_delete)

print(f"\n  {passed} passed, {failed} failed, {passed+failed} total")

os.unlink(tmp_path)
