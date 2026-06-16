from __future__ import annotations

import os
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon


ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
MEAL = ROOT / "outputs" / "formal_evaluation_meal_plan_caution_fallback_v2_68"
BASE = ROOT / "outputs" / "formal_evaluation_current_unseen_stratified100"
EXT = ROOT / "outputs" / "formal_evaluation_targeted_unseen_extension70"
OUT = ROOT / "outputs" / "analysis_caution_fallback_v2_68_with_counterfactual"
FIG = OUT / "figures"

BB = "#D62728"
DS = "#4C78A8"
NEUTRAL = "#8C8C8C"

DIMENSION_ZH = {
    "age_appropriateness": "月龄适配",
    "allergy_safety": "过敏安全",
    "hard_risk_safety": "严重风险安全",
    "nutrition_balance": "营养均衡",
    "long_term_plan_quality": "长期计划能力",
    "detail_actionability": "详细与可执行性",
    "candidate_adherence": "候选池遵循",
    "overall": "总体评分",
}


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def bootstrap_ci(values: np.ndarray, seed: int, n_boot: int = 30000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    return tuple(np.quantile(samples, [0.025, 0.975]))


def exact_mcnemar(a: np.ndarray, b: np.ndarray) -> tuple[int, int, float]:
    a_only = int(np.sum(a & ~b))
    b_only = int(np.sum(~a & b))
    discordant = a_only + b_only
    p = 1.0 if discordant == 0 else float(binomtest(min(a_only, b_only), discordant, 0.5).pvalue)
    return a_only, b_only, p


def save_figure(fig: plt.Figure, stem: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in [
        ("png", {"dpi": 300}),
        ("pdf", {}),
        ("svg", {}),
        ("tiff", {"dpi": 300}),
    ]:
        fig.savefig(FIG / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def concise(items: list[str], limit: int = 2) -> str:
    cleaned = [str(x).strip() for x in items if str(x).strip()]
    return "；".join(cleaned[:limit]) or "无明确判词"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 150,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })

    formal = load_jsonl(MEAL / "formal_results.jsonl")
    judges = load_jsonl(MEAL / "third_party_judge" / "judge_results.jsonl")
    judge_summary = pd.read_csv(MEAL / "third_party_judge" / "judge_summary.csv")
    group = pd.read_csv(MEAL / "group_metrics.csv")

    bb_overall = np.array([r["scores"]["babybites"]["overall"] for r in judges], dtype=float)
    ds_overall = np.array([r["scores"]["baseline"]["overall"] for r in judges], dtype=float)
    overall_diff = bb_overall - ds_overall
    overall_ci = bootstrap_ci(overall_diff, 61020)
    overall_p = float(wilcoxon(overall_diff, zero_method="pratt").pvalue)

    meal_by_id = {r["case_id"]: r for r in formal}
    bb_7 = np.array([bool(meal_by_id[r["case_id"]]["babybites_metrics"]["is_7_day_plan"]) for r in judges])
    ds_7 = np.array([bool(meal_by_id[r["case_id"]]["baseline_metrics"]["is_7_day_plan"]) for r in judges])
    bb7_only, ds7_only, seven_p = exact_mcnemar(bb_7, ds_7)

    all_formal = load_jsonl(BASE / "formal_results.jsonl") + load_jsonl(EXT / "formal_results.jsonl")
    pairs: dict[str, list[dict]] = defaultdict(list)
    for row in all_formal:
        if row["task_type"] == "counterfactual_consistency":
            pairs[row["case_id"].rsplit("_", 1)[0]].append(row)
    complete_pairs = [rows for rows in pairs.values() if len(rows) == 2]
    cf_bb = np.array([
        all(row["babybites_metrics"]["decision_accuracy"] == 1 for row in rows)
        for rows in complete_pairs
    ])
    cf_ds = np.array([
        all(row["baseline_metrics"]["decision_accuracy"] == 1 for row in rows)
        for rows in complete_pairs
    ])
    cf_bb_only, cf_ds_only, cf_p = exact_mcnemar(cf_bb, cf_ds)
    cf_diff = cf_bb.astype(float) - cf_ds.astype(float)
    cf_ci = bootstrap_ci(cf_diff, 61021)

    wins = Counter(r["winner"] for r in judges)
    bb_safety = sum(bool(r["safety_errors"]["babybites"]) for r in judges)
    ds_safety = sum(bool(r["safety_errors"]["baseline"]) for r in judges)
    bb_modes = Counter(r["babybites_prediction"].get("mode", "unknown") for r in formal)

    dimensions = list(DIMENSION_ZH)
    dimension_rows = []
    for dim in dimensions:
        bb = np.array([r["scores"]["babybites"][dim] for r in judges], dtype=float)
        ds = np.array([r["scores"]["baseline"][dim] for r in judges], dtype=float)
        diff = bb - ds
        p = float(wilcoxon(diff, zero_method="pratt").pvalue) if not np.allclose(diff, 0) else 1.0
        lo, hi = bootstrap_ci(diff, 61022 + len(dimension_rows))
        dimension_rows.append({
            "dimension": dim,
            "dimension_zh": DIMENSION_ZH[dim],
            "babybites_mean": bb.mean(),
            "baseline_mean": ds.mean(),
            "difference": diff.mean(),
            "ci95_low": lo,
            "ci95_high": hi,
            "wilcoxon_p": p,
        })
    dimensions_df = pd.DataFrame(dimension_rows)

    result_rows = []
    for row in judges:
        result_rows.append({
            "case_id": row["case_id"],
            "winner": row["winner"],
            "babybites_overall": row["scores"]["babybites"]["overall"],
            "baseline_overall": row["scores"]["baseline"]["overall"],
            "difference": row["scores"]["babybites"]["overall"] - row["scores"]["baseline"]["overall"],
            "babybites_safety_error": bool(row["safety_errors"]["babybites"]),
            "baseline_safety_error": bool(row["safety_errors"]["baseline"]),
            "winner_reason": row.get("winner_reason", ""),
            "babybites_strengths": concise(row["strengths"]["babybites"]),
            "babybites_weaknesses": concise(row["weaknesses"]["babybites"]),
            "baseline_strengths": concise(row["strengths"]["baseline"]),
            "baseline_weaknesses": concise(row["weaknesses"]["baseline"]),
        })
    per_case = pd.DataFrame(result_rows).sort_values("difference", ascending=False)

    summary = {
        "meal_plan_caution_fallback_v2": {
            "cases": len(judges),
            "wins": dict(wins),
            "babybites_overall": float(bb_overall.mean()),
            "baseline_overall": float(ds_overall.mean()),
            "paired_difference": float(overall_diff.mean()),
            "ci95": list(overall_ci),
            "wilcoxon_p": overall_p,
            "babybites_7_day_rate": float(bb_7.mean()),
            "baseline_7_day_rate": float(ds_7.mean()),
            "seven_day_exact_mcnemar_p": seven_p,
            "babybites_safety_error_cases": bb_safety,
            "baseline_safety_error_cases": ds_safety,
            "babybites_generation_modes": dict(bb_modes),
        },
        "counterfactual_consistency_new_combined": {
            "complete_pairs": len(complete_pairs),
            "babybites_pair_accuracy": float(cf_bb.mean()),
            "baseline_pair_accuracy": float(cf_ds.mean()),
            "paired_difference": float(cf_diff.mean()),
            "ci95": list(cf_ci),
            "babybites_only_correct_pairs": cf_bb_only,
            "baseline_only_correct_pairs": cf_ds_only,
            "exact_mcnemar_p": cf_p,
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    dimensions_df.to_csv(OUT / "meal_plan_qwen_dimension_statistics.csv", index=False, encoding="utf-8-sig")
    per_case.to_csv(OUT / "meal_plan_per_case_judge_summary.csv", index=False, encoding="utf-8-sig")

    # Figure 1: primary outcomes with their natural scales.
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 4.2))
    panels = [
        ("周计划 Qwen Overall", bb_overall.mean(), ds_overall.mean(), (0, 5), f"n=68\nWilcoxon p={overall_p:.3g}"),
        ("周计划 7天完整率", bb_7.mean(), ds_7.mean(), (0, 1.05), f"n=68\nMcNemar p={seven_p:.3g}"),
        ("反事实完整配对准确率", cf_bb.mean(), cf_ds.mean(), (0, 1.05), f"n={len(complete_pairs)} pairs\nMcNemar p={cf_p:.3g}"),
    ]
    for ax, (title, bbv, dsv, ylim, note) in zip(axes, panels):
        bars = ax.bar(["BabyBites", "DeepSeek"], [bbv, dsv], color=[BB, DS], width=0.62)
        ax.set_title(title, fontsize=11)
        ax.set_ylim(*ylim)
        ax.text(
            0.5, 0.80, note, transform=ax.transAxes, ha="center", va="top", fontsize=8.5,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 2},
        )
        for bar, value in zip(bars, [bbv, dsv]):
            ax.text(bar.get_x() + bar.get_width() / 2, value + (ylim[1] * 0.025), f"{value:.3f}", ha="center", fontsize=9)
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("新 caution fallback 周计划协议与反事实一致性主指标", fontsize=13, y=1.02)
    save_figure(fig, "figure_1_primary_outcomes")

    # Figure 2: Qwen dimensions.
    plot_dims = dimensions_df.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    y = np.arange(len(plot_dims))
    for yi, (_, row) in zip(y, plot_dims.iterrows()):
        ax.plot([row["baseline_mean"], row["babybites_mean"]], [yi, yi], color="#C7C7C7", lw=2)
        ax.scatter(row["baseline_mean"], yi, color=DS, s=52, zorder=2)
        ax.scatter(row["babybites_mean"], yi, color=BB, s=72, zorder=3)
    ax.set_yticks(y, plot_dims["dimension_zh"])
    ax.set_xlim(3.2, 5.05)
    ax.set_xlabel("Qwen3.7-plus 双盲评分（0–5，越高越好）")
    ax.set_title("周计划各维度：BB 仅在详细与可执行性领先")
    ax.grid(axis="x", alpha=0.2)
    ax.scatter([], [], color=BB, s=72, label="BabyBites")
    ax.scatter([], [], color=DS, s=52, label="DeepSeek")
    ax.legend(frameon=False, loc="lower right")
    save_figure(fig, "figure_2_meal_plan_qwen_dimensions")

    # Figure 3: wins and safety error cases, separated because direction differs.
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 4.2))
    win_bars = axes[0].bar(["BabyBites", "DeepSeek", "平局"], [wins["babybites"], wins["baseline"], wins["tie"]],
                           color=[BB, DS, NEUTRAL])
    axes[0].set_title("Qwen 双盲胜负")
    axes[0].set_ylabel("样本数")
    for bar in win_bars:
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.6, str(int(bar.get_height())), ha="center")
    error_bars = axes[1].bar(["BabyBites", "DeepSeek"], [bb_safety, ds_safety], color=[BB, DS])
    axes[1].set_title("Qwen 标记安全错误样本（越低越好）")
    for bar in error_bars:
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.12, str(int(bar.get_height())), ha="center")
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
    save_figure(fig, "figure_3_wins_and_safety_errors")

    # Figure 4: paired per-case overall scores.
    fig, ax = plt.subplots(figsize=(5.8, 5.2))
    jitter = np.random.default_rng(61023).normal(0, 0.025, size=(len(judges), 2))
    ax.scatter(ds_overall + jitter[:, 0], bb_overall + jitter[:, 1], color=BB, alpha=0.7, s=34)
    ax.plot([0, 5], [0, 5], ls="--", color=NEUTRAL, lw=1)
    ax.set_xlim(0.8, 5.2)
    ax.set_ylim(0.8, 5.2)
    ax.set_xlabel("DeepSeek Qwen Overall")
    ax.set_ylabel("BabyBites Qwen Overall")
    ax.set_title("周计划逐样本配对评分")
    ax.text(1.0, 5.0, "虚线上方：BB更高", fontsize=8.5, color=BB)
    ax.grid(alpha=0.18)
    save_figure(fig, "figure_4_meal_plan_paired_scatter")

    best_bb = per_case.iloc[0]
    best_ds = per_case.iloc[-1]
    bb_error_ids = per_case.loc[per_case.babybites_safety_error, "case_id"].tolist()
    ds_error_ids = per_case.loc[per_case.baseline_safety_error, "case_id"].tolist()
    report = [
        "# 新 caution fallback 协议 68 例结果与反事实一致性",
        "",
        "## 数据口径",
        "",
        "- 周计划：`formal_evaluation_meal_plan_caution_fallback_v2_68`，68 条统一新 prompt 样本，Qwen3.7-plus 双盲评分。",
        "- 反事实一致性：最近定稿 100 例与未使用样本追加 70 例合并后的 15 个完整 A/B 配对。",
        "- 所有新图输出到独立目录，未覆盖旧图。",
        "",
        "## 周计划主结果",
        "",
        f"- 胜负完全持平：BabyBites {wins['babybites']} 胜，DeepSeek {wins['baseline']} 胜，平局 {wins['tie']}。",
        f"- Qwen Overall：BabyBites {bb_overall.mean():.3f}，DeepSeek {ds_overall.mean():.3f}；配对差值 {overall_diff.mean():+.3f}，"
        f"95% CI [{overall_ci[0]:+.3f}, {overall_ci[1]:+.3f}]，Wilcoxon p={overall_p:.4g}。",
        f"- 7天完整率：BabyBites {bb_7.mean():.3f}，DeepSeek {ds_7.mean():.3f}；精确 McNemar p={seven_p:.4g}。",
        f"- Qwen 标记安全错误样本：BabyBites {bb_safety}/68，DeepSeek {ds_safety}/68。",
        f"- BabyBites 生成模式：{dict(bb_modes)}。",
        "",
        "## 维度解释",
        "",
        "- BabyBites 的明确优势是详细与可执行性，平均分高于 DeepSeek。",
        "- DeepSeek 在过敏安全、严重风险安全、候选池遵循、营养均衡、长期计划能力和总体评分上更高。",
        "- 单维度未校正检验中，营养均衡与详细可执行性达到 p<0.05；若对 8 个维度做多重比较校正，则不应直接宣称这些维度差异已统计显著。",
        "- 新协议已实现候选不足时的 caution fallback，但没有在本轮显著提高 BB 的总体胜率；BB 仍需提高完整 7 天输出率。",
        "",
        "## 安全错误审计",
        "",
        "- Qwen 原始判词标记 BabyBites 7 例、DeepSeek 4 例安全错误；该数字不能直接等同于确定性安全错误。",
        "- BB 的 `EV00463`、`EV00471`、`EV00631` 均为 12–22 月龄整颗葡萄案例。BB 已附切小块/不可整颗喂警告，符合当前“可加工管理 caution 可纳入”的协议，但 Qwen 仍按不得纳入判错，属于 judge 与协议解释冲突。",
        "- 较明确的 BB 问题包括：`EV00566` 未遵守避免海鲜偏好；`EV00638` 同时引入多种新食物；部分案例中 BB 与 judge 对 suitable 数量和潜在过敏原分级不同。",
        "- 因此正式汇报应同时报告“Qwen 标记安全错误数”和“人工协议审计后的明确错误数”，不应只引用前者。",
        "",
        "## 反事实一致性新结果",
        "",
        f"- 完整配对准确率：BabyBites {cf_bb.mean():.3f}，DeepSeek {cf_ds.mean():.3f}。",
        f"- 配对差值 {cf_diff.mean():+.3f}，95% CI [{cf_ci[0]:+.3f}, {cf_ci[1]:+.3f}]。",
        f"- BB 单独正确 {cf_bb_only} 对，DS 单独正确 {cf_ds_only} 对；精确 McNemar p={cf_p:.6g}。",
        "- 该任务中 BabyBites 的优势明确且具有统计显著性。",
        "",
        "## 典型正反例",
        "",
        f"- BabyBites 优势例 `{best_bb.case_id}`，Overall 差值 {best_bb.difference:+.1f}。判词：{best_bb.winner_reason}",
        f"- DeepSeek 优势例 `{best_ds.case_id}`，Overall 差值 {best_ds.difference:+.1f}。判词：{best_ds.winner_reason}",
        f"- BabyBites 被标记安全错误的样本：{', '.join(bb_error_ids) if bb_error_ids else '无'}。",
        f"- DeepSeek 被标记安全错误的样本：{', '.join(ds_error_ids) if ds_error_ids else '无'}。",
        "",
        "## 输出文件",
        "",
        "- `figures/figure_1_primary_outcomes.*`：新协议周计划主指标和反事实一致性。",
        "- `figures/figure_2_meal_plan_qwen_dimensions.*`：周计划 Qwen 各维度。",
        "- `figures/figure_3_wins_and_safety_errors.*`：胜负与安全错误。",
        "- `figures/figure_4_meal_plan_paired_scatter.*`：逐样本配对评分。",
        "- `meal_plan_per_case_judge_summary.csv`：每例胜负、分差和判词摘要。",
    ]
    (OUT / "RESULT_SUMMARY_ZH.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote={OUT}")


if __name__ == "__main__":
    main()
