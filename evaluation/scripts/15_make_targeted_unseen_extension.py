from __future__ import annotations

import argparse
import glob
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def age_bin(row: dict) -> str:
    age = float((row.get("baby_profile_structured") or {}).get("corrected_age_month", 0))
    if age < 6:
        return "under_6"
    if age < 9:
        return "6_8"
    if age < 12:
        return "9_11"
    return "12_plus"


def stratified_take(rows: list[dict], n: int, rng: random.Random) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(age_bin(row), str(row.get("expected_decision")))].append(row)
    for group in groups.values():
        rng.shuffle(group)

    selected = []
    keys = sorted(groups)
    while len(selected) < n and any(groups.values()):
        for key in keys:
            if groups[key] and len(selected) < n:
                selected.append(groups[key].pop())
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/evaluation/evaluation_cases.jsonl")
    parser.add_argument("--output", default="outputs/evaluation/evaluation_cases_targeted_unseen_extension70.jsonl")
    parser.add_argument("--manifest", default="outputs/evaluation/evaluation_cases_targeted_unseen_extension70_manifest.json")
    parser.add_argument("--history-glob", default="outputs/formal_evaluation*/formal_results.jsonl")
    parser.add_argument("--meal-plan-count", type=int, default=50)
    parser.add_argument("--counterfactual-pairs", type=int, default=10)
    parser.add_argument("--seed", type=int, default=60915)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    history_paths = sorted(Path(".").glob(args.history_glob))
    used_ids = {
        row["case_id"]
        for path in history_paths
        for row in load_jsonl(path)
        if row.get("case_id")
    }
    eligible = [
        row for row in load_jsonl(Path(args.input))
        if row.get("case_id") not in used_ids
        and 0 <= int((row.get("baby_profile_structured") or {}).get("age_month", 0)) <= 36
    ]

    meal_pool = [row for row in eligible if row["task_type"] == "meal_plan_generation"]
    if len(meal_pool) < args.meal_plan_count:
        raise RuntimeError(f"Need {args.meal_plan_count} unseen meal plans, found {len(meal_pool)}")
    meal_selected = stratified_take(meal_pool, args.meal_plan_count, rng)

    pairs: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        if row["task_type"] == "counterfactual_consistency":
            group_id = (row.get("synthetic_generation_trace") or {}).get("counterfactual_group_id")
            pairs[str(group_id)].append(row)
    complete_pairs = [
        sorted(pair, key=lambda row: row["case_id"])
        for pair in pairs.values()
        if len(pair) == 2
    ]
    rng.shuffle(complete_pairs)
    if len(complete_pairs) < args.counterfactual_pairs:
        raise RuntimeError(
            f"Need {args.counterfactual_pairs} unseen counterfactual pairs, found {len(complete_pairs)}"
        )
    counterfactual_selected = [
        row for pair in complete_pairs[:args.counterfactual_pairs] for row in pair
    ]

    selected = sorted(meal_selected + counterfactual_selected, key=lambda row: row["case_id"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in selected),
        encoding="utf-8",
    )

    manifest = {
        "seed": args.seed,
        "source": args.input,
        "history_files": [str(path) for path in history_paths],
        "historical_unique_case_ids_excluded": len(used_ids),
        "selected_count": len(selected),
        "task_counts": dict(Counter(row["task_type"] for row in selected)),
        "meal_plan_strata": dict(Counter(
            f"{age_bin(row)}::{row.get('expected_decision')}" for row in meal_selected
        )),
        "counterfactual_complete_pairs": args.counterfactual_pairs,
        "selected_case_ids": [row["case_id"] for row in selected],
        "overlap_with_history": sorted({row["case_id"] for row in selected} & used_ids),
    }
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
