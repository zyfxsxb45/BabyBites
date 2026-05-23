-- ============================================
-- 宝宝巴适 SQLite 数据库 Schema
-- 用途：存储可变数据（商品/配料/营养成分等）
-- ============================================

-- 品牌表
CREATE TABLE IF NOT EXISTS brands (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    name_en     TEXT,
    country     TEXT,
    website     TEXT
);

-- 商品/产品表
CREATE TABLE IF NOT EXISTS products (
    id                  TEXT PRIMARY KEY,
    barcode             TEXT UNIQUE,
    brand_id            TEXT REFERENCES brands(id),
    name                TEXT NOT NULL,
    name_en             TEXT,
    category            TEXT,           -- 参照 food_categories.json 的分类
    suggested_age_months TEXT,          -- '6', '8', '12' 等
    price               REAL,           -- 人民币
    price_per_100g      REAL,
    image_url           TEXT,
    source              TEXT DEFAULT 'manual',   -- 'manual' | 'open_food_facts'
    source_url          TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- 配料/成分表
CREATE TABLE IF NOT EXISTS ingredients (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    name_en         TEXT,
    ins_code        TEXT,               -- Codex INS 编号
    e_code          TEXT,               -- EU E 编号
    category        TEXT,               -- 'additive' | 'fortifier' | 'base_ingredient' | 'flavoring'
    is_allergen     INTEGER DEFAULT 0,
    allergen_id     TEXT,               -- 引用 allergens.json 中的 id
    is_added_sugar  INTEGER DEFAULT 0,
    is_added_salt   INTEGER DEFAULT 0,
    is_artificial   INTEGER DEFAULT 0,
    risk_level      TEXT                -- 'safe' | 'caution' | 'avoid_under_12m'
);

-- 商品-配料 N:N 关联表
CREATE TABLE IF NOT EXISTS product_ingredients (
    product_id      TEXT REFERENCES products(id) ON DELETE CASCADE,
    ingredient_id   TEXT REFERENCES ingredients(id),
    sequence        INTEGER,            -- 配料表排序位置（配料表按含量降序排列）
    quantity_per_100g TEXT,             -- 可选：具体含量
    PRIMARY KEY (product_id, ingredient_id)
);

-- 商品营养成分表
CREATE TABLE IF NOT EXISTS product_nutrition (
    product_id      TEXT REFERENCES products(id) ON DELETE CASCADE,
    nutrient_name   TEXT NOT NULL,
    value           REAL NOT NULL,
    unit            TEXT NOT NULL,
    per_what        TEXT DEFAULT '100g',
    source          TEXT,
    PRIMARY KEY (product_id, nutrient_name)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_id);
CREATE INDEX IF NOT EXISTS idx_ingredients_category ON ingredients(category);
CREATE INDEX IF NOT EXISTS idx_ingredients_allergen ON ingredients(allergen_id)
    WHERE is_allergen = 1;
CREATE INDEX IF NOT EXISTS idx_pi_product ON product_ingredients(product_id);
CREATE INDEX IF NOT EXISTS idx_pi_ingredient ON product_ingredients(ingredient_id);
CREATE INDEX IF NOT EXISTS idx_pn_product ON product_nutrition(product_id);
