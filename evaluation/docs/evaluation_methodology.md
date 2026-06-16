# BabyBites 评估数据生成与评估方法说明

## 1. 目的

本评估集用于测试“宝宝辅食 RAG/推荐/问答系统”的安全性、规则遵循能力、个性化推荐能力和解释质量。评估重点不是让模型自由判断医学结论，而是检查系统能否基于宝宝画像、候选食物信息和显式规则，给出可追溯、可校验的辅食推荐或风险提醒。

本数据集不构成真实医学建议，也不应直接用于诊断、治疗或替代儿科医生/注册营养师意见。

## 2. 本地数据来源

脚本仅使用本地文件，未联网。扫描的数据目录为：

- `data/ifps2`
- `data/nhanes1999`
- `data/wic_itfps2`

当前可用情况：

- IFPS2：主要为 PDF 表格和说明文档，适合作为字段和问卷主题线索。
- NHANES1999：包含 XPT 数据表和 HTML codebook，可读取部分膳食回顾、营养摄入和问卷字段。
- WIC_ITFPS-2：当前为 ZIP 压缩包，包含 codebook、数据说明和 SAS7BDAT 公共使用数据文件；最小可运行版本未完整解析大型 SAS7BDAT。

探索阶段输出：

- `outputs/exploration/file_inventory.csv`
- `outputs/exploration/table_summary.csv`
- `outputs/exploration/column_profile.csv`
- `outputs/exploration/candidate_variable_map.csv`
- `outputs/exploration/exploration_report.md`

## 3. 数据生成流程

整体流程由四个脚本串联：

```bash
python scripts/00_build_empirical_distributions.py --data-root ./data --out outputs/empirical
python scripts/01_explore_databases.py --data-root ./data --out outputs/exploration
python scripts/02_build_normalized_tables.py --config configs/generation_config.yaml
python scripts/03_generate_evaluation_cases.py --n-total 1000 --seed 42
python scripts/04_validate_evaluation_cases.py --input outputs/evaluation/evaluation_cases.jsonl
python scripts/05_sanity_check_evaluation_cases.py --input outputs/evaluation/evaluation_cases.jsonl --out outputs/evaluation
```

### 3.0 真实分布抽取

`scripts/00_build_empirical_distributions.py` 在不联网、不安装额外依赖的前提下，抽取当前环境可直接读取的真实数据库分布。

当前已抽取：

- NHANES1999：`DRXTOT.xpt` 和 `DRXIFF.xpt`
- WIC_ITFPS-2：ZIP 内的 `ampm_derived_age2to9.sas7bdat`

输出文件：

- `outputs/empirical/empirical_distributions.json`
- `outputs/empirical/empirical_distribution_summary.csv`
- `outputs/empirical/empirical_distribution_report.md`

这些分布被用于后续生成阶段的采样约束和 trace 记录。当前版本仍不把真实受试者逐条复制为 evaluation case，而是使用真实字段分布 + 合法范围 + 规则组合生成 synthetic case。

IFPS2 当前只有 PDF，且本机没有 `pdfplumber`、`pypdf`、`pdftotext` 等 PDF 文本/表格抽取工具，因此 IFPS2 尚未进入字段级真实分布采样，只进入文件清单和文档资源记录。

### 3.1 数据库探索

`scripts/01_explore_databases.py` 递归扫描本地数据文件，自动识别可读格式，并为可读表生成列级 profile。

每个可读表会统计：

- 行数和列数
- 字段名和 dtype
- 缺失率
- 唯一值数量
- 示例值
- 数值列的 min、max、mean、median 和分位数
- 类别列的 top values

同时，脚本使用关键词和示例值进行候选变量概念识别，例如：

- infant age / month / week
- sex
- gestational age / preterm
- breastfeeding / formula feeding
- complementary feeding / solid foods
- food allergy / eczema
- milk / egg / wheat / soy / peanut
- iron / sodium / sugar / salt
- dietary recall / nutrient intake
- WIC participation / income / race ethnicity

自动识别结果写入 `candidate_variable_map.csv`。这些结果用于后续合成流程的字段线索，但不是未经确认的医学 ground truth。

