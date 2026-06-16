from __future__ import annotations

import os
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon


ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()


def load_jsonl_snapshot(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A running evaluation may leave its final line incomplete during the snapshot.
            continue
    return rows


def load_stats_module():
    path = ROOT / "scripts" / "14_statistical_analysis_and_figures.py"
    spec = importlib.util.spec_from_file_location("babybites_stats", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        default="outputs/formal_evaluation_current_unseen_stratified100/formal_results.jsonl",
    )
    parser.add_argument(
        "--extension",
        default="outputs/formal_evaluation_candidate_selection_unseen141_v20260610/progress.jsonl",
    )
    parser.add_argument(
        "--out",
        default="outputs/interim_candidate_selection_statistics_v20260610",
    )
    args = parser.parse_args()

    base = [row for row in load_jsonl_snapshot(ROOT / args.base) if row["task_type"] == "candidate_selection"]
    extension = [
        row for row in load_jsonl_snapshot(ROOT / args.extension)
        if row["task_type"] == "candidate_selection"
    ]
    by_id = {row["case_id"]: row for row in base}
    base_ids = set(by_id)
    for row in extension:
        by_id[row["case_id"]] = row
    rows = list(by_id.values())

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot_manifest.json").write_text(json.dumps({
        "base_unique_cases": len(base_ids),
        "extension_complete_unique_cases": len({row["case_id"] for row in extension}),
        "extension_overlap_with_base": sorted(base_ids & {row["case_id"] for row in extension}),
        "combined_unique_cases": len(rows),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    stats = load_stats_module()
    safety = stats.candidate_safety_statistical_tests(rows)
    safety.to_csv(out / "combined_safety_mcnemar_tests.csv", index=False, encoding="utf-8-sig")

    bb_case = np.asarray([row["babybites_metrics"]["accuracy"] for row in rows], dtype=float)
    ds_case = np.asarray([row["baseline_metrics"]["accuracy"] for row in rows], dtype=float)
    case_summary = {
        "n_cases": len(rows),
        "babybites_mean_accuracy": float(bb_case.mean()),
        "baseline_mean_accuracy": float(ds_case.mean()),
        "paired_mean_difference": float((bb_case - ds_case).mean()),
        "wilcoxon_p_value": float(wilcoxon(bb_case - ds_case, zero_method="pratt").pvalue),
        "bb_better_cases": int(np.sum(bb_case > ds_case)),
        "baseline_better_cases": int(np.sum(ds_case > bb_case)),
        "tied_cases": int(np.sum(ds_case == bb_case)),
    }
    (out / "combined_case_accuracy_test.json").write_text(
        json.dumps(case_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    item_bb, item_ds = [], []
    for row in rows:
        expected = row.get("expected_labels") or {}
        bb_map = stats.candidate_prediction_map(row.get("babybites_prediction"))
        ds_map = stats.candidate_prediction_map(row.get("baseline_prediction"))
        for food_id, gold in expected.items():
            gold = stats.normalize_candidate_decision(gold)
            item_bb.append(bb_map.get(food_id, "caution") == gold)
            item_ds.append(ds_map.get(food_id, "caution") == gold)
    p_value, bb_only, ds_only = stats.mcnemar_exact_p(item_bb, item_ds)
    item_summary = {
        "n_candidate_items": len(item_bb),
        "babybites_item_accuracy": float(np.mean(item_bb)),
        "baseline_item_accuracy": float(np.mean(item_ds)),
        "bb_only_correct": bb_only,
        "baseline_only_correct": ds_only,
        "discordant_items": bb_only + ds_only,
        "exact_mcnemar_p_value": p_value,
    }
    (out / "combined_item_accuracy_mcnemar_test.json").write_text(
        json.dumps(item_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(case_summary, ensure_ascii=False, indent=2))
    print(json.dumps(item_summary, ensure_ascii=False, indent=2))
    print(safety.to_string(index=False))
    print(f"wrote={out}")


if __name__ == "__main__":
    main()
