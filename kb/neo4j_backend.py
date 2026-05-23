"""
Neo4j 知识库实现。

使用 Neo4j 图数据库存储全部知识（食材、营养素、月龄、过敏原、
商品、配料），Cypher 查询替代 JSON/SQLite 的内存遍历。

启用方式：在 .env 中设置 KB_BACKEND=neo4j
前提：先运行 scripts/init_neo4j.py 将 JSON 数据导入 Neo4j

设计原则：
  - 与 json_backend 实现相同的接口方法集
  - 对于食材查询，用 Cypher MATCH 替代 Python 遍历
  - 包过敏路径查（check_path_to_allergen）在图中更自然：
    MATCH (p:Product)-[:HAS_INGREDIENT]->()-[:IS_ALLERGEN]->(a:Allergen)
"""

from typing import Optional
import warnings

from config.settings import NEO4J_CONFIG


class Neo4jKnowledgeBase:
    """
    基于 Neo4j 的知识库后端。

    Neo4j 图模型：
      (:Food) -[:CONTAINS {value, unit}]-> (:Nutrient)
      (:Food) -[:CATEGORY]-> (:FoodCategory)
      (:Food) -[:SUITABLE_STAGE]-> (:AgeStage)
      (:Food) -[:ALLERGEN]-> (:Allergen)
      (:Product) -[:HAS_INGREDIENT]-> (:Ingredient)
      (:Ingredient) -[:IS_ALLERGEN]-> (:Allergen)
    """

    def __init__(self):
        self._driver = None
        self._connect()

    def _connect(self):
        """连接 Neo4j"""
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                NEO4J_CONFIG["uri"],
                auth=(NEO4J_CONFIG["user"], NEO4J_CONFIG["password"]),
            )
            # 测试连接
            self._driver.verify_connectivity()
        except ImportError:
            raise RuntimeError(
                "Neo4j backend requires 'neo4j' package. "
                "Install with: pip install neo4j\n"
                "Or switch to JSON backend: set KB_BACKEND=json in .env"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to connect to Neo4j at {NEO4J_CONFIG['uri']}: {e}\n"
                "Make sure Neo4j is running and credentials are correct.\n"
                "Or switch to JSON backend: set KB_BACKEND=json in .env"
            )

    def _run(self, query: str, **params) -> list:
        """执行 Cypher 查询并返回记录列表"""
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    # ===== 食材查询 =====

    def get_food(self, food_id: str) -> Optional[dict]:
        results = self._run(
            "MATCH (f:Food {id: $id}) RETURN f",
            id=food_id,
        )
        return results[0]["f"] if results else None

    def get_food_by_name(self, name_zh: str) -> Optional[dict]:
        results = self._run(
            "MATCH (f:Food {name_zh: $name}) RETURN f",
            name=name_zh,
        )
        return results[0]["f"] if results else None

    def list_foods_by_age(self, age_months: int) -> list[dict]:
        results = self._run(
            "MATCH (f:Food) WHERE f.min_age_months <= $age RETURN f",
            age=age_months,
        )
        return [r["f"] for r in results]

    def list_foods_by_category(self, category: str) -> list[dict]:
        results = self._run(
            "MATCH (f:Food {category: $cat}) RETURN f",
            cat=category,
        )
        return [r["f"] for r in results]

    def list_foods_by_tag(self, tag: str) -> list[dict]:
        results = self._run(
            "MATCH (f:Food) WHERE $tag IN f.tags RETURN f",
            tag=tag,
        )
        return [r["f"] for r in results]

    def find_substitutes(self, food_name: str) -> list[dict]:
        results = self._run("""
            MATCH (f:Food {name_zh: $name})-[:SUBSTITUTE]->(alt:Food)
            RETURN alt
        """, name=food_name)
        return [r["alt"] for r in results]

    # ===== 过敏原查询 =====

    def get_allergen(self, allergen_id: str) -> Optional[dict]:
        results = self._run(
            "MATCH (a:Allergen {id: $id}) RETURN a",
            id=allergen_id,
        )
        return results[0]["a"] if results else None

    def list_allergens(self) -> list[dict]:
        results = self._run("MATCH (a:Allergen) RETURN a")
        return [r["a"] for r in results]

    def match_allergen_by_alias(self, text: str) -> Optional[str]:
        results = self._run("""
            MATCH (a:Allergen)
            WHERE $text IN a.aliases
            RETURN a.id AS id
        """, text=text.lower())
        return results[0]["id"] if results else None

    # ===== 月龄阶段 =====

    def get_age_stage(self, age_months: int) -> Optional[dict]:
        results = self._run("""
            MATCH (s:AgeStage)
            WHERE s.min_age <= $age AND s.max_age >= $age
            RETURN s
        """, age=age_months)
        return results[0]["s"] if results else None

    # ===== 营养数据 =====

    def get_nutrient_info(self, nutrient_id: str) -> Optional[dict]:
        results = self._run(
            "MATCH (n:Nutrient {id: $id}) RETURN n",
            id=nutrient_id,
        )
        return results[0]["n"] if results else None

    def list_nutrients(self) -> list[dict]:
        results = self._run("MATCH (n:Nutrient) RETURN n")
        return [r["n"] for r in results]

    # ===== 商品/配料 =====

    def get_product(self, product_id: str) -> Optional[dict]:
        results = self._run("""
            MATCH (p:Product {id: $id})
            OPTIONAL MATCH (p)-[:HAS_INGREDIENT]->(i:Ingredient)
            RETURN p, collect(i) AS ingredients
        """, id=product_id)
        if not results:
            return None
        r = results[0]
        product = dict(r["p"])
        product["ingredients"] = [dict(i) for i in r["ingredients"] if i]
        return product

    def get_ingredient(self, ingredient_id: str) -> Optional[dict]:
        results = self._run(
            "MATCH (i:Ingredient {id: $id}) RETURN i",
            id=ingredient_id,
        )
        return results[0]["i"] if results else None

    def match_ingredient_by_name(self, name: str) -> Optional[dict]:
        results = self._run(
            "MATCH (i:Ingredient) WHERE i.name = $name OR i.name_en = $name RETURN i",
            name=name,
        )
        return results[0]["i"] if results else None

    def list_products_by_age(self, age_months: int) -> list[dict]:
        results = self._run("""
            MATCH (p:Product)
            WHERE toInteger(p.suggested_age_months) <= $age
            RETURN p
        """, age=age_months)
        return [r["p"] for r in results]

    # ===== 图查询（Neo4j 原生优势）=====

    def find_foods_rich_in(self, nutrient_name: str, age_months: int) -> list[dict]:
        results = self._run("""
            MATCH (f:Food)-[:CONTAINS]->(n:Nutrient {name_zh: $nutrient})
            WHERE f.min_age_months <= $age
            RETURN f
        """, nutrient=nutrient_name, age=age_months)
        return [r["f"] for r in results]

    def check_path_to_allergen(self, product_id: str, allergen_id: str) -> bool:
        """路径可达性：检查商品是否（通过配料）关联到过敏原。
        这是 Neo4j 比 JSON 后端表达更自然的查询：
        一条 MATCH 即完成任务。
        """
        results = self._run("""
            MATCH (p:Product {id: $pid})-[:HAS_INGREDIENT]->(i:Ingredient)
            WHERE i.allergen_id = $aid OR $aid IN i.cross_allergens
            RETURN i LIMIT 1
        """, pid=product_id, aid=allergen_id)
        return len(results) > 0

    # ===== 工具方法 =====

    def get_stats(self) -> dict:
        """获取知识库统计信息（仅统计本项目节点）"""
        counts = {}
        for label in ["Food", "Allergen", "Nutrient", "AgeStage", "Product", "Ingredient"]:
            r = self._run(
                f"MATCH (n:{label}:BabyBites) RETURN count(n) AS cnt"
            )
            counts[label] = r[0]["cnt"] if r else 0
        return {**counts, "backend": "Neo4j"}

    def close(self):
        """关闭驱动连接"""
        if self._driver:
            self._driver.close()
