# 宝宝巴适 BabyBites — TODO

> 最后更新: 2026-06-05
> 格式: [ ] 未开始  [~] 进行中  [x] 已完成

---

## Phase 1: 项目骨架 ✅

- [x] 项目目录结构搭建
- [x] 环境配置（.env DeepSeek / .env.example / requirements.txt）
- [x] Git 仓库 + GitHub 推送
- [x] README 项目说明
- [x] 系统架构文档（docs/系统架构.md）
- [x] 知识库 Schema 设计（docs/knowledge_schema.md）

---

## Phase 2: 知识底座 ✅

- [x] foods.json — **40 种**食材，全部真实营养数据
- [x] age_stages.json — 3 个月龄阶段
- [x] allergens.json — 9 种过敏原 + 28 umbrella term + LLM 语义解析
- [x] nutrients.json — 7 种关键营养素
- [x] food_categories.json — 11 个类别（含 seafood、dairy）
- [x] textures.json / food_substitutes.json
- [x] SQLite schema（5张表）+ seed（8商品 + 20配料）

---

## Phase 3: 规则引擎 ✅

- [x] 9 个规则模块：allergen / age / texture / interval / nutrition / additive / cost / feedback / engine
- [x] 过敏原语义匹配：umbrella→alias→LLM 三级 fallback
- [x] 用户反馈闭环：存储→规则转换→计划调整
- [x] 48 项测试全部通过

---

## Phase 4: 智能体层 ✅

- [x] 6 个工作流智能体 + 1 个 Chat 智能体
- [x] LLM OpenAI 兼容适配器（DeepSeek API）
- [x] Chat 智能问答 + RAG 检索增强

---

## Phase 5: 前端串联 ✅

- [x] Streamlit 四 Tab 全部串联
- [x] 周历卡片视图 + 深色文字可读
- [x] 安全评估四分类展示
- [x] 自定义过敏原输入 + LLM 解析确认
- [x] 反馈表单 + 历史展示
- [x] FastAPI REST 后端（8 个端点）
- [x] React Web 前端

---

## 待办

### 结题交付 [ ]

- [ ] 结题报告 5000 字
- [ ] PPT + Demo 视频
- [ ] 消融实验（规则引擎 vs 纯 LLM A/B 对比）
- [ ] **6月28日 deadline**

### 技术加分项 [ ]

- [ ] Neo4j 图查询演示
- [ ] 营养雷达图 Matplotlib 嵌入
- [ ] Open Food Facts API 批量抓取（需 VPN）

### 文档 [ ]

- [x] README 更新
- [x] 系统架构文档更新
- [x] TODO 更新
- [ ] 数据源清单更新
