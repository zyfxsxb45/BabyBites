// ============================================
// Neo4j 初始化脚本：约束与索引
// 也可手动在 Neo4j Browser 中执行
// ============================================

// 清除宝宝巴适数据（开发用，不影响其他项目的图）
// MATCH (n:BabyBites) DETACH DELETE n;

// 唯一性约束
CREATE CONSTRAINT food_id_unique IF NOT EXISTS FOR (f:Food) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT allergen_id_unique IF NOT EXISTS FOR (a:Allergen) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT nutrient_id_unique IF NOT EXISTS FOR (n:Nutrient) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT age_stage_id_unique IF NOT EXISTS FOR (s:AgeStage) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT product_id_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT ingredient_id_unique IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.id IS UNIQUE;
CREATE CONSTRAINT brand_id_unique IF NOT EXISTS FOR (b:Brand) REQUIRE b.id IS UNIQUE;

// 索引（加速查询）
CREATE INDEX food_name_idx IF NOT EXISTS FOR (f:Food) ON (f.name_zh);
CREATE INDEX food_category_idx IF NOT EXISTS FOR (f:Food) ON (f.category);
CREATE INDEX food_age_idx IF NOT EXISTS FOR (f:Food) ON (f.min_age_months);
CREATE INDEX allergen_name_idx IF NOT EXISTS FOR (a:Allergen) ON (a.name_zh);
CREATE INDEX ingredient_name_idx IF NOT EXISTS FOR (i:Ingredient) ON (i.name);
