from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/evaluation/evaluation_cases.jsonl")
    parser.add_argument("--output", default="outputs/evaluation/evaluation_cases_stratified_10pct.jsonl")
    parser.add_argument("--fraction", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=60702)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    all_cases = load_jsonl(Path(args.input))
    original_counts = Counter(case["task_type"] for case in all_cases)
    groups: dict[str, list[dict]] = defaultdict(list)
    for case in all_cases:
        age = (case.get("baby_profile_structured") or {}).get("age_month")
        if age is None or not 0 <= int(age) <= 36:
            continue
        groups[case["task_type"]].append(case)

    selected: list[dict] = []
    for task, cases in sorted(groups.items()):
        if task == "counterfactual_consistency":
            pairs: dict[str, list[dict]] = defaultdict(list)
            for case in cases:
                group_id = (case.get("synthetic_generation_trace") or {}).get("counterfactual_group_id")
                pairs[group_id].append(case)
            valid_pairs = [pair for pair in pairs.values() if len(pair) == 2]
            rng.shuffle(valid_pairs)
            pair_count = round(original_counts[task] * args.fraction) // 2
            for pair in valid_pairs[:pair_count]:
                selected.extend(sorted(pair, key=lambda row: row["case_id"]))
        else:
            shuffled = list(cases)
            rng.shuffle(shuffled)
            selected.extend(shuffled[:round(original_counts[task] * args.fraction)])

    selected.sort(key=lambda row: row["case_id"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for case in selected:
            handle.write(json.dumps(case, ensure_ascii=False, default=str) + "\n")
    print(f"selected={len(selected)} tasks={dict(Counter(row['task_type'] for row in selected))}")


if __name__ == "__main__":
    main()
