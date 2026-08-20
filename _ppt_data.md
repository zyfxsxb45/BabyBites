# PPT用数据快照 —— 宝宝巴适 BabyBites
# AI辅助6-12月龄婴儿辅食推荐与过敏预警系统

## 技术架构
- 规则引擎: 9模块（过敏原/月龄/质地/添加物/营养素/成本/反馈/间隔/窒息）
- 知识底座: 40种食材 + 9类过敏原 + 28个umbrella term + 7种关键营养素 + 11类别
- 知识图谱: Neo4j（48节点 + 580关系）
- LLM: DeepSeek-V4-Flash，负责语义解析、计划生成、对话
- RAG: TF-IDF索引（4742块），支持自由文本问答
- 前端: Streamlit 4 Tab + React Web + FastAPI后端
- 评测: 候选选择 + 安全决策 + 周计划生成 + 开放问答（22个用例，4类任务）

## 核心设计原则
安全不过 LLM —— 规则引擎做安全决策，LLM 做排序和解释
确定性优先 —— 过敏原=已知+血缘（milk→whey），窒息风险按年龄分级

## 评测进展（最新）
- 候选选择: safe/avoid/caution 三级判定，规则ID精确映射
- 周计划: LLM模式（规则过滤 + LLM排序），已与baseline持平
- RAG开放问答: 8/10 胜 baseline（Qwen Judge）
