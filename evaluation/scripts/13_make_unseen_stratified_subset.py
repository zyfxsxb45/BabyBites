from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_QUOTAS = {
    "candidate_selection": 25,
    "safety_rule_trigger": 20,
    "meal_plan_generation": 20,
    "profile_extraction": 15,
    "counterfactual_consistency": 10,
    "rag_vs_plain_gpt_judge": 10,
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/evaluation/evaluation_cases.jsonl")
    parser.add_argument("--output", default="outputs/evaluation/evaluation_cases_unseen_stratified100.jsonl")
    parser.add_argument("--manifest", default="outputs/evaluation/evaluation_cases_unseen_stratified100_manifest.json")
    parser.add_argument("--history-glob", default="outputs/formal_evaluation*/formal_results.jsonl")
    parser.add_argument("--seed", type=int, default=60803)
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
        row
        for row in load_jsonl(Path(args.input))
        if row.get("case_id") not in used_ids
        and 0 <= int((row.get("baby_profile_structured") or {}).get("age_month", 0)) <= 36
    ]
    by_task: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        by_task[row["task_type"]].append(row)

    selected: list[dict] = []
    for task, quota in DEFAULT_QUOTAS.items():
        if task != "counterfactual_consistency":
            pool = list(by_task[task])
            rng.shuffle(pool)
            if len(pool) < quota:
                raise RuntimeError(f"{task}: need {quota} unseen cases, only {len(pool)} available")
            selected.extend(pool[:quota])
            continue

        pairs: dict[str, list[dict]] = defaultdict(list)
        for row in by_task[task]:
            group_id = (row.get("synthetic_generation_trace") or {}).get("counterfactual_group_id")
            pairs[str(group_id)].append(row)
        valid_pairs = [
            sorted(pair, key=lambda row: row["case_id"])
            for pair in pairs.values()
            if len(pair) == 2
        ]
        rng.shuffle(valid_pairs)
        required_pairs = quota // 2
        if len(valid_pairs) < required_pairs:
            raise RuntimeError(
                f"{task}: need {required_pairs} unseen pairs, only {len(valid_pairs)} available"
            )
        for pair in valid_pairs[:required_pairs]:
            selected.extend(pair)

    selected.sort(key=lambda row: row["case_id"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in selected),
        encoding="utf-8",
    )

    manifest = {
        "seed": args.seed,
        "source": str(Path(args.input)),
        "output": str(output),
        "history_files": [str(path) for path in history_paths],
        "historical_unique_case_ids_excluded": len(used_ids),
        "selected_count": len(selected),
        "task_counts": dict(Counter(row["task_type"] for row in selected)),
        "selected_case_ids": [row["case_id"] for row in selected],
        "overlap_with_history": sorted({row["case_id"] for row in selected} & used_ids),
    }
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
