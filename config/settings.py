"""
全局配置中心。

所有环境相关的参数从这里读取，其他模块 import from config.settings。
用 .env 文件 + 环境变量覆盖，不用硬编码。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ===== 项目路径 =====
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR", "data/knowledge")
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "data/database/babybites.db")
SOURCES_DIR = PROJECT_ROOT / "data/sources"

# ===== 知识库后端 =====
KB_BACKEND = os.getenv("KB_BACKEND", "json")  # "json" or "neo4j"


# ===== Neo4j 连接配置 =====
NEO4J_CONFIG = {
    "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    "user": os.getenv("NEO4J_USER", "neo4j"),
    "password": os.getenv("NEO4J_PASSWORD", ""),
}


# ===== LLM 配置 =====
LLM_CONFIG = {
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
}


# ===== 系统行为 =====
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# ===== 喂养领域常量 =====
MIN_FEEDING_AGE_MONTHS = 6      # 最早开始辅食的月龄
MAX_FEEDING_AGE_MONTHS = 12     # 系统覆盖的上限
INTERVAL_DAYS_NEW_FOOD = 3      # 引入新食材的观察间隔（天）
MAX_NEW_FOODS_PER_WEEK = 3      # 每周最多引入几种新食材
