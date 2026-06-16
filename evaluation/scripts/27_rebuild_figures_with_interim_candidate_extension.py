from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
SOURCE = ROOT / "outputs" / "statistical_analysis_combined_counterfactual15" / "_analysis_input"
BASE = ROOT / "outputs" / "formal_evaluation_current_unseen_stratified100" / "formal_results.jsonl"
EXTENSION = ROOT / "outputs" / "formal_evaluation_candidate_selection_unseen141_v20260610" / "progress.jsonl"
OUT = ROOT / "outputs" / "statistical_analysis_combined_counterfactual15_candidate_interim"
INPUT = OUT / "_analysis_input"


def load_jsonl_snapshot(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )


def load_eval_module():
    os.environ.setdefault("BABYBITES_APP_ROOT", str(ROOT))
    path = Path(__file__).resolve().parent / "07_run_formal_task_evaluation.py"
    spec = importlib.util.spec_from_file_location("formal_eval", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    source_rows = load_jsonl_snapshot(SOURCE / "formal_results.jsonl")
    base_candidate = [
        row for row in load_jsonl_snapshot(BASE)
        if row["task_type"] == "candidate_selection"
    ]
    extension_candidate = [
        row for row in load_jsonl_snapshot(EXTENSION)
        if row["task_type"] == "candidate_selection"
    ]
    candidate_by_id = {row["case_id"]: row for row in base_candidate}
    for row in extension_candidate:
        candidate_by_id[row["case_id"]] = row
    candidates = list(candidate_by_id.values())
    combined = [row for row in source_rows if row["task_type"] != "candidate_selection"] + candidates

    INPUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(INPUT / "formal_results.jsonl", combined)
    judge_dir = INPUT / "third_party_judge"
    judge_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE / "third_party_judge" / "judge_results.jsonl", judge_dir / "judge_results.jsonl")
    shutil.copy2(SOURCE / "third_party_judge" / "judge_summary.csv", judge_dir / "judge_summary.csv")

    formal_eval = load_eval_module()
    formal_eval.group_metrics(combined).to_csv(
        INPUT / "group_metrics.csv", index=False, encoding="utf-8-sig"
    )
    manifest = {
        "source_analysis": str(SOURCE),
        "candidate_base_cases": len(base_candidate),
        "candidate_extension_snapshot_cases": len(extension_candidate),
        "candidate_combined_unique_cases": len(candidates),
        "other_tasks_unchanged": True,
        "note": "Interim snapshot while candidate extension evaluation was still running.",
    }
    (OUT / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
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