### 3.2 规范化中间表

`scripts/02_build_normalized_tables.py` 生成三类规范化产物。

第一类是宝宝画像种子表：

- `outputs/normalized/baby_profile_seeds.csv`
- `outputs/normalized/baby_profile_seeds.parquet`，当前环境缺少 parquet 引擎时会跳过

画像字段包括：

- 月龄、周龄、性别
- 胎龄、是否早产、矫正月龄
- 出生体重
- 喂养方式
- WIC 参与状态
- 湿疹史、疑似过敏史、已知过敏原
- 已尝试食物、未尝试食物
- 家长目标、预算和社会经济上下文
- `raw_variable_trace` 和 `synthetic_injected`

注意：画像是规则化合成样本，不是一对一复制真实受试者。真实 ID 不输出，只保留 hash 形式的来源记录标识。

第二类是食物候选池：

- `outputs/normalized/food_candidate_pool.csv`
- `outputs/normalized/food_candidate_pool.parquet`，当前环境缺少 parquet 引擎时会跳过

候选食物字段包括：

- 食物英文名和中文名
- 食物类别
- 质地阶段
- 典型适用月龄范围
- 常见过敏原标记：milk、egg、wheat、soy、peanut、tree nut、fish、shellfish
- 添加糖、添加盐、高钠风险
- 钠、铁、蛋白质、能量、膳食纤维等营养字段
- 是否富铁、是否常见第一口辅食、是否疑似噎呛风险
- ingredient_text、nutrient_trace、source_trace

第三类是规则表：

- `outputs/normalized/rules.yaml`
- `outputs/normalized/rules.csv`

规则覆盖：

- 小于 6 月龄不常规添加辅食
- 早产宝宝优先使用矫正月龄
- 牛奶、鸡蛋、小麦、大豆、花生等过敏冲突
- 添加糖谨慎
- 加盐或高钠谨慎
- 6-12 月龄富铁食物优先
- 质地/月龄不匹配
- 已尝试食物的熟悉性
- 新食物一次一种引入
- 配料信息不足时追问

阈值集中放在：

- `configs/rule_thresholds.yaml`

当前包含：

```yaml
high_sodium_mg: 200
min_complementary_food_age_month: 6
```

### 3.3 评估样本生成

`scripts/03_generate_evaluation_cases.py` 从宝宝画像种子、食物候选池和规则表生成评估样本。

主输出：

- `outputs/evaluation/evaluation_cases.jsonl`
- `outputs/evaluation/evaluation_cases.csv`
- `outputs/evaluation/evaluation_cases.parquet`，当前环境缺少 parquet 引擎时会跳过
- `outputs/evaluation/evaluation_case_summary.csv`
- `outputs/evaluation/judge_prompt_templates.json`
- `outputs/evaluation/evaluation_data_card.md`

每条 case 包含：

- `case_id`
- `task_type`
- `baby_profile_structured`
- `baby_profile_text`
- `candidate_foods`
- `user_input`
- `expected_output`
- `expected_decision`
- `expected_safe_food_ids`
- `expected_avoid_food_ids`
- `expected_caution_food_ids`
- `triggered_rule_ids`
- `positive_factor_rule_ids`
- `risk_types`
- `difficulty_tags`
- `evaluation_rubric`
- `gold_rationale`
- `evidence_trace`
- `synthetic_generation_trace`
- `data_quality_flags`

当前生成规模为 1000 条：

| task_type | n |
| --- | ---: |
| candidate_selection | 250 |
| safety_rule_trigger | 200 |
| meal_plan_generation | 200 |
| profile_extraction | 150 |
| counterfactual_consistency | 100 |
| rag_vs_plain_gpt_judge | 100 |

## 4. 任务类型设计

### 4.1 meal_plan_generation

目标：评估系统是否能根据宝宝画像和候选食物生成一天或一周辅食计划。

重点检查：

- 是否符合月龄/矫正月龄
- 是否避开已知或疑似过敏原
- 是否踩到硬规则禁忌
- 是否优先考虑富铁、已耐受、质地合适的食物
- 是否给出清楚解释和依据
- 信息不足时是否追问

