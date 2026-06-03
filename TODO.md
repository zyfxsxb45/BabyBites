# 宝宝巴适 BabyBites — TODO

> 最后更新: 2026-05-27
> 格式: [ ] 未开始  [~] 进行中  [x] 已完成

---

## Phase 1: 项目骨架 ✅

- [x] 项目目录结构搭建（68个文件）
- [x] 环境配置（.env DeepSeek / .env.example / requirements.txt）
- [x] Git 仓库 + GitHub 推送
- [x] README 项目说明
- [x] 系统架构文档（docs/系统架构.md）
- [x] 知识库 Schema 设计（docs/knowledge_schema.md）

---

## Phase 2: 知识底座 ✅

### 2.1 JSON 知识数据 ✅

- [x] foods.json — **20 种**食材（猪肝、鸡蛋、三文鱼、菠菜、胡萝卜、牛肉、猪肉、鸡肉、鳕鱼、南瓜、西兰花、豆腐、苹果、香蕉、番茄、土豆、牛油果、燕麦、鸡肝、小米）
- [x] 全部标注真实营养数据（来源：中国食物成分表 + USDA + CDC）
- [x] age_stages.json — 3 个月龄阶段
- [x] allergens.json — 8 大过敏原 + 芝麻 + 隐藏来源
- [x] nutrients.json — 7 种关键营养素（附日需量 + 丰富来源）
- [x] food_categories.json — 10 个食物类别
- [x] textures.json — 3 个质地等级
- [x] food_substitutes.json — 8 组替代关系

### 2.2 SQLite + 商品数据 ✅

- [x] schema.sql — 5 张表
- [x] seed.sql — **8 个市售辅食商品** + 20 种配料（含 INS/E 编码、过敏原标记、添加糖标记）
  - 嘉宝DHA大米米粉、嘉宝南瓜小米高铁米粉
  - 小皮有机胡萝卜泥、小皮有机苹果泥
  - 亨氏婴儿营养米粉、亨氏混合蔬菜泥
  - 英氏钙铁锌米粉、方广婴幼儿肉酥
- [ ] Open Food Facts API 批量抓取（需 VPN）

### 2.3 Neo4j 知识图谱 ✅

- [x] 项目标签隔离 :BabyBites
- [x] init.cypher + query_examples.cypher
- [x] scripts/init_neo4j.py（JSON→Neo4j 一键导入）
- [x] Neo4j 5.26.25 连接配置完成

---

## Phase 3: 规则引擎 ✅

- [x] 全部 8 个规则模块写就
- [x] 规则调度器 RuleEngine（单食材评估 + 全计划校验）
- [~] 规则测试（3个已有，5个待补）

---

## Phase 4: 智能体层 ✅

- [x] 6 个工作流智能体 + 1 个 Chat 智能体
- [x] Chat 智能体：关键词检索知识库 → LLM 生成回答 → 来源标注 → 医疗免责

---

## Phase 5: Chat 智能问答 ✅

- [x] agents/chat.py — 基于知识库检索的问答
- [x] ui/pages/chat.py — 对话气泡界面
- [x] ui/app.py — 第四 Tab「💬 智能问答」
- [x] 医疗问题自动附加免责声明
- [x] 食材关键词匹配覆盖全部 20 种食材

---

## 下一步：后端完善（优先）

### A. 补完测试覆盖 ✅

- [x] rules/test_comprehensive.py — 20 项（质地/排敏/营养/添加剂/成本/引擎/KB边缘）
- [x] tests/test_pipeline.py — 16 项（全链路6场景）
- [x] **36/36 全部通过**

### B. 全链路验证 [ ]

- [ ] 写集成测试脚本 tests/test_pipeline.py
  - 画像提取 → 阶段判断 → 食材筛选 → 计划生成 → 校验 → 输出
- [ ] 关键路径跑通：猪肝/鸡蛋过敏/6月龄 三场景
- [ ] ChatAgent 端到端测试（需 DeepSeek API 连通）

### C. 智能体细节打磨 [ ]

- [ ] user_profile: 字段校验错误处理
- [ ] label_parsing: 配料表切分断句优化
- [ ] safety_boundary: 矫正月龄逻辑验证
- [ ] plan_generation: 周计划排序算法优化
- [ ] validation: 校验失败回退逻辑
- [ ] chat: RAG 可选层（向量化 PDF 标准）

### D. 数据持续充实 [ ]

- [ ] foods.json 20 → 30+（补充鸭肉、带鱼、酸奶、红枣、紫薯等）
- [ ] 接入 USDA FoodData Central API 填充精确营养值
- [ ] 手动录入更多中国市售辅食商品条码

---

## 前端完善（后续）

- [ ] 宝宝信息录入 → 连接 SafetyBoundaryAgent
- [ ] 周历视图 ui/components/weekly_calendar.py
- [ ] 营养雷达图 Matplotlib 嵌入
- [ ] 配料解析实时交互
- [ ] 反馈闭环（家长标记反应 → 下次调整）

---

## 交付

- [ ] 结题报告 5000 字
- [ ] PPT / 路演
- [ ] 代码注释整理
- [ ] **6月28日 final**

---

## 当前状态统计

```
Phase 1  项目骨架:    ✅ 100%
Phase 2  知识底座:    ✅ 100% (20食材+8商品)
Phase 3  规则引擎:    ✅ 85%  (代码完成,测试60%)
Phase 4  智能体层:    ✅ 70%  (骨架完成,细节待打磨)
Phase 5  Chat系统:    ✅ 100%
Phase A  后端测试:    ✅ 100%
Phase B  全链路:      ⬜ 0%
Phase C  前端:        ⬜ 5%
```
