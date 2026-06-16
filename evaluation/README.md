# BabyBites Evaluation

本目录保存 BabyBites 性能评测相关脚本、方法学文档和轻量结果快照。它是独立评测模块，不属于线上后端实现路径。

## 目录结构

```text
evaluation/
  README.md
  requirements-evaluation.txt
  scripts/
    00_*.py - 05_*.py   数据探索、规范化、评测集生成与 sanity check
    06_*.py - 12_*.py   系统对比、第三方盲评、样例与报告生成
    13_*.py - 24_*.py   未见样本抽样、定向加测与双向盲评整合
    25_*.py - 27_*.py   画像分布、候选加测统计和最终作图
    babybites_common.py 评测数据生成使用的公共函数
  configs/
    generation_config.yaml
    rule_thresholds.yaml
  docs/
    evaluation_methodology.md
    metric_guide.md
    risk_type_protocol.md
    PAPER_EVALUATION_METHODS_RESULTS_DISCUSSION_ZH.md
  results_snapshot/
    statistics/                 当前论文口径的轻量统计表
    profile_distributions/       当前论文口径的画像分布表
```

## 与后端的边界

- 后端代码仍位于 `agents/`、`rules/`、`kb/`、`server/`、`ui/` 等目录。
- `evaluation/scripts/` 可以调用后端公开接口或 `eval_adapter.py` 做离线评测，但不参与线上服务启动。
- 评测输出默认写入仓库根目录下的 `outputs/`，该目录不应提交到 Git。
- API key 只通过环境变量读取，不写入脚本、文档或结果快照。

## 环境变量

常用变量：

```powershell
$env:BABYBITES_EVAL_ROOT="<repo-root>"
$env:BABYBITES_APP_ROOT="<repo-root>"
$env:OPENAI_API_KEY="<your-deepseek-key>"
$env:OPENAI_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-v4-pro"
$env:JUDGE_API_KEY="<your-dashscope-key>"
```

`BABYBITES_EVAL_ROOT` 默认会自动解析为 `evaluation/..`，通常不必手动设置。

## 典型流程

### 1. 生成或刷新评测数据

```powershell
python evaluation\scripts\00_build_empirical_distributions.py --data-root data --out outputs\empirical
python evaluation\scripts\01_explore_databases.py --data-root data --out outputs\exploration
python evaluation\scripts\02_build_normalized_tables.py --config evaluation\configs\generation_config.yaml
python evaluation\scripts\03_generate_evaluation_cases.py --n-total 1000 --seed 42
python evaluation\scripts\04_validate_evaluation_cases.py --input outputs\evaluation\evaluation_cases.jsonl
python evaluation\scripts\05_sanity_check_evaluation_cases.py --input outputs\evaluation\evaluation_cases.jsonl --out outputs\evaluation
```

### 2. 运行正式任务评测

```powershell
python evaluation\scripts\07_run_formal_task_evaluation.py `
  --input outputs/evaluation/evaluation_cases_unseen_stratified100_v20260608.jsonl `
  --out outputs/formal_evaluation_current_unseen_stratified100 `
  --limit 100 `
  --model deepseek-v4-pro
```

### 3. 第三方盲评

```powershell
python evaluation\scripts\10_run_third_party_judge.py `
  --cases outputs/evaluation/evaluation_cases_meal_plan_caution_fallback_v2_68_v20260609.jsonl `
  --results outputs/formal_evaluation_meal_plan_caution_fallback_v2_68/formal_results.jsonl `
  --out outputs/formal_evaluation_meal_plan_caution_fallback_v2_68/third_party_judge `
  --model qwen3.7-plus
```

### 4. 统计分析与绘图

```powershell
python evaluation\scripts\27_rebuild_figures_with_interim_candidate_extension.py

$env:BABYBITES_PROFILE_DIST_INPUT="outputs/statistical_analysis_combined_counterfactual15_candidate_interim/_analysis_input/formal_results.jsonl"
$env:BABYBITES_PROFILE_DIST_OUT="outputs/task_profile_distributions_candidate_interim"
python evaluation\scripts\25_plot_task_profile_distributions.py
```

## 当前快照口径

`results_snapshot/` 保存当前论文中使用的轻量统计表：

- 候选选择：77 个案例，478 个候选食物。
- 安全规则触发：20 个案例。
- 反事实一致性：15 个完整配对。
- 周计划：68 个案例，Qwen3.7-plus 双向盲评。
- RAG 开放回答：10 个案例。

完整原始输出、日志、大体积 jsonl 样本和图片不在本目录中提交；需要复现时从 `evaluation/scripts/` 重新生成。
