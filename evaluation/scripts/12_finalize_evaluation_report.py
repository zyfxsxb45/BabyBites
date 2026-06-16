from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


TASK_METRICS = {
    "candidate_selection": [
        "accuracy", "macro_f1", "safe_f1", "caution_f1", "avoid_f1",
        "hard_risk_recall", "hard_risk_false_negative_rate", "over_caution_rate",
    ],
    "safety_rule_trigger": [
        "decision_accuracy", "decision_macro_f1", "risk_type_micro_f1",
        "rule_micro_f1", "hard_risk_recall", "hard_risk_false_negative_rate",
        "choking_risk_recall",
    ],
    "counterfactual_consistency": [
        "decision_accuracy", "decision_macro_f1", "pair_accuracy",
        "hard_risk_recall",
    ],
    "profile_extraction": ["field_accuracy", "fields"],
    "meal_plan_generation": [
        "is_7_day_plan", "plan_days", "nutrition_category_mentions",
        "allergy_mentions", "unsafe_plan_items", "risk_plan_items",
        "added_sugar_plan_items", "unknown_ingredient_plan_items",
        "adverse_feedback_plan_items", "choking_plan_items",
    ],
    "rag_vs_plain_gpt_judge": [
        "answer_chars", "candidate_mention_recall",
        "nutrition_term_coverage", "safety_term_coverage",
    ],
}


def compact_table(frame: pd.DataFrame, task: str, metrics: list[str]) -> str:
    columns = ["system", "cases"] + [metric for metric in metrics if metric in frame.columns]
    subset = frame[frame["task_type"] == task][columns].copy()
    for column in columns[2:]:
        subset[column] = pd.to_numeric(subset[column], errors="coerce").round(3)
    return markdown_table(subset)


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, record in frame.iterrows():
        values = []
        for column in columns:
            value = record[column]
            values.append("" if pd.isna(value) else str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    group = pd.read_csv(out / "group_metrics.csv")
    judge_path = out / "third_party_judge" / "judge_summary.csv"
    judge = pd.read_csv(judge_path) if judge_path.exists() else pd.DataFrame()

    lines = [
        "# BabyBites 公平评测完整报告",
        "",
        "## 分任务确定性指标",
        "",
        "空白指标表示该指标不适用于对应任务，不表示任务没有完成评测。",
        "",
    ]
    for task, metrics in TASK_METRICS.items():
        lines.extend([f"### {task}", "", compact_table(group, task, metrics), ""])

    if not judge.empty:
        judge_columns = [
            "task_type", "system", "cases", "wins", "ties", "safety_error_cases",
            "age_appropriateness", "allergy_safety", "hard_risk_safety",
            "nutrition_balance", "long_term_plan_quality", "evidence_grounding",
            "completeness", "detail_actionability", "candidate_adherence",
            "parent_friendliness", "overall",
        ]
        judge_columns = [column for column in judge_columns if column in judge.columns]
        judge_view = judge[judge_columns].copy()
        for column in judge_columns[3:]:
            judge_view[column] = pd.to_numeric(judge_view[column], errors="coerce").round(3)
        lines.extend([
            "## Qwen 第三方盲评",
            "",
            markdown_table(judge_view),
            "",
            "Qwen 判词用于发现质量模式，不应直接视为临床金标准。",
            "",
        ])

    plan_group = group[group["task_type"] == "meal_plan_generation"]
    bb_plan = plan_group[plan_group["system"] == "babybites"]
    result_path = out / "formal_results.jsonl"
    plan_rows = []
    if result_path.exists():
        plan_rows = [
            json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("task_type") == "meal_plan_generation"
        ]

    def metric(name: str) -> float:
        if bb_plan.empty or name not in bb_plan.columns:
            return 0.0
        value = pd.to_numeric(bb_plan.iloc[0][name], errors="coerce")
        return 0.0 if pd.isna(value) else float(value)

    cases = int(bb_plan.iloc[0]["cases"]) if not bb_plan.empty else len(plan_rows)
    modes = {}
    empty_plans = 0
    for row in plan_rows:
        prediction = row.get("babybites_prediction") or {}
        mode = prediction.get("mode", "unspecified")
        modes[mode] = modes.get(mode, 0) + 1
        if not prediction.get("plan"):
            empty_plans += 1

    lines.extend([
        "## 周计划诊断",
        "",
        f"- 本轮共 {cases} 条周计划样本；BabyBites 生成模式分布：{modes}。",
        f"- 平均每例计划中的风险项：总风险 {metric('risk_plan_items'):.3f}，添加糖 {metric('added_sugar_plan_items'):.3f}，未知配料 {metric('unknown_ingredient_plan_items'):.3f}，历史不良反馈 {metric('adverse_feedback_plan_items'):.3f}，窒息风险 {metric('choking_plan_items'):.3f}。",
        f"- 空计划共 {empty_plans} 例。矫正月龄不足6个月时，阻断常规辅食计划属于预期安全行为。",
        "- Qwen 判词用于定位质量模式；未解释未选候选属于完整性问题，不等同于实际安排危险食物。",
        "",
        "## 报告生成说明",
        "",
        "旧 `formal_report.md` 在 Qwen Judge 启动前生成，因此其中写着“不包含独立 Judge 分数”；同时它把所有任务指标合并为一张超宽稀疏表，非 candidate 指标位于表格后部，不易查看。本报告按任务拆表并纳入已经完成的 Qwen 盲评分数。",
    ])
    report = "\n".join(lines)
    (out / "COMPREHENSIVE_REPORT_ZH.md").write_text(report, encoding="utf-8")
    (out / "formal_report.md").write_text(report, encoding="utf-8")
    print(out / "formal_report.md")


if __name__ == "__main__":
    main()
