"""精确统计数据"""
import json

BASE = "D:/课程文件/大二下/人工智能导论/AI系统实践/宝宝巴适/data/knowledge"

with open(f"{BASE}/foods.json", "r", encoding="utf-8") as f:
    foods = json.load(f)
real_foods = {k: v for k, v in foods.items() if isinstance(v, dict) and "category" in v}
print(f"实际食材: {len(real_foods)}")
iron_rich = sum(1 for v in real_foods.values() if v.get("iron_rich"))
allergenic = sum(1 for v in real_foods.values() if v.get("potential_allergen"))
print(f"  高铁: {iron_rich}, 潜在过敏原: {allergenic}")

with open(f"{BASE}/allergens.json", "r", encoding="utf-8") as f:
    al = json.load(f)
real_al = {k: v for k, v in al.items() if isinstance(v, dict) and "aliases" in v}
print(f"过敏原: {len(real_al)}, names: {list(real_al.keys())}")
umbrella = al.get("umbrella_terms", {})
print(f"umbrella terms: {len(umbrella)}")

with open(f"{BASE}/age_stages.json", "r", encoding="utf-8") as f:
    st = json.load(f)
real_st = {k: v for k, v in st.items() if isinstance(v, dict) and "age_range" in v}
print(f"月龄阶段: {len(real_st)}, names: {[v.get('label','') for v in real_st.values()]}")

with open(f"{BASE}/food_categories.json", "r", encoding="utf-8") as f:
    cats = json.load(f)
real_cats = {k: v for k, v in cats.items() if isinstance(v, dict) and "name_zh" in v}
print(f"食材类别: {len(real_cats)}, names: {[v.get('name_zh','') for v in real_cats.values()]}")

with open(f"{BASE}/nutrients.json", "r", encoding="utf-8") as f:
    nu = json.load(f)
real_nu = {k: v for k, v in nu.items() if isinstance(v, dict) and "unit" in v}
print(f"营养素: {len(real_nu)}, names: {list(real_nu.keys())}")
