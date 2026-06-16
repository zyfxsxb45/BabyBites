from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
BASE = ROOT / "outputs" / "formal_evaluation_current_unseen_stratified100"
EXT = ROOT / "outputs" / "formal_evaluation_targeted_unseen_extension70"
MEAL = ROOT / "outputs" / "formal_evaluation_meal_plan_caution_fallback_v2_68"
OUT = ROOT / "outputs" / "statistical_analysis_combined_counterfactual15"
INPUT = OUT / "_analysis_input"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )


def average_bidirectional_judges() -> list[dict]:
    original = {
        row["case_id"]: row
        for row in load_jsonl(MEAL / "third_party_judge" / "judge_results.jsonl")
    }
    reversed_rows = {
        row["case_id"]: row
        for row in load_jsonl(MEAL / "third_party_judge_reversed" / "judge_results.jsonl")
    }
    integrated = {
        row["case_id"]: row
        for row in load_jsonl(MEAL / "bidirectional_judge" / "bidirectional_integrated_results.jsonl")
    }
    rows = []
    for case_id in sorted(original.keys() & reversed_rows.keys()):
        first = original[case_id]
        second = reversed_rows[case_id]
        scores = {}
        safety_errors = {}
        for system in ("babybites", "baseline"):
            dimensions = first["scores"][system].keys()
            scores[system] = {
                dimension: (
                    float(first["scores"][system][dimension])
                    + float(second["scores"][system][dimension])
                ) / 2
                for dimension in dimensions
            }
            # Count only stable safety errors that both mapping orders identify.
            safety_errors[system] = (
                first["safety_errors"][system]
                if first["safety_errors"][system] and second["safety_errors"][system]
                else []
            )
        rows.append({
            "case_id": case_id,
            "task_type": "meal_plan_generation",
            "judge_model": "qwen3.7-plus_bidirectional_mean",
            "winner": integrated[case_id]["final_winner"],
            "scores": scores,
            "safety_errors": safety_errors,
            "strengths": {"babybites": [], "baseline": []},
            "weaknesses": {"babybites": [], "baseline": []},
            "winner_reason": "",
        })
    return rows


def build_judge_summary(judges: list[dict]) -> pd.DataFrame:
    records = []
    task_dimensions = {
        "meal_plan_generation": [
            "age_appropriateness", "allergy_safety", "hard_risk_safety",
            "nutrition_balance", "long_term_plan_quality", "detail_actionability",
            "candidate_adherence", "overall",
        ],
        "rag_vs_plain_gpt_judge": [
            "age_appropriateness", "allergy_safety", "hard_risk_safety",
            "nutrition_balance", "evidence_grounding", "completeness",
            "detail_actionability", "parent_friendliness", "overall",
        ],
    }
    for task, dimensions in task_dimensions.items():
        task_rows = [row for row in judges if row["task_type"] == task]
        for system in ("babybites", "baseline"):
            record = {
                "task_type": task,
                "system": system,
                "cases": len(task_rows),
                "wins": sum(row["winner"] == system for row in task_rows),
                "ties": sum(row["winner"] == "tie" for row in task_rows),
                "safety_error_cases": sum(bool(row["safety_errors"][system]) for row in task_rows),
            }
            for dimension in dimensions:
                values = [float(row["scores"][system][dimension]) for row in task_rows]
                record[dimension] = sum(values) / len(values) if values else None
            records.append(record)
    return pd.DataFrame(records)


def main() -> None:
    INPUT.mkdir(parents=True, exist_ok=True)
    (INPUT / "third_party_judge").mkdir(parents=True, exist_ok=True)

    base_results = load_jsonl(BASE / "formal_results.jsonl")
    extension_results = load_jsonl(EXT / "formal_results.jsonl")
    meal_results = load_jsonl(MEAL / "formal_results.jsonl")
    combined_results = [
        row for row in base_results
        if row["task_type"] not in {"counterfactual_consistency", "meal_plan_generation"}
    ]
    combined_results += [
        row for row in base_results + extension_results
        if row["task_type"] == "counterfactual_consistency"
    ]
    combined_results += [
        row for row in meal_results if row["task_type"] == "meal_plan_generation"
    ]
    write_jsonl(INPUT / "formal_results.jsonl", combined_results)

    base_judges = [
        row for row in load_jsonl(BASE / "third_party_judge" / "judge_results.jsonl")
        if row["task_type"] != "meal_plan_generation"
    ]
    averaged_meal_judges = average_bidirectional_judges()
    combined_judges = base_judges + averaged_meal_judges
    write_jsonl(INPUT / "third_party_judge" / "judge_results.jsonl", combined_judges)

    base_group = pd.read_csv(BASE / "group_metrics.csv")
    meal_group = pd.read_csv(MEAL / "group_metrics.csv")
    combined_group = pd.concat([
        base_group[base_group.task_type != "meal_plan_generation"],
        meal_group[meal_group.task_type == "meal_plan_generation"],
    ], ignore_index=True, sort=False)
    combined_group.to_csv(INPUT / "group_metrics.csv", index=False, encoding="utf-8-sig")
    build_judge_summary(combined_judges).to_csv(
        INPUT / "third_party_judge" / "judge_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    manifest = {
        "base_tasks_source": str(BASE),
        "counterfactual_sources": [str(BASE), str(EXT)],
        "counterfactual_complete_pairs": 15,
        "meal_plan_source": str(MEAL),
        "meal_plan_cases": len(averaged_meal_judges),
        "meal_plan_judge": "qwen3.7-plus",
        "meal_plan_score_rule": "Per-case mean of original and exactly reversed A/B judge scores.",
        "meal_plan_winner_rule": "Keep system winner only when both directions agree; otherwise tie.",
        "meal_plan_stable_safety_error_rule": "Count safety error only when both directions mark that system.",
        "deprecated_for_meal_plan": "All earlier qwen-plus meal-plan judge results.",
        "final_winners": dict(Counter(row["winner"] for row in averaged_meal_judges)),
    }
    (OUT / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["BABYBITES_STATS_EVAL"] = str(INPUT)
    env["BABYBITES_STATS_OUT"] = str(OUT)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "14_statistical_analysis_and_figures.py")],
        cwd=ROOT,
        env=env,
        check=True,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"wrote={OUT}")


if __name__ == "__main__":
    main()
