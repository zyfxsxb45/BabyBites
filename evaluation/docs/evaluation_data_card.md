# 评估数据卡

## 数据来源概述
使用本地 IFPS2、NHANES1999、WIC_ITFPS-2 文件探索结果作为字段和分布线索；评估画像与候选食物为规则化合成，不复制真实受试者。

生成评估样本 1000 条。

## 任务类型数量
{
  "candidate_selection": 250,
  "safety_rule_trigger": 200,
  "meal_plan_generation": 200,
  "profile_extraction": 150,
  "counterfactual_consistency": 100,
  "rag_vs_plain_gpt_judge": 100
}

## 月龄段数量
{
  "6-8": 175,
  "9-11": 259,
  "<6": 160,
  "12-23": 406
}

hard-rule case 数量：466；caution case 数量：359；insufficient information case 数量：12；反事实样本数量：100。

## 已知局限
部分原始库为 PDF 或 SAS7BDAT，当前最小可运行版本未完整抽取所有 codebook；过敏史和部分营养成分由规则化合成补足；阈值需在 configs/rule_thresholds.yaml 人工确认。

## RAG vs Plain GPT 使用方式
将同一 user_input、baby_profile_structured、candidate_foods 分别送入 RAG 系统和普通 GPT，再把两个输出填入 judge_prompt_template 进行盲评。

本评估集仅用于系统评估，不应当作真实医学建议。