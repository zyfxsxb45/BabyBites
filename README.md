# 宝宝巴适 BabyBites

> AI 辅助 6-12 月龄婴儿辅食推荐与过敏预警系统
> 
> 清华大学《人工智能导论》课程大作业 · 2026 春

---

## 项目简介

面向新手家长，基于"规则约束 + LLM 语义理解 + 知识库检索"架构，提供：

- **阶段判断**：根据月龄和发育信号评估是否适合开始辅食
- **安全评估**：40种食材四分类标注（🚫避免 / ⚠️谨慎 / ⭐优先推荐 / 🔜后续添加）
- **过敏原语义匹配**：日常口语「海鲜」「面食」自动解析为具体过敏原（三级回退：规则→别名→LLM）
- **配料解析**：识别商品配料表中的致敏物、添加糖/盐、INS编码
- **周度计划**：在安全约束下生成一周辅食安排，支持用户反馈闭环调整
- **智能问答**：基于 RAG 检索增强的辅食知识问答（覆盖28份国际/国内标准）

## 核心设计原则

```
安全规则不能过 LLM   → 过敏拦截、月龄门槛由规则引擎硬编码
LLM 只做 NLU         → 配料切分、过敏原语义解析、解释生成
知识来源可追溯       → 每个数据点标注来源（中国食物成分表 / USDA / CDC / WHO）
数据与逻辑分离       → JSON/SQLite 管数据，Python 函数管逻辑
校验冗余            → 计划生成后规则引擎二次验证
```

## 关键数据

| 指标 | 数值 |
|------|------|
| 食材种类 | 40 种（全部标注真实营养数据） |
| 过敏原覆盖 | 9 种 + 28 个 umbrella term + LLM 语义解析 |
| 规则模块 | 9 个（过敏、月龄、质地、排敏、营养、添加剂、成本、反馈、引擎） |
| 智能体 | 6 个 + Chat |
| 标准文档 | 28 份国际/国内标准（13 国外 + 15 国内） |
| RAG 索引 | 4742 文本块（TF-IDF） |
| 测试覆盖 | 80+ 项（Pipeline 16 + Comprehensive 20 + Feedback 12 + 各专项） |
| 市售商品数据 | 8 种 + 20 配料（含 INS/E 编码） |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据
python scripts/init_db.py          # JSON+SQLite 后端（默认）
# python scripts/init_neo4j.py     # Neo4j 后端（需先启动 Neo4j）
python scripts/build_rag.py        # 构建 RAG 索引

# 3. 配置 LLM API
cp .env.example .env
# 编辑 .env 填入 API Key（支持 DeepSeek / OpenAI 兼容 API）

# 4. 启动（二选一）
streamlit run ui/app.py            # Streamlit 前端
python server/main.py              # FastAPI 后端 + React 前端
```

## 项目结构

```
宝宝巴适/
├── agents/           # 6个工作流智能体 + Chat
│   ├── safety_boundary.py   # 阶段判断 + 安全拦截（纯规则）
│   ├── plan_generation.py   # 周计划生成（约束排序 + 类别轮转）
│   ├── label_parsing.py     # 配料表解析（LLM + 正则 fallback）
│   ├── chat.py              # 智能问答（RAG + LLM + 医疗免责）
│   ├── user_profile.py      # 画像标准化
│   └── base.py              # LLMAgent / RuleAgent 基类
├── rules/            # 规则引擎（安全兜底，不过 LLM）
│   ├── allergen.py          # 过敏原拦截（含语义解析）
│   ├── feedback.py          # 用户反馈→规则转换
│   ├── engine.py            # 调度器
│   └── ...                  # age / texture / interval / nutrition / additive / cost
├── kb/               # 知识库抽象层（双轨：JSON / Neo4j）
│   ├── json_backend.py      # JSON+SQLite 实现（含 resolve_allergen_query）
│   ├── rag.py               # TF-IDF 检索器（4742块）
│   └── factory.py           # 双轨切换
├── data/
│   ├── knowledge/           # JSON 静态知识（40食材、9过敏原、7营养素…）
│   ├── database/            # SQLite schema + seed（8商品+20配料）
│   └── sources/             # 标准原文参考
├── ui/               # Streamlit 前端
│   ├── app.py               # 主入口（四Tab）
│   └── components/          # Boss Baby 悬浮球 + 问答浮窗
├── server/           # FastAPI 后端（供 React 前端调用）
├── web/              # React 前端（Vite）
├── llm/              # LLM 接口抽象（OpenAI 兼容 API）
├── tests/            # 测试（80+项）
├── scripts/          # 数据初始化
└── docs/             # 设计文档
```

## 过敏原语义匹配

```
用户输入: "海鲜" / "面食" / "发物"
    ↓
Level 1: umbrella_terms 精确匹配（28项）
Level 2: 过敏原名/别名匹配
Level 3: LLM 语义解析
    ↓
"海鲜" → [鱼类, 虾]
"面食" → [小麦]
"发物" → [鱼类, 虾, 鸡蛋]  (LLM 推断 + 用户确认)
    ↓
规则引擎硬判断 → avoid/caution/suitable
```

## 团队

曾作为，苏冠辰，翟彝凡

## 许可

课程项目，仅供学习交流。
