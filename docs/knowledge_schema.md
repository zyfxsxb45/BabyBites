# 知识库 Schema 设计说明

> 对应 `data/knowledge/` 下的 JSON 文件 和 `data/database/schema.sql`

## 实体关系总览

```
食材 (Food)
  ├─ 属于: 食材类别 (FoodCategory)
  ├─ 含有: 营养素 (Nutrient)  [带含量数值]
  ├─ 适合: 月龄阶段 (AgeStage)
  ├─ 是过敏原: 过敏原 (Allergen)
  ├─ 质地: 质地等级 (Texture)
  └─ 替代: 食材 (Food) [对称关系]

商品 (Product) ──── 属于 ──── 品牌 (Brand)
  ├─ 含有配料: 配料 (Ingredient)  [按含量排序]
  └─ 营养成分: 营养成分表 (NutritionFact)  [精确数值]

配料 (Ingredient)
  ├─ 是过敏原: 过敏原 (Allergen)
  ├─ 是添加剂: INS/E 编码
  └─ 风险等级: safe | caution | avoid_under_12m

过敏原 (Allergen)
  ├─ 别名映射: 配料名 → 过敏原
  ├─ 交叉反应: 其他过敏原
  └─ 隐藏来源: 常见含该过敏原的食物

月龄阶段 (AgeStage)
  ├─ 关键营养素: [铁, 锌, ...]
  ├─ 质地要求: 泥糊状 | 碎末状 | 小块
  ├─ 严格禁止: [蜂蜜, 整颗坚果, ...]
  └─ 每日餐次: 2-3次 | 3-4次
```

## JSON → SQLite 分工

| 数据 | 存储位置 | 原因 |
|------|---------|------|
| 食材主数据 | `foods.json` | 静态，数量少（几十到几百），一次性整理 |
| 食材分类 | `food_categories.json` | 静态，结构简单 |
| 营养素参考 | `nutrients.json` | 静态，医学营养标准 |
| 月龄阶段 | `age_stages.json` | 静态，CDC/WHO 标准 |
| 过敏原 | `allergens.json` | 半静态，偶尔增加新别名 |
| 商品/品牌 | SQLite `products` / `brands` | 动态，持续增加 |
| 配料 | SQLite `ingredients` | 动态，Open Food Facts 抓取 |
| 营养成分表 | SQLite `product_nutrition` | 动态，每件商品不同 |

## Neo4j 图模型（双轨制对应）

JSON 中的实体在 Neo4j 中对应的节点标签和关系类型：

| JSON 概念 | Neo4j 节点 | Neo4j 关系 |
|-----------|-----------|-----------|
| foods.json | `(:Food)` | `[:CONTAINS {value, unit}]->(:Nutrient)` |
| allergens.json | `(:Allergen)` | `(:Food)-[:ALLERGEN]->(:Allergen)` |
| age_stages.json | `(:AgeStage)` | `(:Food)-[:SUITABLE_STAGE]->(:AgeStage)` |
| food_categories.json | `(:FoodCategory)` | `(:Food)-[:IN_CATEGORY]->(:FoodCategory)` |
| products | `(:Product)` | `[:HAS_INGREDIENT]->(:Ingredient)` |
| ingredients | `(:Ingredient)` | `[:IS_ALLERGEN]->(:Allergen)` |
