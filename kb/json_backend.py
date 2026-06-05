"""
JSON + SQLite 知识库实现。

默认后端，无需安装额外服务。
静态知识（食材、营养素、月龄、过敏原）从 JSON 文件加载到内存。
可变数据（商品、配料）通过 SQLite 查询。

所有查询方法对应 interface.py 中定义的协议。
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

from config.settings import DATA_DIR, DB_PATH


class JSONKnowledgeBase:
    """
    基于 JSON + SQLite 的知识库后端。

    JSON 文件在实例化时一次性加载到内存。
    SQLite 连接按需建立。

    注意：这个类不显式继承 KnowledgeBase Protocol，
    而是通过符合方法签名来满足协议（structural subtyping）。
    这样做的好处是 json_backend 和 neo4j_backend 完全解耦。
    """

    def __init__(self):
        self._foods: dict = {}
        self._age_stages: dict = {}
        self._allergens: dict = {}
        self._nutrients: dict = {}
        self._textures: dict = {}
        self._categories: dict = {}
        self._substitutes: dict = {}
        self._conn: Optional[sqlite3.Connection] = None
        self._load_json_files()
        self._init_db()

    # ===== JSON 加载 =====

    def _load_json_files(self):
        """加载所有 JSON 知识文件到内存"""
        files = {
            "foods": "foods.json",
            "age_stages": "age_stages.json",
            "allergens": "allergens.json",
            "nutrients": "nutrients.json",
            "textures": "textures.json",
            "categories": "food_categories.json",
            "substitutes": "food_substitutes.json",
        }
        for attr, filename in files.items():
            path = DATA_DIR / filename
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    # 过滤掉以 _ 开头的元数据字段
                    clean = {k: v for k, v in data.items() if not k.startswith("_")}
                    setattr(self, f"_{attr}", clean)

    # ===== SQLite =====

    def _init_db(self):
        """建立 SQLite 连接（需要时）"""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _get_db(self) -> sqlite3.Connection:
        """懒加载 SQLite 连接"""
        if self._conn is None:
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # 首次使用自动建表
            schema = DATA_DIR.parent / "database" / "schema.sql"
            if schema.exists():
                self._conn.executescript(schema.read_text(encoding="utf-8"))
        return self._conn

    # ===== 食材查询 =====

    def get_food(self, food_id: str) -> Optional[dict]:
        # 先按key直查，再按内部id字段搜索
        if food_id in self._foods:
            return self._foods[food_id]
        for food in self._foods.values():
            if food.get("id") == food_id:
                return food
        return None

    def get_food_by_name(self, name_zh: str) -> Optional[dict]:
        for food in self._foods.values():
            if food.get("name_zh") == name_zh:
                return food
        return None

    def list_foods_by_age(self, age_months: int) -> list[dict]:
        return [
            f for f in self._foods.values()
            if f.get("min_age_months", 99) <= age_months
        ]

    def list_foods_by_category(self, category: str) -> list[dict]:
        return [
            f for f in self._foods.values()
            if f.get("category") == category
        ]

    def list_foods_by_tag(self, tag: str) -> list[dict]:
        return [
            f for f in self._foods.values()
            if tag in (f.get("tags") or [])
        ]

    def list_all_foods(self) -> list[dict]:
        return list(self._foods.values())

    def find_substitutes(self, food_name: str) -> list[dict]:
        sub = self._substitutes.get(food_name)
        if not sub:
            return []
        result = []
        for alt in sub.get("alternatives", []):
            food = self.get_food_by_name(alt["food"])
            if food:
                food_copy = dict(food)
                food_copy["substitute_reason"] = alt.get("reason", "")
                result.append(food_copy)
        return result

    # ===== 过敏原查询 =====

    def get_allergen(self, allergen_id: str) -> Optional[dict]:
        a = self._allergens.get(allergen_id)
        return a if a and "aliases" in a else None

    def list_allergens(self) -> list[dict]:
        return [
            v for k, v in self._allergens.items()
            if not k.startswith("_") and k != "umbrella_terms"
        ]

    def match_allergen_by_alias(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for aid, a in self._allergens.items():
            aliases = [al.lower() for al in a.get("aliases", [])]
            if text_lower in aliases:
                return aid
        return None

    def resolve_allergen_query(self, text: str, llm=None) -> list[str]:
        """
        将用户输入的日常用语解析为过敏原 ID 列表（三级 fallback）。
          1. umbrella_terms 精确匹配
          2. 过敏原名/别名匹配
          3. LLM 语义解析（需传入 llm 实例）

        Returns:
            匹配到的过敏原 ID 列表
        """
        if not text:
            return []

        # Level 1: umbrella_terms
        umbrella = self._allergens.get("umbrella_terms", {})
        for term, targets in umbrella.items():
            if not term.startswith("_") and text == term:
                resolved = []
                for target_name in targets:
                    aid = self._find_allergen_id_by_name(target_name)
                    if aid:
                        resolved.append(aid)
                if resolved:
                    return resolved

        # Level 2: exact name / alias
        aid = self._find_allergen_id_by_name(text)
        if aid:
            return [aid]
        aid = self.match_allergen_by_alias(text)
        if aid:
            return [aid]

        # Level 3: LLM NLU
        if llm:
            return self._resolve_allergen_by_llm(text, llm)

        return []

    def _resolve_allergen_by_llm(self, text: str, llm) -> list[str]:
        """
        用 LLM 将日常口语翻译为过敏原 ID 候选集。
        严格约束：只返回 KB 中存在的过敏原 ID，不编造。
        """
        import json as _json
        valid = [
            (a["id"], k, a.get("aliases", []))
            for k, a in self._allergens.items()
            if not k.startswith("_") and k != "umbrella_terms" and "aliases" in a
        ]
        allergen_list = "\n".join(
            f"- {aid} | {name} | 别名：{', '.join(aliases[:6])}"
            for aid, name, aliases in valid
        )

        prompt = f"""你是婴儿辅食过敏原识别助手。

