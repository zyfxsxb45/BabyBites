-- ============================================
-- 种子数据（示例商品，用于开发和测试）
-- ============================================

-- 品牌
INSERT OR IGNORE INTO brands (id, name, name_en, country) VALUES
    ('brand_001', '嘉宝', 'Gerber', '美国'),
    ('brand_002', '小皮', 'Little Freddie', '中国'),
    ('brand_003', '亨氏', 'Heinz', '美国');

-- 商品
INSERT OR IGNORE INTO products (id, brand_id, name, category, suggested_age_months, source) VALUES
    ('prod_001', 'brand_001', '嘉宝DHA大米米粉', 'grains', '6', 'manual'),
    ('prod_002', 'brand_001', '嘉宝鸡肉蔬菜泥', 'mixed', '6', 'manual'),
    ('prod_003', 'brand_002', '小皮有机胡萝卜泥', 'vegetables', '6', 'manual');

-- 配料
INSERT OR IGNORE INTO ingredients (id, name, name_en, ins_code, e_code, category, is_allergen, is_added_sugar, risk_level) VALUES
    ('ing_001', '大米', 'rice', NULL, NULL, 'base_ingredient', 0, 0, 'safe'),
    ('ing_002', '乳清蛋白', 'whey protein', NULL, NULL, 'base_ingredient', 1, 0, 'safe'),
    ('ing_003', '白砂糖', 'sucrose', NULL, NULL, 'base_ingredient', 0, 1, 'caution'),
    ('ing_004', '柠檬酸', 'citric acid', '330', 'E330', 'additive', 0, 0, 'safe'),
    ('ing_005', '碳酸钙', 'calcium carbonate', '170(i)', 'E170', 'fortifier', 0, 0, 'safe'),
    ('ing_006', '鸡肉', 'chicken', NULL, NULL, 'base_ingredient', 0, 0, 'safe'),
    ('ing_007', '胡萝卜', 'carrot', NULL, NULL, 'base_ingredient', 0, 0, 'safe'),
    ('ing_008', '麦芽糊精', 'maltodextrin', NULL, NULL, 'additive', 0, 0, 'caution');

-- 商品配料关联
INSERT OR IGNORE INTO product_ingredients (product_id, ingredient_id, sequence) VALUES
    ('prod_001', 'ing_001', 1),
    ('prod_001', 'ing_002', 2),
    ('prod_001', 'ing_005', 3),
    ('prod_002', 'ing_006', 1),
    ('prod_002', 'ing_007', 2),
    ('prod_003', 'ing_007', 1);

-- 商品营养数据
INSERT OR IGNORE INTO product_nutrition (product_id, nutrient_name, value, unit) VALUES
    ('prod_001', '铁', 6.0, 'mg/100g'),
    ('prod_001', '锌', 3.0, 'mg/100g'),
    ('prod_001', '蛋白质', 7.0, 'g/100g'),
    ('prod_002', '蛋白质', 5.0, 'g/100g'),
    ('prod_002', '铁', 2.0, 'mg/100g');
