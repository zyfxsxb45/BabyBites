// ============================================
// Neo4j 查询示例（对应 kb/interface.py 中的方法）
// 可在 Neo4j Browser 中逐一执行验证
// ============================================

// ----- 基础查询 -----

// 1. 查某个食材
MATCH (f:Food {id: 'food_001'}) RETURN f;

// 2. 查适龄食材
MATCH (f:Food) WHERE f.min_age_months <= 6 RETURN f.name_zh, f.category, f.iron_rich;

// 3. 查某类别的食材
MATCH (f:Food {category: 'red_meat'}) RETURN f.name_zh;

// ----- 图遍历查询 -----

// 4. 查富含铁的适龄食材（等价于 find_foods_rich_in('铁', 6)）
MATCH (f:Food)-[:CONTAINS]->(n:Nutrient {name_zh: '铁'})
WHERE f.min_age_months <= 6
RETURN f.name_zh, n.name_zh;

// 5. 查过敏原路径（等价于 check_path_to_allergen）
//    查某商品是否含有某过敏原
MATCH (p:Product {id: 'prod_001'})-[:HAS_INGREDIENT]->(i:Ingredient)
WHERE i.allergen_id = 'allergen_001'
RETURN p.name, i.name;

// 6. 某食材所有关联的营养素
MATCH (f:Food {name_zh: '猪肝'})-[r:CONTAINS]->(n:Nutrient)
RETURN n.name_zh, r.value, r.unit;

// ----- 路径分析 -----

// 7. 两种食材的共同营养素（找替代关系）
MATCH (f1:Food {name_zh: '猪肝'})-[:CONTAINS]->(n:Nutrient)<-[:CONTAINS]-(f2:Food)
RETURN f2.name_zh, collect(n.name_zh) AS shared_nutrients;

// 8. 当前月龄阶段的关键营养素对应的食材（知识图谱特有能力）
MATCH (s:AgeStage) WHERE s.min_age <= 6 AND s.max_age >= 6
MATCH (f:Food)-[:CONTAINS]->(n:Nutrient)
WHERE n.name_zh IN s.key_nutrients AND f.min_age_months <= 6
RETURN f.name_zh, n.name_zh, f.min_age_months;
