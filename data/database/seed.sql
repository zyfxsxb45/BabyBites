-- ============================================
-- 种子数据 — 中国市售婴儿辅食商品
-- 数据来源：品牌官网 + 电商平台商品详情
-- ============================================

-- 品牌
INSERT OR IGNORE INTO brands (id, name, name_en, country) VALUES
    ('brand_001', '嘉宝', 'Gerber', '美国'),
    ('brand_002', '小皮', 'Little Freddie', '中国'),
    ('brand_003', '亨氏', 'Heinz', '美国'),
    ('brand_004', '英氏', 'Engnice', '中国'),
    ('brand_005', '方广', 'Fangguang', '中国');

-- 商品
INSERT OR IGNORE INTO products (id, brand_id, name, category, suggested_age_months, source) VALUES
    ('prod_001', 'brand_001', '嘉宝DHA大米米粉', 'grains', '6', 'manual'),
    ('prod_002', 'brand_001', '嘉宝南瓜小米高铁米粉', 'grains', '6', 'manual'),
    ('prod_003', 'brand_002', '小皮有机胡萝卜泥', 'vegetables', '6', 'manual'),
    ('prod_004', 'brand_002', '小皮有机苹果泥', 'fruits', '6', 'manual'),
    ('prod_005', 'brand_003', '亨氏婴儿营养米粉(原味)', 'grains', '6', 'manual'),
    ('prod_006', 'brand_003', '亨氏混合蔬菜泥', 'vegetables', '6', 'manual'),
    ('prod_007', 'brand_004', '英氏钙铁锌米粉', 'grains', '6', 'manual'),
    ('prod_008', 'brand_005', '方广婴幼儿营养肉酥(猪肉)', 'red_meat', '7', 'manual');

-- 配料（与 Codex INS 编号对应）
INSERT OR IGNORE INTO ingredients (id, name, name_en, ins_code, e_code, category, is_allergen, allergen_id, is_added_sugar, is_added_salt, is_artificial, risk_level) VALUES
    -- 基础配料
    ('ing_001', '大米', 'rice', NULL, NULL, 'base_ingredient', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_002', '米粉', 'rice flour', NULL, NULL, 'base_ingredient', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_003', '南瓜', 'pumpkin', NULL, NULL, 'base_ingredient', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_004', '胡萝卜', 'carrot', NULL, NULL, 'base_ingredient', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_005', '苹果', 'apple', NULL, NULL, 'base_ingredient', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_006', '鸡肉', 'chicken', NULL, NULL, 'base_ingredient', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_007', '猪肉', 'pork', NULL, NULL, 'base_ingredient', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_008', '小米', 'millet', NULL, NULL, 'base_ingredient', 0, NULL, 0, 0, 0, 'safe'),

    -- 母乳替代（致敏成分）
    ('ing_010', '乳清蛋白', 'whey protein', NULL, NULL, 'base_ingredient', 1, 'allergen_002', 0, 0, 0, 'safe'),
    ('ing_011', '全脂乳粉', 'whole milk powder', NULL, NULL, 'base_ingredient', 1, 'allergen_002', 0, 0, 0, 'safe'),
    ('ing_012', '大豆卵磷脂', 'soy lecithin', '322', 'E322', 'additive', 1, 'allergen_005', 0, 0, 0, 'caution'),

    -- 强化剂
    ('ing_020', '碳酸钙', 'calcium carbonate', '170(i)', 'E170', 'fortifier', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_021', '焦磷酸铁', 'ferric pyrophosphate', NULL, NULL, 'fortifier', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_022', '硫酸锌', 'zinc sulfate', NULL, NULL, 'fortifier', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_023', '维生素C', 'ascorbic acid', '300', 'E300', 'fortifier', 0, NULL, 0, 0, 0, 'safe'),

    -- 添加剂和糖
    ('ing_030', '白砂糖', 'sucrose', NULL, NULL, 'base_ingredient', 0, NULL, 1, 0, 0, 'caution'),
    ('ing_031', '果糖', 'fructose', NULL, NULL, 'base_ingredient', 0, NULL, 1, 0, 0, 'caution'),
    ('ing_032', '食用盐', 'salt', NULL, NULL, 'additive', 0, NULL, 0, 1, 0, 'avoid_under_12m'),
    ('ing_033', '柠檬酸', 'citric acid', '330', 'E330', 'additive', 0, NULL, 0, 0, 0, 'safe'),
    ('ing_034', '麦芽糊精', 'maltodextrin', NULL, NULL, 'additive', 0, NULL, 0, 0, 0, 'caution');

-- 商品配料关联
INSERT OR IGNORE INTO product_ingredients (product_id, ingredient_id, sequence) VALUES
    -- 嘉宝DHA大米米粉
    ('prod_001', 'ing_001', 1),
    ('prod_001', 'ing_021', 2),
    ('prod_001', 'ing_022', 3),
    ('prod_001', 'ing_020', 4),
    ('prod_001', 'ing_023', 5),
    -- 嘉宝南瓜小米高铁米粉
    ('prod_002', 'ing_008', 1),
    ('prod_002', 'ing_003', 2),
    ('prod_002', 'ing_021', 3),
    ('prod_002', 'ing_022', 4),
    ('prod_002', 'ing_020', 5),
    -- 小皮有机胡萝卜泥
    ('prod_003', 'ing_004', 1),
    ('prod_003', 'ing_033', 2),
    -- 小皮有机苹果泥
    ('prod_004', 'ing_005', 1),
    ('prod_004', 'ing_023', 2),
    -- 亨氏婴儿营养米粉
    ('prod_005', 'ing_001', 1),
    ('prod_005', 'ing_021', 2),
    ('prod_005', 'ing_020', 3),
    -- 亨氏混合蔬菜泥
    ('prod_006', 'ing_004', 1),
    ('prod_006', 'ing_003', 2),
    -- 英氏钙铁锌米粉
    ('prod_007', 'ing_001', 1),
    ('prod_007', 'ing_020', 2),
    ('prod_007', 'ing_021', 3),
    ('prod_007', 'ing_022', 4),
    -- 方广婴幼儿肉酥
    ('prod_008', 'ing_007', 1),
    ('prod_008', 'ing_032', 2);

-- 商品营养成分表
INSERT OR IGNORE INTO product_nutrition (product_id, nutrient_name, value, unit) VALUES
    ('prod_001', '铁', 6.0, 'mg/100g'),
    ('prod_001', '锌', 3.0, 'mg/100g'),
    ('prod_001', '钙', 300, 'mg/100g'),
    ('prod_001', '蛋白质', 7.0, 'g/100g'),
    ('prod_002', '铁', 5.5, 'mg/100g'),
    ('prod_002', '锌', 3.2, 'mg/100g'),
    ('prod_002', '钙', 280, 'mg/100g'),
    ('prod_002', '蛋白质', 6.5, 'g/100g'),
    ('prod_005', '铁', 5.0, 'mg/100g'),
    ('prod_005', '锌', 2.8, 'mg/100g'),
    ('prod_005', '钙', 250, 'mg/100g'),
    ('prod_007', '铁', 6.2, 'mg/100g'),
    ('prod_007', '锌', 3.5, 'mg/100g'),
    ('prod_007', '钙', 320, 'mg/100g'),
    ('prod_008', '蛋白质', 45.0, 'g/100g'),
    ('prod_008', '铁', 3.0, 'mg/100g');
