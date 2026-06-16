from __future__ import annotations

import argparse
import glob
import json
import random
from collections import Counter
from pathlib import Path


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
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--count", type=int, default=0, help="0 selects every unseen eligible case.")
    parser.add_argument("--history-glob", default="outputs/formal_evaluation*/formal_results.jsonl")
    parser.add_argument("--seed", type=int, default=20260610)
    args = parser.parse_args()

    history_paths = sorted(Path(path) for path in glob.glob(args.history_glob))
    used_ids = {
        row["case_id"]
        for path in history_paths
        for row in load_jsonl(path)
        if row.get("case_id")
    }
    pool = [
        row
        for row in load_jsonl(Path(args.input))
        if row.get("task_type") == args.task
        and row.get("case_id") not in used_ids
        and 0 <= int((row.get("baby_profile_structured") or {}).get("age_month", 0)) <= 36
    ]
    random.Random(args.seed).shuffle(pool)
    selected = pool if args.count <= 0 else pool[:args.count]
    selected.sort(key=lambda row: row["case_id"])

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in selected),
        encoding="utf-8",
    )
    manifest = {
        "task": args.task,
        "seed": args.seed,
        "source": args.input,
        "history_glob": args.history_glob,
        "history_files": [str(path) for path in history_paths],
        "historical_unique_case_ids_excluded": len(used_ids),
        "eligible_unseen_count": len(pool),
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
