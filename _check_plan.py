# -*- coding: utf-8 -*-
"""快验——给 PPT 的数据"""
import sys, json
sys.path.insert(0, ".")
from eval_adapter import evaluate_candidates, generate_plan

profile = {
    "baby_id": "V060702", "age_months": 7,
    "allergies": [], "tried_foods": ["rice cereal", "pumpkin puree"],
    "feeding_method": "mixed", "notes": "",
}
cands = [
    {"food_id": "N0001", "food_name_zh": "强化铁米粉", "ingredient_text": "rice flour, iron, vitamins", "category": "grains", "min_age_months": 6},
    {"food_id": "N0002", "food_name_zh": "南瓜泥", "ingredient_text": "pumpkin", "category": "vegetables", "min_age_months": 6},
    {"food_id": "N0003", "food_name_zh": "鸡肉泥", "ingredient_text": "chicken", "category": "poultry", "min_age_months": 6},
    {"food_id": "N0004", "food_name_zh": "胡萝卜泥", "ingredient_text": "carrot", "category": "vegetables", "min_age_months": 6},
    {"food_id": "N0005", "food_name_zh": "苹果泥", "ingredient_text": "apple", "category": "fruits", "min_age_months": 6},
    {"food_id": "N0006", "food_name_zh": "猪肝泥", "ingredient_text": "pork liver", "category": "red_meat", "min_age_months": 6},
]

# 评测候选选择
ev = evaluate_candidates(profile, cands)
items = ev.get("items", [])
safe = [i for i in items if i["decision"] == "safe"]
caution = [i for i in items if i["decision"] == "caution"]
avoid = [i for i in items if i["decision"] == "avoid"]
print("=== candidate_selection ===")
print(f"total: {len(items)}, safe: {len(safe)}, caution: {len(caution)}, avoid: {len(avoid)}")
for i in items:
    print(f"  {i['food_name_zh']}: {i['decision']} | rules: {i.get('triggered_rule_ids',[])}")

# 周计划
p = generate_plan(profile, cands)
print(f"\n=== meal_plan ===")
print(f"mode: {p.get('mode')}, days: {len(p.get('plan',[]))}")
print(f"pool: {p.get('total_foods_available')}, new: {p.get('new_foods_this_week')}")
print(f"avoid_ids: {p.get('avoid_food_ids')}, reasons: {p.get('avoid_reasons')}")
for d in p.get("plan", [])[:7]:
    print(f"  {d.get('day')}: {d.get('foods')} {'new' if d.get('is_new_food') else ''} | {d.get('serving_note','')}")
