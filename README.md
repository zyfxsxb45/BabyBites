# 宝宝巴适 BabyBites

> AI 辅助 6-12 月龄婴儿辅食推荐与过敏预警系统
> 
> 清华大学《人工智能导论》课程大作业 · 2026 春

---

## 功能

面向新手家长，基于"规则约束 + LLM 语义理解 + 知识库检索"架构：

- **安全评估**：40种食材四分类标注（🚫避免 / ⚠️谨慎 / ⭐优先推荐 / 🔜后续添加），外部食材支持高钠/添加糖/窒息风险/过敏原结构字段
- **过敏原语义匹配**：日常口语「海鲜」「面食」自动解析（umbrella_terms 28项 → 别名 → LLM 三级回退）
- **配料解析**：识别致敏物、添加糖/盐、INS编码、窒息风险
- **周度计划**：7天辅食安排，支持用户反馈闭环自动调整，支持显式候选池（evaluate/recommend 双模式）
- **智能问答**：RAG 检索增强 + Chat 工具调用（自动查食材营养/过敏原/安全评估）
- **评测适配器**：`eval_adapter.py` 标准评测输入一键调用，输出符合评测规范的 per-candidate 结果

## 核心设计原则

```
安全规则不能过 LLM   → 过敏拦截、月龄门槛由规则引擎硬编码
LLM 只做 NLU         → 配料切分、过敏原语义解析、解释生成
知识来源可追溯       → 每个数据点标注来源（中国食物成分表 / USDA / CDC / WHO）
外部数据不丢弃       → KB未收录食材，只要有结构字段就能做安全判断
双模式切换           → evaluate（逐候选打标）| recommend（生成周计划）
Chat ↔ Profile 互通  → 对话中检测到的过敏原/食物信息自动回写宝宝画像
```

## 关键数据

| 指标 | 数值 |
|------|------|
| 食材 | 40 种（全部标注真实营养来源）+ 外部食材自动包装 |
| 过敏原 | 9 种 + 28 umbrella term + LLM 语义解析 |
| 规则模块 | 9 个（过敏、月龄、质地、排敏、营养、添加剂、成本、反馈、引擎） |
| 智能体 | 7 个（6工作流 + Chat） |
| 评测支持 | eval_adapter 标准化入口，候选覆盖率 100%（无信息丢弃） |
| 标准文档 | 28 份（13国外 + 15国内） |
| RAG 索引 | 4742 文本块（TF-IDF） |
| 测试 | 36 项回归 + 专项测试 |
| 前端 | Streamlit（四Tab）+ React Web（Vite）+ FastAPI |

## 快速开始

```bash
pip install -r requirements.txt
python scripts/init_db.py
python scripts/build_rag.py
cp .env.example .env  # 填 API Key

# 启动（二选一）
streamlit run ui/app.py        # Streamlit 前端
python server/main.py          # FastAPI → http://localhost:8000
# 另开终端: cd web && npm install && npm run dev  → http://localhost:5173
```

## 项目结构

```
宝宝巴适/
├── agents/              # 7个智能体
│   ├── safety_boundary.py    # 阶段判断 + 安全拦截（含外部食材+全局年龄阻断）
│   ├── plan_generation.py    # 周计划（evaluate/recommend 双模式）
│   ├── chat.py               # 智能问答（RAG + 真工具调度）
│   ├── label_parsing.py      # 配料表解析
│   ├── user_profile.py       # 画像标准化
│   └── base.py               # LLMAgent/RuleAgent 基类（含JSON解析器）
├── rules/               # 规则引擎
│   ├── allergen.py           # 过敏原拦截（语义解析+外部食材+strict_mode）
│   ├── engine.py             # 调度器（含外部字段消费层）
│   └── feedback.py / age.py / texture.py / ...
├── kb/                  # 知识库
│   ├── json_backend.py       # JSON+SQLite（含resolve_allergen_query三级回退）
│   ├── external_food.py      # 外部食材包装器（高钠/糖/窒息/过敏原→内部格式）
│   ├── rag.py                # TF-IDF 检索器
│   └── neo4j_backend.py      # Neo4j 图查询（可选）
├── eval_adapter.py      # 评测适配器（标准输入→系统调用→评测输出）
├── data/knowledge/      # 40食材、9过敏原+umbrella_terms、7营养素、11类别
├── ui/                  # Streamlit 四Tab
├── server/              # FastAPI REST
├── web/                 # React 前端（Vite）
├── tests/               # 回归测试
└── docs/                # 设计文档
```

## 评测适配器

```python
from eval_adapter import evaluate_candidates

result = evaluate_candidates(
    profile={"age_months": 8, "allergies": ["牛奶"], "tried_foods": [], "notes": ""},
    candidates=[
        {"food_id": "F1", "food_name_zh": "加盐肉汤", "contains_added_salt": True, "sodium_mg": 420},
        {"food_id": "F2", "food_name_zh": "原味酸奶", "contains_milk": True},
        {"food_id": "F3", "food_name_zh": "整颗葡萄", "is_choking_risk_candidate": True},
    ],
)
# → {items: [{food_id, food_name_zh, decision, triggered_rule_ids, reasons}]}
```

## 团队

曾作为，苏冠辰，翟彝凡
