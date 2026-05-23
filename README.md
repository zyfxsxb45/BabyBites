# 宝宝巴适 BabyBites

> AI 辅助 6-12 月龄婴儿辅食推荐与过敏预警系统
> 
> 清华大学《人工智能导论》课程大作业 · 2026 春

---

## 项目简介

面向新手家长，基于"规则约束 + 工具调用 + 大语言模型解释"架构，提供：

- **阶段判断**：根据月龄和发育信号评估是否适合开始辅食
- **风险标签**：对食材和商品标注 suitable/caution/avoid
- **配料解析**：识别商品配料表中的致敏物、添加糖/盐
- **周度计划**：在安全约束下生成一周辅食安排
- **成本优化**：在可行方案中按营养/价格比排序

## 核心设计原则

```
安全规则不能过 LLM → 必须硬编码
知识来源必须可追溯 → 每个规则和数据点标注来源
数据与逻辑分离      → JSON/SQLite 管数据，Python 函数管逻辑
校验冗余           → 计划生成后二次规则验证
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据（二选一）
python scripts/init_db.py          # JSON+SQLite 后端（默认，无需安装额外服务）
python scripts/init_neo4j.py       # Neo4j 后端（需先启动 Neo4j 服务）

# 3. 配置 LLM API
cp .env.example .env
# 编辑 .env 填入 API Key

# 4. 启动
streamlit run ui/app.py
```

## 项目结构

```
宝宝巴适/
├── config/          # 全局配置（KB后端切换入口）
├── data/            # 知识库数据源
│   ├── knowledge/   #   JSON 静态知识（主数据源）
│   ├── database/    #   SQLite schema（可变数据）
│   └── sources/     #   国际标准与指南文档
├── kb/              # 知识库抽象层（双轨：JSON / Neo4j）
├── rules/           # 规则引擎（安全兜底）
├── agents/          # 6 个智能体
├── llm/             # LLM 接口抽象
├── ui/              # Streamlit 前端
├── utils/           # 工具函数
├── scripts/         # 数据初始化脚本
├── neo4j/           # Neo4j Cypher 脚本
├── tests/           # 测试
└── docs/            # 设计文档
```

## 团队

| 角色 | 姓名 |
|------|------|
| 知识图谱与数据整理 | 翟彝凡 |
| 规则引擎与安全校验 | TBD |
| 前端与系统集成 | TBD |

## 许可

课程项目，仅供学习交流。
