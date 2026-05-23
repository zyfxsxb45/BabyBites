# 宝宝巴适 BabyBites — TODO

> 最后更新: 2026-05-13
> 格式: [ ] 未开始  [~] 进行中  [x] 已完成

---

## Phase 1: 项目骨架 [x]

- [x] 项目目录结构搭建（68个文件）
- [x] 环境配置文件（.env / .env.example / requirements.txt）
- [x] Git 忽略规则
- [x] README 项目说明
- [x] 系统架构文档（docs/系统架构.md）
- [x] 知识库 Schema 设计文档
- [x] DeepSeek API 配置

---

## Phase 2: 知识底座 [~]

### 2.1 JSON 知识数据 [~]

- [x] foods.json — 5 种食材（猪肝、鸡蛋、三文鱼、菠菜、胡萝卜）
- [ ] foods.json — 扩展到至少 30 种核心食材
  - 红肉/内脏：牛肉、猪肉、鸡肝等
  - 禽肉：鸡肉、鸭肉
  - 鱼类：鳕鱼、带鱼、鲈鱼
  - 蔬菜：南瓜、西兰花、土豆、番茄
  - 水果：苹果、香蕉、牛油果
  - 谷物：米粉、燕麦、小米
  - 豆制品：豆腐
- [x] age_stages.json — 3 个月龄阶段
- [x] allergens.json — 8 大过敏原 + 芝麻
- [x] nutrients.json — 7 种关键营养素
- [x] food_categories.json — 10 个食物类别
- [x] textures.json — 3 个质地等级
- [x] food_substitutes.json — 4 组替代食材

### 2.2 SQLite 数据库 [~]

- [x] schema.sql — 5 张表（brands, products, ingredients, product_ingredients, product_nutrition）
- [x] seed.sql — 示例种子数据（3 商品 + 8 配料）
- [ ] 录入至少 10 个常见市售辅食商品（嘉宝、小皮、亨氏等）
- [ ] 从 Open Food Facts API 批量抓取商品数据（scripts/fetch_products.py）

### 2.3 Neo4j 知识图谱 [~]

- [x] init.cypher — 约束与索引脚本
- [x] query_examples.cypher — 8 条示例查询
- [x] scripts/init_neo4j.py — JSON → Neo4j 导入脚本
- [x] 项目标签隔离（:BabyBites），不影响其他项目
- [~] 跑通 `python scripts/init_neo4j.py`（上次 f-string 转义问题已修复，待重新运行）

### 2.4 数据来源整理 [x]

- [x] 13 份国外标准/指南已下载并分类
- [x] 文件重命名为易懂中文名
- [x] 分为国家标准/ 和 指南/ 两个文件夹

---

## Phase 3: 规则引擎 [x]

- [x] rules/base.py — RuleResult / RuleOutput 类型定义
- [x] rules/engine.py — 规则调度器（单食材评估 + 全计划校验）
- [x] rules/allergen.py — 已知过敏原拦截 + 配料过敏检测
- [x] rules/age.py — 月龄适龄 + 严格禁止食物
- [x] rules/texture.py — 质地匹配
- [x] rules/interval.py — 排敏间隔（3 天 + 每周上限）
- [x] rules/nutrition.py — 营养多样性覆盖检查
- [x] rules/additive.py — 添加糖/盐/添加剂检测
- [x] rules/cost.py — 成本-营养性价比排序

### 3.1 规则测试 [~]

- [x] test_allergen.py — 过敏拦截单测
- [x] test_age.py — 月龄适龄单测
- [ ] test_texture.py
- [ ] test_interval.py
- [ ] test_nutrition.py
- [ ] test_additive.py
- [ ] test_engine.py — 规则引擎集成测试

---

## Phase 4: 智能体层 [~]

### 4.1 智能体骨架 [x]

- [x] agents/base.py — RuleAgent / LLMAgent 基类
- [x] agents/user_profile.py — 用户画像提取
- [x] agents/label_parsing.py — 配料表解析
- [x] agents/safety_boundary.py — 阶段判断 + 安全拦截
- [x] agents/plan_generation.py — 计划生成
- [x] agents/validation.py — 计划校验
- [x] agents/dialogue.py — 解释生成