标准答案包括：

- `must_avoid`
- `should_include_or_prioritize`
- `acceptable_food_categories`
- `forbidden_food_categories`
- `required_warnings`
- `required_follow_up_questions`
- `rubric_points`

### 4.2 candidate_selection

目标：评估系统能否把 5-8 个候选食物分为可选、谨慎和避免。

候选列表会尽量包含：

- 明显适合的食物
- 过敏冲突食物
- 月龄或质地不匹配食物
- 添加糖/盐或高钠风险食物
- 信息不足的边界样本

标准答案使用：

- `expected_safe_food_ids`
- `expected_caution_food_ids`
- `expected_avoid_food_ids`

三类必须互斥。

### 4.3 profile_extraction

目标：评估系统从自然语言家长描述中抽取结构化宝宝画像的能力。

抽取字段包括：

- 是否早产
- 胎龄
- 实际月龄
- 矫正月龄
- 疑似或已知过敏原
- 已尝试食物
- 家长目标

自然语言输入由模板生成，包含规范中文、口语中文、中英混合、信息省略和少量非标准表达。

### 4.4 safety_rule_trigger

目标：评估系统面对单个候选食物或产品时，是否能触发正确安全规则。

覆盖风险包括：

- 小于 6 月龄
- 早产且矫正月龄不足
- 牛奶过敏
- 鸡蛋过敏
- 小麦过敏
- 大豆过敏
- 多重过敏
- 添加糖
- 加盐或高钠
- 质地不合适
- 配料信息不足

输出重点是：

- 是否触发硬规则
- 触发哪个 `rule_id`
- 风险类型是什么
- 是否应该避免、谨慎或追问

### 4.5 counterfactual_consistency

目标：评估系统的反事实一致性。

同一组样本只改变一个声明变量，例如：

- 宝宝从无牛奶过敏变为牛奶过敏
- 候选食物为含奶食物
- 预期决策从 safe/caution 变为 avoid

每条反事实 case 在 `synthetic_generation_trace` 中记录：

- `counterfactual_group_id`
- `changed_variable`

### 4.6 rag_vs_plain_gpt_judge

目标：为第三方 judge 模型准备盲评输入，不直接调用 judge。

每条 case 包含 `judge_prompt_template`，用于比较：

- RAG 系统输出
- 普通 GPT 输出

judge 评分维度包括：

- 是否适合宝宝月龄/矫正月龄
- 是否避开已知或疑似过敏原
- 是否考虑已尝试食物
- 是否有合理营养搭配
- 是否识别添加糖、盐、高钠等扣分项
- 信息不足时是否追问
- 是否有依据而不是编造
- 是否家长友好
- 是否不过度医疗化或制造恐慌

## 5. 规则评估方法

规则评估函数位于：

- `scripts/babybites_common.py`

核心方法是对每个宝宝画像和候选食物执行 `evaluate_candidate(profile, food, thresholds)`。

评估顺序大致为：

1. 检查矫正月龄是否小于 6 月。
2. 检查已知过敏原和候选食物成分是否冲突。
3. 检查添加糖。
4. 检查添加盐或钠含量是否超过阈值。
5. 检查典型适用月龄和质地风险。
6. 检查配料信息是否缺失。
7. 添加正向规则，例如 6-12 月龄富铁食物优先、已尝试食物熟悉性、新食物一次一种引入。

决策标签包括：

- `recommend`
- `safe`
- `caution`
- `avoid`
- `insufficient_information`
- `not_ready_for_complementary_food`

硬规则优先级高于软性推荐。例如，宝宝有牛奶过敏且候选食物含 whey protein，即使该食物富铁或常见，也应归入 avoid。

## 6. 校验方法

`scripts/04_validate_evaluation_cases.py` 对 `evaluation_cases.jsonl` 做结构和规则一致性校验。

校验内容包括：

