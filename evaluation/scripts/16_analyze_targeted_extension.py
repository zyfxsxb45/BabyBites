from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, wilcoxon


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def bootstrap_ci(values: np.ndarray, seed: int = 60916, n_boot: int = 30000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    return tuple(np.quantile(samples, [0.025, 0.975]))


def holm_two(p1: float, p2: float) -> tuple[float, float]:
    values = [p1, p2]
    order = np.argsort(values)
    adjusted = [0.0, 0.0]
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (2 - rank) * values[idx]))
        adjusted[idx] = running
    return adjusted[0], adjusted[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-out", default="outputs/formal_evaluation_current_unseen_stratified100")
    parser.add_argument("--extension-out", default="outputs/formal_evaluation_targeted_unseen_extension70")
    args = parser.parse_args()

    base = Path(args.base_out)
    extension = Path(args.extension_out)
    output = extension / "combined_targeted_statistics"
    output.mkdir(parents=True, exist_ok=True)

    formal = load_jsonl(base / "formal_results.jsonl") + load_jsonl(extension / "formal_results.jsonl")
    judges = (
        load_jsonl(base / "third_party_judge" / "judge_results.jsonl")
        + load_jsonl(extension / "third_party_judge" / "judge_results.jsonl")
    )

    # Counterfactual pair accuracy and exact McNemar test.
    pairs: dict[str, list[dict]] = defaultdict(list)
    for row in formal:
        if row["task_type"] == "counterfactual_consistency":
            pairs[row["case_id"].rsplit("_", 1)[0]].append(row)
    complete_pairs = [pair for pair in pairs.values() if len(pair) == 2]
    bb_pair = np.array([
        all(row["babybites_metrics"]["decision_accuracy"] == 1 for row in pair)
        for pair in complete_pairs
    ])
    ds_pair = np.array([
        all(row["baseline_metrics"]["decision_accuracy"] == 1 for row in pair)
        for pair in complete_pairs
    ])
    bb_only = int(np.sum(bb_pair & ~ds_pair))
    ds_only = int(np.sum(~bb_pair & ds_pair))
    discordant = bb_only + ds_only
    cf_p = 1.0 if discordant == 0 else float(binomtest(min(bb_only, ds_only), discordant, 0.5).pvalue)
    cf_diff = bb_pair.astype(float) - ds_pair.astype(float)
    cf_ci = bootstrap_ci(cf_diff, seed=60917)

    # Meal-plan Qwen overall paired Wilcoxon test.
    meal = [row for row in judges if row["task_type"] == "meal_plan_generation"]
    meal_bb = np.array([row["scores"]["babybites"]["overall"] for row in meal], dtype=float)
    meal_ds = np.array([row["scores"]["baseline"]["overall"] for row in meal], dtype=float)
    meal_diff = meal_bb - meal_ds
    meal_p = float(wilcoxon(meal_diff, zero_method="pratt").pvalue) if not np.allclose(meal_diff, 0) else 1.0
    meal_ci = bootstrap_ci(meal_diff, seed=60918)

    cf_holm, meal_holm = holm_two(cf_p, meal_p)
    summary = {
        "counterfactual_consistency": {
            "complete_pairs": len(complete_pairs),
            "babybites_pair_accuracy": float(bb_pair.mean()),
            "baseline_pair_accuracy": float(ds_pair.mean()),
            "paired_difference": float(cf_diff.mean()),
            "ci95": list(cf_ci),
            "bb_only_correct_pairs": bb_only,
            "ds_only_correct_pairs": ds_only,
            "exact_mcnemar_p": cf_p,
            "holm_p_for_two_targeted_tests": cf_holm,
        },
        "meal_plan_generation": {
            "qwen_judged_cases": len(meal),
            "babybites_qwen_overall": float(meal_bb.mean()),
            "baseline_qwen_overall": float(meal_ds.mean()),
            "paired_difference": float(meal_diff.mean()),
            "ci95": list(meal_ci),
            "wilcoxon_p": meal_p,
            "holm_p_for_two_targeted_tests": meal_holm,
        },
    }
    (output / "combined_targeted_statistics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 追加评测合并统计报告",
        "",
        "本报告合并最近一次定稿评测与本轮未使用样本追加评测，只检验预先指定的两个目标任务，并对两个主检验进行 Holm 校正。",
        "",
        "## 反事实一致性",
        "",
        f"- 完整配对数：{len(complete_pairs)}",
        f"- BabyBites 配对准确率：{bb_pair.mean():.3f}",
        f"- 纯 DeepSeek 配对准确率：{ds_pair.mean():.3f}",
        f"- 配对差值：{cf_diff.mean():+.3f}，95% CI [{cf_ci[0]:+.3f}, {cf_ci[1]:+.3f}]",
        f"- 精确 McNemar P：{cf_p:.6g}",
        f"- 两项目标检验 Holm P：{cf_holm:.6g}",
        "",
        "## 周计划生成",
        "",
        f"- Qwen 双盲评分样本数：{len(meal)}",
        f"- BabyBites Qwen Overall：{meal_bb.mean():.3f}",
        f"- 纯 DeepSeek Qwen Overall：{meal_ds.mean():.3f}",
        f"- 配对差值：{meal_diff.mean():+.3f}，95% CI [{meal_ci[0]:+.3f}, {meal_ci[1]:+.3f}]",
        f"- 配对 Wilcoxon P：{meal_p:.6g}",
        f"- 两项目标检验 Holm P：{meal_holm:.6g}",
        "",
        "统计显著性取决于新增样本中效果是否继续存在；扩样不会保证 P 值降低。",
    ]
    (output / "COMBINED_TARGETED_STATISTICAL_REPORT_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote={output}")


if __name__ == "__main__":
    main()
