"""
知识库接口定义。

使用 Protocol 而非 ABC——遵循 Python 的"鸭子类型"哲学。
任何实现了这些方法的对象都可以作为知识库后端使用，
不需要显式继承。这让 json_backend 和 neo4j_backend 可以
完全独立开发，只需保证方法签名一致即可。

上层（rules、agents）只依赖这个接口，不依赖具体实现。
切换后端只需在 factory.py 改一行。
"""

from typing import Protocol, Optional


class KnowledgeBase(Protocol):
    """知识库接口协议。

    定义了规则引擎和智能体需要查询的所有方法。
    每个方法标注了它在规则引擎或智能体中的使用场景。
    """

    # ===== 食材查询 =====
    # 使用场景：阶段判断、过敏拦截、计划生成

    def get_food(self, food_id: str) -> Optional[dict]:
        """按 ID 获取单一食材的完整信息。

        Returns:
            dict with keys: id, name_zh, category, nutrients,
            allergen, min_age_months, texture_stage, iron_rich, tags...
            未找到返回 None
        """
        ...

    def get_food_by_name(self, name_zh: str) -> Optional[dict]:
        """按中文名模糊匹配食材"""
        ...

    def list_foods_by_age(self, age_months: int) -> list[dict]:
        """查询所有适龄食材。

        返回 min_age_months <= age_months 的所有食材。
        用于计划生成时构建候选食材池。
        """
        ...

    def list_foods_by_category(self, category: str) -> list[dict]:
        """查询某一类别下的所有食材。

        category: 'red_meat', 'vegetables', 'fish' 等
        用于营养多样性检查。
        """
        ...

    def list_foods_by_tag(self, tag: str) -> list[dict]:
        """按标签查询食材。

        tag: '高铁', '高锌', '高DHA' 等
        用于目标导向的食物推荐。
        """
        ...

    def find_substitutes(self, food_id: str) -> list[dict]:
        """查找对等替代食材。

        用于计划生成时做多样性替换。
        """
        ...

    # ===== 过敏原查询 =====
    # 使用场景：过敏拦截、配料表解析

    def get_allergen(self, allergen_id: str) -> Optional[dict]:
        """获取过敏原详情。

        Returns:
            dict with: id, category, aliases, cross_reactive, hidden_sources, severity
        """
        ...

    def list_allergens(self) -> list[dict]:
        """列出所有已知过敏原"""
        ...

    def match_allergen_by_alias(self, text: str) -> Optional[str]:
        """根据别名文本匹配过敏原 ID。

        输入 'whey' → 返回 'allergen_002' (牛奶)
        输入 '卵白蛋白' → 返回 'allergen_001' (鸡蛋)
        用于配料表解析时识别隐藏过敏原。
        """
        ...

    # ===== 月龄阶段查询 =====
    # 使用场景：阶段判断、质地匹配

    def get_age_stage(self, age_months: int) -> Optional[dict]:
        """根据月龄返回对应阶段定义。

        6-8 → stage_6_8, 9-11 → stage_9_11, 12+ → stage_12_plus
        """
        ...

    # ===== 营养数据查询 =====
    # 使用场景：营养缺口检测、成本-营养排序

    def get_nutrient_info(self, nutrient_id: str) -> Optional[dict]:
        """获取营养素定义和每日需求量"""
        ...

    def list_nutrients(self) -> list[dict]:
        """列出所有追踪的营养素"""
        ...

    # ===== 商品/配料查询（SQLite 或 Neo4j）=====
    # 使用场景：标签解析、商品推荐

    def get_product(self, product_id: str) -> Optional[dict]:
        """获取商品详情（含配料和营养成分）"""
        ...

    def get_ingredient(self, ingredient_id: str) -> Optional[dict]:
        """获取配料/成分详情"""
        ...

    def match_ingredient_by_name(self, name: str) -> Optional[dict]:
        """按名称模糊匹配配料。

        用于配料表解析：把 LLM 切分出的成分名称匹配到 ingredients 表。
        """
        ...

    def list_products_by_age(self, age_months: int) -> list[dict]:
        """查询适龄商品"""
        ...

    # ===== 图查询（Neo4j 专有，JSON 后端提供等价实现）=====

    def find_foods_rich_in(self, nutrient_id: str, age_months: int) -> list[dict]:
        """查找富含某营养素且适龄的食材。

        在图中：MATCH (f:Food)-[:CONTAINS]->(n:Nutrient {id: $nutrient_id})
                WHERE f.min_age <= $age_months AND f.iron_rich = true (for iron)
              RETURN f
        在 JSON 中：遍历 foods 做 filter
        """
        ...

    def check_path_to_allergen(self, product_id: str, allergen_id: str) -> bool:
        """检查商品是否含有某过敏原（含别名匹配）。

        在图中检查 (Product)-[:CONTAINS_INGREDIENT]->(Ingredient)-[:IS_ALLERGEN]->(Allergen)
        在 JSON 中查 allergens.json 的 aliases 字段
        这是一个典型的"路径可达性"图查询。
        """
        ...