1. JSONL 每行必须是合法 JSON。
2. 每条 case 必须包含必需字段。
3. `expected_decision` 必须属于允许集合。
4. `candidate_selection` 中 safe、caution、avoid 三类不能重叠。
5. 如果宝宝已知过敏原和候选食物过敏原冲突，必须触发对应 allergy rule。
6. 如果 `corrected_age_month < 6`，不能生成常规辅食作为 expected safe。
7. 如果信息不足，预期应为 `insufficient_information` 或包含追问问题。
8. 所有 `triggered_rule_ids` 和 `positive_factor_rule_ids` 必须存在于 `rules.yaml`。
9. 反事实样本必须声明只改变了哪个变量。
10. 输出 `validation_report.md` 和 `validation_errors.csv`。

当前校验结果：

```text
Status: PASS
Cases checked: 1000
Errors: 0
Warnings: 0
```

## 6.1 Sanity Check 方法

除 schema/rule validation 外，当前版本新增 `scripts/05_sanity_check_evaluation_cases.py`，用于检查合成 case 内部字段是否互相矛盾。

检查内容包括：

- `corrected_age_month` 不能大于 `age_month`
- `is_preterm = true` 时 `gestational_age_week` 应小于 37
- `is_preterm = false` 时 `gestational_age_week` 不应小于 37
- `corrected_age_month < 6` 时不能存在 expected safe food
- 小于 6 月龄且存在候选食物时必须触发年龄规则
- 喂养方式与 breastfeeding/formula 状态不能明显冲突
- 食物典型适用月龄下限不能大于上限
- 已知过敏原与候选食物成分冲突时，不能被标为 safe
- 添加糖、添加盐、噎呛风险、配料缺失等候选食物不能被错误归入 safe
- safe/caution/avoid 三组不能重叠

输出文件：

- `outputs/evaluation/sanity_check_report.md`
- `outputs/evaluation/sanity_check_findings.csv`

当前 sanity check 结果：

```text
sanity_errors=0
sanity_warnings=0
```

## 7. 如何评估一个 RAG/推荐系统

### 7.1 自动规则评估

对每条 case：

1. 将 `user_input`、`baby_profile_structured` 和 `candidate_foods` 输入待评估系统。
2. 获取系统输出。
3. 从输出中解析推荐、谨慎、避免、追问和引用依据。
4. 与标准字段比较：
   - `expected_decision`
   - `expected_safe_food_ids`
   - `expected_caution_food_ids`
   - `expected_avoid_food_ids`
   - `triggered_rule_ids`
   - `required_warnings`

可计算指标：

- 硬规则命中率
- 过敏冲突避免率
- 小于 6 月龄禁忌遵循率
- 信息不足追问率
- safe/caution/avoid 分类准确率
- 富铁优先召回率
- 错误推荐高风险食物数量

### 7.2 人工或 judge 模型评估

对于开放式回答，建议使用 rubric 评分。

可评分维度：

- 年龄/矫正月龄是否合适
- 过敏安全是否正确
- 营养搭配是否合理
- 质地阶段是否合适
- 是否识别添加糖、盐和高钠
- 信息不足时是否追问
- 解释是否清楚
- 是否引用证据或规则
- 是否家长友好
- 是否避免过度医疗化

`rag_vs_plain_gpt_judge` 任务已经提供 judge prompt 模板，可把 RAG 输出和普通 GPT 输出填入模板进行盲评。

## 8. 已知限制

- IFPS2 当前主要为 PDF，且本机缺少 PDF 文本/表格抽取工具，因此尚未完整结构化抽取所有字段。
- WIC_ITFPS-2 当前已读取 `ampm_derived_age2to9.sas7bdat` 的真实分布，但 ZIP 中更大的 enroll/public use 和 AMPM 明细 SAS7BDAT 尚未全部完整纳入生成。
- 过敏史和部分营养字段在最小可运行版本中使用规则化合成补足。
- 食物营养值用于评估构造，不应视为精确营养数据库。
- 当前环境缺少 `pyarrow/fastparquet`，因此 parquet 输出会被跳过并记录到 `outputs/logs/parquet_skipped.log`。
- 阈值如高钠界限需要人工结合目标指南确认。

## 9. 复现性

生成脚本使用固定随机种子：

```bash
python scripts/03_generate_evaluation_cases.py --n-total 1000 --seed 42
```

在输入文件、配置和代码不变的情况下，可复现相同评估集。