### 4.2 需完善 [ ]

- [ ] user_profile: 接入 LLM 实际调用，添加字段校验逻辑
- [ ] label_parsing: 接入 LLM 配料表切分，完善数据库匹配
- [ ] safety_boundary: 添加发育信号提取（"能坐""能控制头"等）
- [ ] plan_generation: 接入 LLM 做灵活的每日安排排序
- [ ] validation: 跑通完整链路（计划 → 校验 → 通过/重新生成）
- [ ] dialogue: 接入 LLM 生成自然语言解释

### 4.3 智能体测试 [~]

- [x] test_safety_boundary.py — 阶段判断单测
- [ ] test_user_profile.py
- [ ] test_label_parsing.py
- [ ] test_validation.py

---

## Phase 5: 前端 (Streamlit) [ ]

- [x] ui/app.py — 骨架版本（三 Tab：评估/计划/解析）
- [ ] 宝宝信息录入表单 → 连接 SafetyBoundaryAgent
- [ ] 阶段评估结果展示（can_start, blocking_reasons, stage）
- [ ] 候选食材列表 + 安全标签可视化
- [ ] 配料解析交互（输入配料表 → 展示风险成分）
- [ ] 周历视图组件（ui/components/weekly_calendar.py）
- [ ] 食物卡片组件（ui/components/food_card.py）
- [ ] 营养雷达图（Matplotlib 嵌入）
- [ ] 对话反馈功能（家长标记"宝宝拉肚子了"→ 下次调整）

---

## Phase 6: 全链路联调 [ ]

- [ ] 用户输入 → 画像提取 → 阶段判断 → 安全筛选 → 计划生成 → 验证 → 解释 → 展示
- [ ] 边界情况测试：
  - 早产儿（矫正月龄 < 实际月龄）
  - 多种过敏（鸡蛋 + 牛奶）
  - 交叉过敏（花生过敏 → 大豆标注 caution）
  - 已尝试所有可用食材（无新食材可推荐）
  - 空输入 / 异常输入处理
- [ ] 性能测试（食材库 100+ 时的规则引擎耗时）
- [ ] LLM 输出格式稳定性测试

---

## Phase 7: 扩展功能 [ ]

### 7.1 成本优化 [ ]

- [ ] 商品价格数据录入
- [ ] 成本-营养比排序展示
- [ ] 同类商品比价推荐

### 7.2 RAG 补充层（可选）[ ]

- [ ] 对已下载的 PDF 标准做向量化
- [ ] Chroma 向量库搭建
- [ ] "标准/指南引用"查询（用户问"CDC怎么说"→ 检索原文）

### 7.3 更多数据源 [ ]

- [ ] USDA FoodData Central API 对接
- [ ] Open Food Facts API 对接（抓取中国市售辅食商品）
- [ ] 补充下载 EU 2016/127 委任法规
- [ ] 补充下载 AAP 辅食政策声明

---

## Phase 8: 交付 [ ]

- [ ] 结题报告（5000 字）
- [ ] PPT / 路演材料
- [ ] 代码整理 + 注释完善
- [ ] 用户使用说明（README 终版）
- [ ] 最终提交（6月28日）

---

## 快速巡检命令

```bash
# 语法检查
python -m py_compile **/*.py

# 运行所有测试
pytest tests/ -v

# 初始化 JSON 后端
python scripts/init_db.py

# 初始化 Neo4j 后端
python scripts/init_neo4j.py

# 启动前端
streamlit run ui/app.py
```

---

## 团队分工建议

| 模块 | 建议负责 | 当前状态       |
|------|------|------------|
| 知识库数据（JSON 填食材） | 待分配 | 待进行        |
| 规则引擎完善 + 测试 | 待分配 | 骨架完成，需补充测试 |
| 智能体接入 LLM 调试 | 待分配 | 骨架完成，需接入   |
| Streamlit 前端 | 待分配 | 骨架完成       |
| 系统集成 + 联调 | 全员 | 未开始        |