已知过敏原列表（只能从下面选，不能编造）：
{allergen_list}

家长说宝宝「{text}」。请判断这可能对应哪些已知过敏原。

规则：
1. 只返回 JSON 数组，包含匹配到的过敏原 ID，如 ["allergen_004", "allergen_009"]
2. 如果家长说法模糊（如"发物"），返回所有可能相关的
3. 如果完全无法对应，返回 []
4. 只返回 JSON，不要解释"""

        try:
            result = llm.chat_structured(
                system_prompt="你是过敏原映射助手。只返回JSON数组。",
                user_message=prompt,
                schema={"type": "array", "items": {"type": "string"}},
                max_tokens=200,
            )
            if isinstance(result, list):
                valid_ids = {aid for aid, _, _ in valid}
                return [r for r in result if isinstance(r, str) and r in valid_ids]
            if isinstance(result, dict):
                raw = result.get("raw", "")
                try:
                    parsed = _json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(parsed, list):
                        valid_ids = {aid for aid, _, _ in valid}
                        return [r for r in parsed if isinstance(r, str) and r in valid_ids]
                except (_json.JSONDecodeError, TypeError):
                    pass
        except Exception:
            pass

        return []

    def _find_allergen_id_by_name(self, name: str) -> Optional[str]:
        """按过敏原中文名查找 ID"""
        for aid, a in self._allergens.items():
            if aid.startswith("_"):
                continue
            # 键名匹配（如 allergens["鱼类"] → allergen_004）
            if aid == name:
                return a.get("id")
            # name_zh/id 字段匹配
            if a.get("name_zh") == name or a.get("id") == name:
                return a.get("id")
            # 别名匹配
            aliases = [al.lower() for al in a.get("aliases", [])]
            if name.lower() in aliases:
                return a.get("id")
        return None

    # ===== 月龄阶段 =====

    def get_age_stage(self, age_months: int) -> Optional[dict]:
        for stage in self._age_stages.values():
            lo, hi = self._parse_age_range(stage.get("age_range", ""))
            if lo <= age_months <= hi:
                return stage
        return None

    @staticmethod
    def _parse_age_range(range_str: str) -> tuple[int, int]:
        """解析 "6-8月龄" → (6, 8)"""
        if not range_str:
            return (0, 99)
        parts = range_str.replace("月龄", "").replace("以上", "-99").split("-")
        try:
            return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 99)
        except (ValueError, IndexError):
            return (0, 99)

    # ===== 营养数据 =====

    def get_nutrient_info(self, nutrient_id: str) -> Optional[dict]:
        if nutrient_id in self._nutrients:
            return self._nutrients[nutrient_id]
        for n in self._nutrients.values():
            if n.get("id") == nutrient_id:
                return n
        return None

    def list_nutrients(self) -> list[dict]:
        return list(self._nutrients.values())

    # ===== 商品/配料（SQLite 查询）=====

    def get_product(self, product_id: str) -> Optional[dict]:
        db = self._get_db()
        row = db.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if not row:
            return None
        product = dict(row)
        # 附加配料
        ingredients = db.execute("""
            SELECT i.*, pi.sequence, pi.quantity_per_100g
            FROM product_ingredients pi
            JOIN ingredients i ON pi.ingredient_id = i.id
            WHERE pi.product_id = ?
            ORDER BY pi.sequence
        """, (product_id,)).fetchall()
        product["ingredients"] = [dict(r) for r in ingredients]
        # 附加营养成分
        nutrition = db.execute("""
            SELECT * FROM product_nutrition WHERE product_id = ?
        """, (product_id,)).fetchall()
        product["nutrition"] = [dict(r) for r in nutrition]
        return product

    def get_ingredient(self, ingredient_id: str) -> Optional[dict]:
        db = self._get_db()
        row = db.execute(
            "SELECT * FROM ingredients WHERE id = ?", (ingredient_id,)
        ).fetchone()
        return dict(row) if row else None

    def match_ingredient_by_name(self, name: str) -> Optional[dict]:
        db = self._get_db()
        row = db.execute(
            "SELECT * FROM ingredients WHERE name = ? OR name_en = ?",
            (name, name)
        ).fetchone()
        if row:
            return dict(row)
        # 模糊匹配
        row = db.execute(
            "SELECT * FROM ingredients WHERE name LIKE ? OR name_en LIKE ?",
            (f"%{name}%", f"%{name}%")
        ).fetchone()
        return dict(row) if row else None

    def list_products_by_age(self, age_months: int) -> list[dict]:
        db = self._get_db()
        # suggested_age_months 是文本如 '6', '8'，需要比较
        rows = db.execute("""
            SELECT * FROM products
            WHERE CAST(suggested_age_months AS INTEGER) <= ?
        """, (age_months,)).fetchall()
        return [dict(r) for r in rows]

    # ===== 图查询（JSON 等价实现）=====

    def find_foods_rich_in(self, nutrient_name: str, age_months: int) -> list[dict]:
        """等价于图遍历：找适龄且富含某营养素的食材"""
        result = []
        for food in self._foods.values():
            if food.get("min_age_months", 99) > age_months:
                continue
            nutrients = food.get("nutrients", {})
            if nutrient_name in nutrients:
                result.append(food)
        return result

    def check_path_to_allergen(self, product_id: str, allergen_id: str) -> bool:
        """检查商品配料表是否含某过敏原"""
        allergen = self.get_allergen(allergen_id)
        if not allergen:
            return False
        aliases = [a.lower() for a in allergen.get("aliases", [])]
        product = self.get_product(product_id)
        if not product:
            return False
        for ing in product.get("ingredients", []):
            ing_name = ing.get("name", "").lower()
            ing_name_en = ing.get("name_en", "").lower()
            if ing_name in aliases or ing_name_en in aliases:
                return True
            # 查 ingredients 表的 allergen_id
            if ing.get("allergen_id") == allergen_id:
                return True
        return False

    # ===== 工具方法 =====

    def get_stats(self) -> dict:
        """获取知识库统计信息"""
        db = self._get_db()
        return {
            "foods_count": len(self._foods),
            "allergens_count": len([k for k in self._allergens if not k.startswith("_") and k != "umbrella_terms"]),
            "nutrients_count": len(self._nutrients),
            "age_stages_count": len(self._age_stages),
            "products_count": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "ingredients_count": db.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0],
            "backend": "JSON + SQLite",
        }
