# 宝宝巴适 BabyBites — TODO

> 最后更新: 2026-06-05
> 格式: [ ] 未开始  [~] 进行中  [x] 已完成

---

## Phase 1-4: 核心系统 ✅

- [x] 40 种食材知识库 + 外部食材包装
- [x] 9 种过敏原 + 28 umbrella term + LLM 语义解析 + strict_mode 阈值
- [x] 9 个规则模块（含外部字段消费层：高钠/添加糖/窒息风险）
- [x] 7 个智能体（含 Chat 真工具调度、计划 evaluate/recommend 双模式）
- [x] 全局年龄阻断（<6月龄所有候选统一 avoid）
- [x] Chat→Profile 双向通路（对话检测到的过敏原自动回写）
- [x] 评测适配器 `eval_adapter.py` 标准化入口
- [x] _ask_llm_structured() JSON 解析修复
- [x] 36 项回归测试 + 专项验证

## Phase 5: 评测对齐 ✅

- [x] 外部食材 KB 覆盖 100%（不再因未映射丢弃候选数据）
- [x] 评测适配器（标准输入→per-candidate {decision, rule_ids}）
- [x] 反馈闭环（UI + 规则联动）
- [x] 过敏原语义匹配（umbrella→alias→LLM 三级回退）

## 前端完善

- [x] Streamlit 四Tab（安全评估/周计划/配料解析/智能问答）
- [x] React Web 前端（Sidebar + Assess + Plan + Label + Chat）
- [x] FastAPI REST 后端
- [x] Boss Baby 悬浮球
- [x] 营养雷达图（recharts）

## 结题交付 [ ]

- [ ] 结题报告 5000 字
- [ ] PPT + Demo 视频
- [ ] 消融实验（规则引擎 vs 纯 LLM A/B 对比）
- [ ] **6月28日 deadline**

## 技术后续 [ ]

- [ ] Neo4j 图查询演示
- [ ] Open Food Facts API 批量抓取
- [ ] Chat Agent 升级为真 function calling（tool_use API）
