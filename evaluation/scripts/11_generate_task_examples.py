from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def compact(value: Any, limit: int = 2600) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return text if len(text) <= limit else text[:limit] + "\n... [截断]"


def bb_score(row: dict) -> float:
    metrics = row.get("babybites_metrics") or {}
    task = row["task_type"]
    if task == "candidate_selection":
        return float(metrics.get("accuracy", 0)) + float(metrics.get("macro_f1", 0))
    if task in {"safety_rule_trigger", "counterfactual_consistency"}:
        return float(metrics.get("decision_accuracy", 0)) + float(metrics.get("rule_f1", 0))
    if task == "meal_plan_generation":
        return float(metrics.get("is_7_day_plan", 0)) - float(metrics.get("unsafe_plan_items", 0))
    if task == "profile_extraction":
        return float(metrics.get("field_accuracy", 0))
    return float(metrics.get("candidate_mention_recall", 0)) + 0.1 * float(metrics.get("safety_term_coverage", 0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="outputs/evaluation/evaluation_cases_stratified_10pct_eligible.jsonl")
    parser.add_argument("--results", default="outputs/formal_evaluation_v060702_adapter_stratified100/formal_results.jsonl")
    parser.add_argument("--out", default="outputs/formal_evaluation_v060702_adapter_stratified100/TASK_POSITIVE_NEGATIVE_EXAMPLES_ZH.md")
    args = parser.parse_args()
    cases = {row["case_id"]: row for row in load_jsonl(Path(args.cases))}
    results = load_jsonl(Path(args.results))
    task_names = {
        "candidate_selection": "候选食物选择",
        "safety_rule_trigger": "安全规则触发",
        "meal_plan_generation": "7 天计划生成",
        "profile_extraction": "画像抽取",
        "counterfactual_consistency": "反事实一致性",
        "rag_vs_plain_gpt_judge": "RAG 开放回答",
    }
    lines = [
        "# V060702 各任务正反例",
        "",
        "正例指 BabyBites 在当前自动指标下表现较好的样本；反例指表现较差、适合定位问题的样本。",
    ]
    for task, title in task_names.items():
        rows = [row for row in results if row["task_type"] == task]
        ranked = sorted(rows, key=bb_score)
        examples = [("反例", ranked[0]), ("正例", ranked[-1])]
        lines += ["", f"## {title}"]
        for label, row in examples:
            case = cases[row["case_id"]]
            lines += [
                "",
                f"### {label}：`{row['case_id']}`",
                "",
                f"- BabyBites 自动指标：`{compact(row.get('babybites_metrics'), 800)}`",
                f"- 基线自动指标：`{compact(row.get('baseline_metrics'), 800)}`",
                "",
                "**输入画像/问题**",
                "```json",
                compact({
                    "profile": case.get("baby_profile_structured"),
                    "user_input": case.get("user_input_zh") or case.get("user_input"),
                    "candidate_foods": case.get("candidate_foods"),
                }),
                "```",
                "",
                "**标准答案/期望**",
                "```json",
                compact({
                    "expected_decision": case.get("expected_decision"),
                    "expected_output": case.get("expected_output"),
                    "expected_safe_food_ids": case.get("expected_safe_food_ids"),
                    "expected_caution_food_ids": case.get("expected_caution_food_ids"),
                    "expected_avoid_food_ids": case.get("expected_avoid_food_ids"),
                    "triggered_rule_ids": case.get("triggered_rule_ids"),
                }),
                "```",
                "",
                "**BabyBites 输出**",
                "```json",
                compact(row.get("babybites_output")),
                "```",
                "",
                "**DeepSeek 基线输出**",
                "```json",
                compact(row.get("baseline_output")),
                "```",
            ]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote={args.out}")


if __name__ == "__main__":
    main()
