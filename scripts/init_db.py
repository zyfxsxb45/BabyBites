#!/usr/bin/env python3
"""
初始化 SQLite 数据库。
从 data/database/schema.sql 建表，从 seed.sql 植入种子数据。
"""

import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))

    # 建表
    schema = PROJECT_ROOT / "data/database/schema.sql"
    if schema.exists():
        conn.executescript(schema.read_text(encoding="utf-8"))
        print(f"✓ Schema loaded from {schema}")

    # 种子数据
    seed = PROJECT_ROOT / "data/database/seed.sql"
    if seed.exists():
        conn.executescript(seed.read_text(encoding="utf-8"))
        print(f"✓ Seed data loaded from {seed}")

    conn.commit()
    conn.close()

    print(f"✓ SQLite database created at {DB_PATH}")

    # 验证
    conn = sqlite3.connect(str(DB_PATH))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    print(f"  Tables: {', '.join(t[0] for t in tables)}")
    product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    ingredient_count = conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
    print(f"  Products: {product_count}, Ingredients: {ingredient_count}")
    conn.close()


if __name__ == "__main__":
    init_db()
