#!/usr/bin/env python3
"""
将 JSON 知识库数据导入 Neo4j 图数据库。

前提：Neo4j 服务已启动（bolt://localhost:7687）。
JSON → Neo4j 的映射关系：
  - foods.json → (:Food) 节点
  - age_stages.json → (:AgeStage) 节点
  - allergens.json → (:Allergen) 节点
  - nutrients.json → (:Nutrient) 节点
  - food_categories.json → (:FoodCategory) 节点
  - (:Food)-[:CONTAINS {value, unit}]->(:Nutrient)
  - (:Food)-[:SUITABLE_STAGE]->(:AgeStage) 等

用法：python scripts/init_neo4j.py
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATA_DIR, NEO4J_CONFIG

try:
    from neo4j import GraphDatabase
except ImportError:
    print("Error: neo4j package not installed. Run: pip install neo4j")
    sys.exit(1)


def connect():
    driver = GraphDatabase.driver(
        NEO4J_CONFIG["uri"],
        auth=(NEO4J_CONFIG["user"], NEO4J_CONFIG["password"]),
    )
    driver.verify_connectivity()
    return driver


# 项目标签，确保不会误删其他项目的图数据
PROJECT_LABEL = "BabyBites"


def clear_all(driver):
    """只清空本项目的数据，不影响同一 Neo4j 实例中的其他知识图谱"""
    with driver.session() as session:
        session.run(f"MATCH (n:{PROJECT_LABEL}) DETACH DELETE n")
    print("✓ Cleared existing BabyBites data (other projects unaffected)")


def create_constraints(driver):
    """创建唯一性约束"""
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (f:Food) REQUIRE f.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Allergen) REQUIRE a.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Nutrient) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (s:AgeStage) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:FoodCategory) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.id IS UNIQUE",
    ]
    with driver.session() as session:
        for c in constraints:
            session.run(c)
    print("✓ Constraints created")


def import_foods(driver):
    """导入食材节点"""
    with open(DATA_DIR / "foods.json", encoding="utf-8") as f:
        data = json.load(f)

    foods = {k: v for k, v in data.items() if not k.startswith("_")}

    with driver.session() as session:
        for name, food in foods.items():
            # 创建 Food 节点
            session.run(f"""
                MERGE (f:Food {{id: $id}})
                SET f:{PROJECT_LABEL},
                    f.name_zh = $name_zh,
                    f.name_en = $name_en,
                    f.category = $category,
                    f.min_age_months = $min_age,
                    f.texture_stage = $texture,
                    f.iron_rich = $iron_rich,
                    f.potential_allergen = $potential_allergen,
                    f.tags = $tags
            """,
                id=food["id"],
                name_zh=food.get("name_zh", ""),
                name_en=food.get("name_en", ""),
                category=food.get("category", ""),
                min_age=food.get("min_age_months", 6),
                texture=food.get("texture_stage", "puree"),
                iron_rich=food.get("iron_rich", False),
                potential_allergen=food.get("potential_allergen", False),
                tags=food.get("tags", []),
            )

            # 关联营养素
            for nutrient_name, nutrient_data in food.get("nutrients", {}).items():
                session.run(f"""
                    MERGE (n:Nutrient {{name_zh: $name}})
                    SET n:{PROJECT_LABEL}
                    WITH n
                    MATCH (f:Food {{id: $food_id}})
                    MERGE (f)-[r:CONTAINS]->(n)
                    SET r.value = $value, r.unit = $unit
                """,
                    name=nutrient_name,
                    food_id=food["id"],
                    value=nutrient_data.get("value", 0),
                    unit=nutrient_data.get("unit", ""),
                )

            # 关联过敏原
            if food.get("allergen"):
                allergen_id = food["allergen"]
                session.run(f"""
                    MERGE (a:Allergen {{name_zh: $name}})
                    SET a:{PROJECT_LABEL}
                    WITH a
                    MATCH (f:Food {{id: $food_id}})
                    MERGE (f)-[:ALLERGEN]->(a)
                """, name=allergen_id, food_id=food["id"])

    print(f"✓ Imported {len(foods)} foods")


def import_allergens(driver):
    """导入过敏原节点"""
    with open(DATA_DIR / "allergens.json", encoding="utf-8") as f:
        data = json.load(f)

    allergens = {k: v for k, v in data.items() if not k.startswith("_")}

    with driver.session() as session:
        for name, a in allergens.items():
            session.run(f"""
                MERGE (a:Allergen {{id: $id}})
                SET a:{PROJECT_LABEL},
                    a.name_zh = $name,
                    a.category = $category,
                    a.aliases = $aliases,
                    a.severity = $severity
            """,
                id=a["id"],
                name=name,
                category=a.get("category", ""),
                aliases=a.get("aliases", []),
                severity=a.get("severity", "medium"),
            )

    print(f"✓ Imported {len(allergens)} allergens")


def import_age_stages(driver):
    """导入月龄阶段"""
    with open(DATA_DIR / "age_stages.json", encoding="utf-8") as f:
        data = json.load(f)

    stages = {k: v for k, v in data.items() if not k.startswith("_")}

    with driver.session() as session:
        for sid, s in stages.items():
            range_str = s.get("age_range", "")
            lo, hi = 0, 99
            parts = range_str.replace("月龄", "").replace("以上", "-99").split("-")
            try:
                lo, hi = int(parts[0]), int(parts[1]) if len(parts) > 1 else 99
            except (ValueError, IndexError):
                pass

            session.run(f"""
                MERGE (s:AgeStage {{id: $id}})
                SET s:{PROJECT_LABEL},
                    s.label = $label,
                    s.age_range = $age_range,
                    s.min_age = $lo,
                    s.max_age = $hi,
                    s.texture = $texture,
                    s.meals_per_day = $meals,
                    s.key_nutrients = $nutrients
            """,
                id=s["id"],
                label=s.get("label", ""),
                age_range=range_str,
                lo=lo, hi=hi,
                texture=s.get("texture", ""),
                meals=s.get("meals_per_day", ""),
                nutrients=s.get("key_nutrients", []),
            )

    print(f"✓ Imported {len(stages)} age stages")


def main():
    print("Neo4j Knowledge Graph Initialization")
    print(f"  URI: {NEO4J_CONFIG['uri']}")
    print()

    driver = connect()
    print("✓ Connected to Neo4j\n")

    clear_all(driver)
    create_constraints(driver)
    import_foods(driver)
    import_allergens(driver)
    import_age_stages(driver)

    # 统计
    with driver.session() as session:
        for label in ["Food", "Allergen", "Nutrient", "AgeStage"]:
            r = session.run(
                f"MATCH (n:{label}:{PROJECT_LABEL}) RETURN count(n) AS cnt"
            ).single()
            print(f"  {label}: {r['cnt']} nodes")

    driver.close()
    print("\n✓ Neo4j import complete!")


if __name__ == "__main__":
    main()
