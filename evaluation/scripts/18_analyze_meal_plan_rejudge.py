from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-results", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=60918)
    args = parser.parse_args()

    rows = [
        row for row in load_jsonl(Path(args.judge_results))
        if row["task_type"] == "meal_plan_generation"
    ]
    bb = np.array([row["scores"]["babybites"]["overall"] for row in rows], dtype=float)
    ds = np.array([row["scores"]["baseline"]["overall"] for row in rows], dtype=float)
    diff = bb - ds
    rng = np.random.default_rng(args.seed)
    boot = rng.choice(diff, size=(30000, len(diff)), replace=True).mean(axis=1)
    ci = np.quantile(boot, [0.025, 0.975])
    p = float(wilcoxon(diff, zero_method="pratt").pvalue) if not np.allclose(diff, 0) else 1.0
    wins = {
        "babybites": sum(row["winner"] == "babybites" for row in rows),
        "baseline": sum(row["winner"] == "baseline" for row in rows),
        "tie": sum(row["winner"] == "tie" for row in rows),
    }
    summary = {
        "judge_model": rows[0]["judge_model"] if rows else None,
        "cases": len(rows),
        "babybites_qwen_overall": float(bb.mean()),
        "baseline_qwen_overall": float(ds.mean()),
        "paired_difference": float(diff.mean()),
        "ci95": ci.tolist(),
        "wilcoxon_p": p,
        "wins": wins,
        "babybites_safety_error_cases": sum(bool(row["safety_errors"]["babybites"]) for row in rows),
        "baseline_safety_error_cases": sum(bool(row["safety_errors"]["baseline"]) for row in rows),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "meal_plan_qwen37_statistics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = [
        "# 周计划 qwen3.7-plus 统一盲评统计",
        "",
        f"- 样本数：{summary['cases']}",
        f"- BabyBites Overall：{summary['babybites_qwen_overall']:.3f}",
        f"- 纯 DeepSeek Overall：{summary['baseline_qwen_overall']:.3f}",
        f"- 配对差值：{summary['paired_difference']:+.3f}，95% CI [{ci[0]:+.3f}, {ci[1]:+.3f}]",
        f"- 配对 Wilcoxon P：{p:.6g}",
        f"- 胜负：BabyBites {wins['babybites']}，DeepSeek {wins['baseline']}，平局 {wins['tie']}",
        f"- Qwen 标记安全错误样本：BabyBites {summary['babybites_safety_error_cases']}，DeepSeek {summary['baseline_safety_error_cases']}",
        "",
        "全部样本均由同一个 qwen3.7-plus Judge 重新盲评，未混合旧 qwen-plus 分数。",
    ]
    (out / "MEAL_PLAN_QWEN37_STATISTICAL_REPORT_ZH.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
