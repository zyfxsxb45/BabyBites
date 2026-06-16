from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    by_id = {}
    source_counts = {}
    for source in args.sources:
        rows = load_jsonl(Path(source))
        meal_rows = [row for row in rows if row["task_type"] == "meal_plan_generation"]
        source_counts[source] = len(meal_rows)
        for row in meal_rows:
            by_id[row["case_id"]] = row

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = [by_id[case_id] for case_id in sorted(by_id)]
    (out / "formal_results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest = {
        "sources": source_counts,
        "unique_meal_plan_cases": len(rows),
        "case_ids": [row["case_id"] for row in rows],
    }
    (out / "merge_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
