from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon


ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
EVAL = Path(os.getenv(
    "BABYBITES_STATS_EVAL",
    str(ROOT / "outputs" / "formal_evaluation_current_unseen_stratified100"),
))
OUT = Path(os.getenv("BABYBITES_STATS_OUT", str(EVAL / "statistical_analysis")))
FIG = OUT / "figures"
RNG = np.random.default_rng(20260609)

BB = "#E64B35"
DS = "#2878B5"
GREY = "#666666"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def bootstrap_ci(differences: np.ndarray, n_boot: int = 20000) -> tuple[float, float]:
    differences = np.asarray(differences, dtype=float)
    if len(differences) == 0:
        return math.nan, math.nan
    samples = RNG.choice(differences, size=(n_boot, len(differences)), replace=True).mean(axis=1)
    return tuple(np.quantile(samples, [0.025, 0.975]))


def wilcoxon_p(bb: np.ndarray, ds: np.ndarray) -> float:
    diff = np.asarray(bb, dtype=float) - np.asarray(ds, dtype=float)
    if np.allclose(diff, 0):
        return 1.0
    return float(wilcoxon(diff, alternative="two-sided", zero_method="pratt").pvalue)


def mcnemar_exact_p(bb_correct: np.ndarray, ds_correct: np.ndarray) -> tuple[float, int, int]:
    bb_correct = np.asarray(bb_correct, dtype=bool)
    ds_correct = np.asarray(ds_correct, dtype=bool)
    bb_only = int(np.sum(bb_correct & ~ds_correct))
    ds_only = int(np.sum(~bb_correct & ds_correct))
    discordant = bb_only + ds_only
    p = 1.0 if discordant == 0 else float(binomtest(min(bb_only, ds_only), discordant, 0.5).pvalue)
    return p, bb_only, ds_only


def holm_adjust(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    m = len(p_values)
    for rank, idx in enumerate(order):
        value = min(1.0, (m - rank) * p_values[idx])
        running = max(running, value)
        adjusted[idx] = running
    return adjusted.tolist()


def normalize_candidate_decision(value: object) -> str:
    value = str(value or "").lower()
    if value in {"recommend", "safe"}:
        return "safe"
    if value in {"insufficient_information", "caution"}:
        return "caution"
    if value in {"avoid", "not_ready_for_complementary_food"}:
        return "avoid"
    return value


def candidate_prediction_map(prediction: object) -> dict[str, str]:
    items = prediction.get("items", []) if isinstance(prediction, dict) else []
    return {
        item["food_id"]: normalize_candidate_decision(item.get("decision"))
        for item in items
        if isinstance(item, dict) and item.get("food_id")
    }


def candidate_gold_safety_flags(case: dict, food: dict) -> dict[str, bool]:
    profile = case.get("baby_profile_structured") or {}
    corrected_age = profile.get("corrected_age_month")
    if corrected_age is None:
        corrected_age = profile.get("age_month")
    known = set(profile.get("known_allergens") or [])
    allergy = any(allergen in known and bool(food.get(f"contains_{allergen}")) for allergen in known)
    under_6 = corrected_age is not None and float(corrected_age) < 6
    choking = bool(food.get("is_choking_risk_candidate"))
    min_age = food.get("typical_age_min_month")
    below_food_min = (
        corrected_age is not None and min_age is not None
        and not pd.isna(min_age) and float(corrected_age) < float(min_age)
    )
    forbidden = bool(food.get("is_strictly_forbidden")) or bool(food.get("contains_forbidden_ingredient"))
    ingredient = food.get("ingredient_text")
    unknown = ingredient is None or pd.isna(ingredient) or not bool(str(ingredient).strip())
    return {
        "hard_risk": allergy or under_6 or below_food_min or forbidden,
        "allergy_conflict": allergy,
        "under_6": under_6,
        "choking_risk": choking,
        "unknown_ingredient": unknown,
    }


def candidate_safety_statistical_tests(rows: list[dict]) -> pd.DataFrame:
    definitions = {
        "hard_risk_recall": (
            "higher",
            lambda flags, _gold: flags["hard_risk"],
            lambda pred: pred == "avoid",
        ),
        "allergy_conflict_recall": (
            "higher",
            lambda flags, _gold: flags["allergy_conflict"],
            lambda pred: pred == "avoid",
        ),
        "under_6_block_rate": (
            "higher",
            lambda flags, _gold: flags["under_6"],
            lambda pred: pred == "avoid",
        ),
        "choking_risk_recall": (
            "higher",
            lambda flags, _gold: flags["choking_risk"],
            lambda pred: pred in {"caution", "avoid"},
        ),
        "hard_risk_false_negative_rate": (
            "lower",
            lambda flags, _gold: flags["hard_risk"],
            lambda pred: pred != "avoid",
        ),
        "over_caution_rate": (
            "lower",
            lambda _flags, gold: gold == "safe",
            lambda pred: pred != "safe",
        ),
        "unknown_ingredient_safe_rate": (
            "lower",
            lambda flags, _gold: flags["unknown_ingredient"],
            lambda pred: pred == "safe",
        ),
    }
    paired = {metric: ([], []) for metric in definitions}
    for case in rows:
        expected = case.get("expected_labels") or {}
        bb_map = candidate_prediction_map(case.get("babybites_prediction"))
        ds_map = candidate_prediction_map(case.get("baseline_prediction"))
        for food in case.get("candidate_foods", []):
            food_id = food.get("food_id")
            if not food_id or food_id not in expected:
                continue
            flags = candidate_gold_safety_flags(case, food)
            gold = normalize_candidate_decision(expected[food_id])
            bb_pred = bb_map.get(food_id, "caution")
            ds_pred = ds_map.get(food_id, "caution")
            for metric, (_direction, relevant, event) in definitions.items():
                if relevant(flags, gold):
                    paired[metric][0].append(float(event(bb_pred)))
                    paired[metric][1].append(float(event(ds_pred)))

    tests = []
    for metric, (direction, _relevant, _event) in definitions.items():
        bb, ds = map(np.asarray, paired[metric])
        p_value, bb_only, ds_only = mcnemar_exact_p(bb, ds)
        tests.append({
            "metric": metric,
            "preferred_direction": direction,
            "n_paired_items": len(bb),
            "babybites_rate": float(bb.mean()) if len(bb) else math.nan,
            "baseline_rate": float(ds.mean()) if len(ds) else math.nan,
            "bb_only_event": bb_only,
            "baseline_only_event": ds_only,
            "discordant_pairs": bb_only + ds_only,
            "test": "Exact McNemar",
            "p_value": p_value,
        })
    adjusted = holm_adjust([row["p_value"] for row in tests])
    for row, p_holm in zip(tests, adjusted):
        row["p_holm"] = p_holm
        row["significant_holm_0.05"] = p_holm < 0.05
    return pd.DataFrame(tests)


def format_p(value: float) -> str:
    return "<0.001" if value < 0.001 else f"{value:.3f}"


def metric_row(task: str, metric: str, bb: np.ndarray, ds: np.ndarray, test: str, primary: bool) -> dict:
    bb = np.asarray(bb, dtype=float)
    ds = np.asarray(ds, dtype=float)
    diff = bb - ds
    lo, hi = bootstrap_ci(diff)
    row = {
        "task": task,
        "metric": metric,
        "primary": primary,
        "n_pairs": len(diff),
        "babybites_mean": bb.mean(),
        "baseline_mean": ds.mean(),
        "paired_difference": diff.mean(),
        "ci95_low": lo,
        "ci95_high": hi,
        "test": test,
    }
    if test == "Wilcoxon signed-rank":
        row["p_value"] = wilcoxon_p(bb, ds)
        row["bb_only_correct"] = math.nan
        row["ds_only_correct"] = math.nan
    else:
        p, bb_only, ds_only = mcnemar_exact_p(bb, ds)
        row["p_value"] = p
        row["bb_only_correct"] = bb_only
        row["ds_only_correct"] = ds_only
    return row


def save_figure(fig: plt.Figure, stem: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in [
        ("png", {"dpi": 400}),
        ("pdf", {}),
        ("svg", {}),
        ("tiff", {"dpi": 400}),
    ]:
        fig.savefig(FIG / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def setup_style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Arial", "DejaVu Sans"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 150,
        "savefig.dpi": 400,
    })


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    setup_style()
    results = load_jsonl(EVAL / "formal_results.jsonl")
    judges = load_jsonl(EVAL / "third_party_judge" / "judge_results.jsonl")
    by_task = defaultdict(list)
    for row in results:
        by_task[row["task_type"]].append(row)
    judge_by_task = defaultdict(list)
    for row in judges:
        judge_by_task[row["task_type"]].append(row)

    primary: list[dict] = []
    secondary: list[dict] = []

    rows = by_task["candidate_selection"]
    primary.append(metric_row(
        "候选食物选择", "逐案例 Accuracy",
        [r["babybites_metrics"]["accuracy"] for r in rows],
        [r["baseline_metrics"]["accuracy"] for r in rows],
        "Wilcoxon signed-rank", True,
    ))
    secondary.append(metric_row(
        "候选食物选择", "逐案例 Macro-F1",
        [r["babybites_metrics"]["macro_f1"] for r in rows],
        [r["baseline_metrics"]["macro_f1"] for r in rows],
        "Wilcoxon signed-rank", False,
    ))

    rows = by_task["safety_rule_trigger"]
    primary.append(metric_row(
        "安全规则触发", "决策正确率",
        [r["babybites_metrics"]["decision_accuracy"] for r in rows],
        [r["baseline_metrics"]["decision_accuracy"] for r in rows],
        "Exact McNemar", True,
    ))
    secondary.append(metric_row(
        "安全规则触发", "Risk-type F1",
        [r["babybites_metrics"]["risk_type_f1"] for r in rows],
        [r["baseline_metrics"]["risk_type_f1"] for r in rows],
        "Wilcoxon signed-rank", False,
    ))

    rows = by_task["counterfactual_consistency"]
    pairs = defaultdict(list)
    for row in rows:
        pairs[row["case_id"].rsplit("_", 1)[0]].append(row)
    bb_pair = [float(all(x["babybites_metrics"]["decision_accuracy"] == 1 for x in pair)) for pair in pairs.values()]
    ds_pair = [float(all(x["baseline_metrics"]["decision_accuracy"] == 1 for x in pair)) for pair in pairs.values()]
    primary.append(metric_row("反事实一致性", "完整配对准确率", bb_pair, ds_pair, "Exact McNemar", True))

    rows = by_task["profile_extraction"]
    primary.append(metric_row(
        "画像抽取", "字段准确率",
        [r["babybites_metrics"]["field_accuracy"] for r in rows],
        [r["baseline_metrics"]["field_accuracy"] for r in rows],
        "Wilcoxon signed-rank", True,
    ))

    for task, label in [("meal_plan_generation", "周计划生成"), ("rag_vs_plain_gpt_judge", "RAG 开放回答")]:
        rows = judge_by_task[task]
        primary.append(metric_row(
            label, "Qwen Overall（1–5）",
            [r["scores"]["babybites"]["overall"] for r in rows],
            [r["scores"]["baseline"]["overall"] for r in rows],
            "Wilcoxon signed-rank", True,
        ))
        bb_safety = [float(len(r["safety_errors"]["babybites"]) == 0) for r in rows]
        ds_safety = [float(len(r["safety_errors"]["baseline"]) == 0) for r in rows]
        secondary.append(metric_row(label, "无 Qwen 标记安全错误比例", bb_safety, ds_safety, "Exact McNemar", False))

    rows = by_task["meal_plan_generation"]
    secondary.append(metric_row(
        "周计划生成", "完整 7 天计划率",
        [r["babybites_metrics"]["is_7_day_plan"] for r in rows],
        [r["baseline_metrics"]["is_7_day_plan"] for r in rows],
        "Exact McNemar", False,
    ))
    for metric, label in [("evidence_grounding", "证据依据"), ("parent_friendliness", "家长友好度")]:
        rows = judge_by_task["rag_vs_plain_gpt_judge"]
        secondary.append(metric_row(
            "RAG 开放回答", f"Qwen {label}（1–5）",
            [r["scores"]["babybites"][metric] for r in rows],
            [r["scores"]["baseline"][metric] for r in rows],
            "Wilcoxon signed-rank", False,
        ))

    primary_df = pd.DataFrame(primary)
    primary_df["p_holm"] = holm_adjust(primary_df["p_value"].tolist())
    primary_df["significant_holm_0.05"] = primary_df["p_holm"] < 0.05
    secondary_df = pd.DataFrame(secondary)
    primary_df.to_csv(OUT / "primary_statistical_tests.csv", index=False, encoding="utf-8-sig")
    secondary_df.to_csv(OUT / "secondary_statistical_tests.csv", index=False, encoding="utf-8-sig")

    group = pd.read_csv(EVAL / "group_metrics.csv")
    group.to_csv(OUT / "figure_source_group_metrics.csv", index=False, encoding="utf-8-sig")
    judge_summary = pd.read_csv(EVAL / "third_party_judge" / "judge_summary.csv")
    judge_summary.to_csv(OUT / "figure_source_judge_summary.csv", index=False, encoding="utf-8-sig")

    # Figure 1: primary metrics, normalized to a common 0–1 display scale.
    plot = primary_df[primary_df["task"] != "画像抽取"].copy()
    plot["bb_plot"] = plot["babybites_mean"]
    plot["ds_plot"] = plot["baseline_mean"]
    judge_mask = plot["metric"].str.contains("1–5")
    plot.loc[judge_mask, ["bb_plot", "ds_plot"]] /= 5
    labels = [f"{t}\n{m}" for t, m in zip(plot["task"], plot["metric"])]
    y = np.arange(len(plot))[::-1]
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    for yi, (_, row) in zip(y, plot.iterrows()):
        ax.plot([row["ds_plot"], row["bb_plot"]], [yi, yi], color="#B8B8B8", lw=2, zorder=1)
        ax.scatter(row["ds_plot"], yi, color=DS, s=45, zorder=2)
        ax.scatter(row["bb_plot"], yi, color=BB, s=45, zorder=2)
        ax.text(1.015, yi, f"Δ={row['paired_difference']:+.3f}\nP_Holm={row['p_holm']:.3g}",
                va="center", fontsize=7, color=GREY)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 1.28)
    ax.set_xlabel("主指标表现（Qwen 1–5 分已除以 5，仅用于同图展示）")
    ax.set_title("BabyBites 在规则约束任务上优势更明显，开放回答差异较小", loc="left", fontweight="bold")
    ax.scatter([], [], color=BB, label="BabyBites")
    ax.scatter([], [], color=DS, label="纯 DeepSeek")
    ax.legend(frameon=False, loc="upper left", ncol=2)
    ax.grid(axis="x", color="#E6E6E6", lw=0.6)
    fig.tight_layout()
    save_figure(fig, "figure_1_primary_metrics")
    plot.to_csv(OUT / "figure_1_source_data.csv", index=False, encoding="utf-8-sig")

    # Figure 2: safety-focused grouped bars, separated by preferred direction.
    safety_metrics_high = [
        ("candidate_selection", "hard_risk_recall", "候选选择\n严重风险召回"),
        ("candidate_selection", "allergy_conflict_recall", "候选选择\n过敏冲突召回"),
        ("candidate_selection", "under_6_block_rate", "候选选择\n低于6月阻断率"),
        ("candidate_selection", "choking_risk_recall", "候选选择\n窒息风险召回"),
    ]
    safety_metrics_low = [
        ("candidate_selection", "hard_risk_false_negative_rate", "候选选择\n严重风险漏报率"),
        ("candidate_selection", "over_caution_rate", "候选选择\n安全食物过度警告率"),
        ("candidate_selection", "unknown_ingredient_safe_rate", "未知配料\n误判安全率"),
    ]
    safety_metrics = safety_metrics_high + safety_metrics_low
    safety_rows = []
    for task, metric, label in safety_metrics:
        for system in ["babybites", "baseline"]:
            value = float(group[(group.task_type == task) & (group.system == system)][metric].iloc[0])
            safety_rows.append({"metric": label, "system": system, "value": value})
    safety_df = pd.DataFrame(safety_rows)
    safety_tests = candidate_safety_statistical_tests(by_task["candidate_selection"])
    safety_tests.to_csv(OUT / "figure_2_statistical_tests.csv", index=False, encoding="utf-8-sig")
    safety_test_by_metric = safety_tests.set_index("metric").to_dict("index")
    width = 0.36
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), gridspec_kw={"width_ratios": [4, 3]})
    for ax, metrics, title in zip(
        axes,
        [safety_metrics_high, safety_metrics_low],
        ["越高越好：风险识别与阻断", "越低越好：漏报与过度警告"],
    ):
        labels = [m[2] for m in metrics]
        sub = safety_df[safety_df.metric.isin(labels)]
        x = np.arange(len(metrics))
        bb_vals = [float(sub[(sub.metric == label) & (sub.system == "babybites")].value.iloc[0]) for label in labels]
        ds_vals = [float(sub[(sub.metric == label) & (sub.system == "baseline")].value.iloc[0]) for label in labels]
        bb_bars = ax.bar(x - width / 2, bb_vals, width, color=BB, label="BabyBites")
        ds_bars = ax.bar(x + width / 2, ds_vals, width, color=DS, label="纯 DeepSeek")
        ax.bar_label(bb_bars, labels=[f"{value:.2f}" for value in bb_vals], padding=3, fontsize=7, color=BB)
        ax.bar_label(ds_bars, labels=[f"{value:.2f}" for value in ds_vals], padding=3, fontsize=7, color=DS)
        for xi, (_task, metric, _label) in enumerate(metrics):
            test = safety_test_by_metric[metric]
            ax.text(
                xi, 1.14,
                f"p={format_p(test['p_value'])}\nHolm={format_p(test['p_holm'])}",
                ha="center", va="bottom", fontsize=6.5, color=GREY,
            )
        ax.set_ylim(0, 1.30)
        ax.set_xticks(x, labels)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.grid(axis="y", color="#E6E6E6", lw=0.6)
    axes[0].set_ylabel("比例")
    axes[1].legend(frameon=False, ncol=1, loc="upper right", bbox_to_anchor=(1.0, 1.22))
    fig.suptitle("候选选择安全指标：BabyBites 无严重风险漏报，且过度警告更少",
                 x=0.07, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.text(0.07, 0.01, "Exact paired McNemar tests; Holm correction across the 7 displayed safety metrics.",
             fontsize=7, color=GREY)
    save_figure(fig, "figure_2_safety_metrics")
    safety_df.to_csv(OUT / "figure_2_source_data.csv", index=False, encoding="utf-8-sig")

    # Figure 3: Qwen judge dimensions as horizontal dumbbell plots.
    dimensions = {
        "meal_plan_generation": [
            "age_appropriateness", "allergy_safety", "hard_risk_safety", "nutrition_balance",
            "long_term_plan_quality", "detail_actionability", "candidate_adherence", "overall",
        ],
        "rag_vs_plain_gpt_judge": [
            "age_appropriateness", "allergy_safety", "hard_risk_safety", "nutrition_balance",
            "evidence_grounding", "completeness", "detail_actionability", "parent_friendliness", "overall",
        ],
    }
    names = {
        "age_appropriateness": "月龄适配", "allergy_safety": "过敏安全", "hard_risk_safety": "硬风险安全",
        "nutrition_balance": "营养均衡", "long_term_plan_quality": "长期计划", "detail_actionability": "细节可执行性",
        "candidate_adherence": "候选遵循", "overall": "综合分", "evidence_grounding": "证据依据",
        "completeness": "完整性", "parent_friendliness": "家长友好度",
    }
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.3), sharex=True)
    judge_source = []
    for ax, (task, dims), title in zip(
        axes, dimensions.items(), ["周计划生成", "RAG 开放回答"]
    ):
        sub = judge_summary[judge_summary.task_type == task].set_index("system")
        yy = np.arange(len(dims))[::-1]
        for yi, dim in zip(yy, dims):
            bbv, dsv = float(sub.loc["babybites", dim]), float(sub.loc["baseline", dim])
            judge_source.extend([
                {"task": title, "dimension": names[dim], "system": "babybites", "value": bbv},
                {"task": title, "dimension": names[dim], "system": "baseline", "value": dsv},
            ])
            ax.plot([dsv, bbv], [yi, yi], color="#B8B8B8", lw=2)
            ax.scatter(dsv, yi, color=DS, s=38)
            ax.scatter(bbv, yi, color=BB, s=38)
        ax.set_yticks(yy, [names[d] for d in dims])
        ax.set_xlim(2.8, 5.05)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.grid(axis="x", color="#E6E6E6", lw=0.6)
        ax.set_xlabel("Qwen 双盲评分（1–5）")
    axes[0].scatter([], [], color=BB, label="BabyBites")
    axes[0].scatter([], [], color=DS, label="纯 DeepSeek")
    axes[0].legend(frameon=False, loc="lower left")
    fig.suptitle("第三方盲评揭示不同质量维度的优势与短板", x=0.06, ha="left", fontweight="bold")
    fig.tight_layout()
    save_figure(fig, "figure_3_qwen_dimensions")
    pd.DataFrame(judge_source).to_csv(OUT / "figure_3_source_data.csv", index=False, encoding="utf-8-sig")

    # Figure 4: paired scatter plots for four representative tasks.
    scatter_specs = [
        ("候选食物选择", by_task["candidate_selection"], "accuracy", "babybites_metrics", "baseline_metrics", (0, 1)),
        ("周计划 Qwen Overall", judge_by_task["meal_plan_generation"], "overall", "scores", "scores", (1, 5)),
        ("RAG Qwen Overall", judge_by_task["rag_vs_plain_gpt_judge"], "overall", "scores", "scores", (1, 5)),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.3))
    scatter_source = []
    for ax, (title, rows, metric, bb_key, ds_key, lim) in zip(axes.flat, scatter_specs):
        if bb_key == "scores":
            bbv = np.array([r["scores"]["babybites"][metric] for r in rows], float)
            dsv = np.array([r["scores"]["baseline"][metric] for r in rows], float)
        else:
            bbv = np.array([r[bb_key][metric] for r in rows], float)
            dsv = np.array([r[ds_key][metric] for r in rows], float)
        jitter = RNG.normal(0, (lim[1] - lim[0]) * 0.006, size=(len(rows), 2))
        ax.scatter(dsv + jitter[:, 0], bbv + jitter[:, 1], color=BB, edgecolor="white", lw=0.5, alpha=0.85)
        ax.plot(lim, lim, ls="--", color="#999999", lw=1)
        margin = (lim[1] - lim[0]) * 0.035
        expanded = (lim[0] - margin, lim[1] + margin)
        ax.set_xlim(expanded); ax.set_ylim(expanded)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(f"{title} (n={len(rows)})", loc="left", fontweight="bold")
        ax.set_xlabel("纯 DeepSeek"); ax.set_ylabel("BabyBites")
        for row, xval, yval in zip(rows, dsv, bbv):
            scatter_source.append({"task": title, "case_id": row["case_id"], "baseline": xval, "babybites": yval})
    fig.suptitle("逐样本配对表现：虚线上方表示 BabyBites 更优", x=0.07, ha="left", fontweight="bold")
    fig.tight_layout()
    save_figure(fig, "figure_4_paired_scatter")
    pd.DataFrame(scatter_source).to_csv(OUT / "figure_4_source_data.csv", index=False, encoding="utf-8-sig")

    lines = [
        "# BabyBites 与纯 DeepSeek 指标统计检验",
        "",
        "## 方法",
        "",
        "- 所有检验均为同一评测样本上的配对检验。",
        "- 连续或比例型逐样本指标使用双侧 Wilcoxon signed-rank test。",
        "- 二元正确性指标使用精确 McNemar 检验。",
        "- 效果量为 BabyBites 减去纯 DeepSeek 的平均配对差；95% CI 使用 20,000 次配对 bootstrap。",
        "- 六个任务各指定一个主指标，并使用 Holm 方法校正六个主检验的多重比较。",
        "- 次指标仅用于诊断，不作总体优越性结论。",
        "",
        "## 主指标统计检验",
        "",
        "| 任务 | 主指标 | n | BabyBites | DeepSeek | 配对差值 [95% CI] | 原始 P | Holm P |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for _, r in primary_df.iterrows():
        lines.append(
            f"| {r.task} | {r.metric} | {int(r.n_pairs)} | {r.babybites_mean:.3f} | "
            f"{r.baseline_mean:.3f} | {r.paired_difference:+.3f} "
            f"[{r.ci95_low:+.3f}, {r.ci95_high:+.3f}] | {r.p_value:.4g} | {r.p_holm:.4g} |"
        )
    lines += [
        "",
        "## 次指标诊断性检验",
        "",
        "以下指标用于解释差异来源，未纳入六个主检验的 Holm 校正，不应单独用于宣称总体优越性。",
        "",
        "| 任务 | 次指标 | n | BabyBites | DeepSeek | 配对差值 [95% CI] | P |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: |",
    ]
    for _, r in secondary_df.iterrows():
        lines.append(
            f"| {r.task} | {r.metric} | {int(r.n_pairs)} | {r.babybites_mean:.3f} | "
            f"{r.baseline_mean:.3f} | {r.paired_difference:+.3f} "
            f"[{r.ci95_low:+.3f}, {r.ci95_high:+.3f}] | {r.p_value:.4g} |"
        )
    lines += [
        "",
        "## 解释",
        "",
        "- 候选食物选择是本轮统计证据最稳定的优势；逐案例 Accuracy 的配对差值为正，且经 Holm 校正后仍显著。",
        "- 画像抽取的差值稳定为负，说明当前 BabyBites 结构化抽取显著落后于基线；这同时受到 schema 和中英文实体规范化问题影响。",
        "- 安全规则触发的有效分歧数较少，当前结果不足以判断系统差异；反事实一致性应结合完整配对数、精确检验和置信区间解释。",
        "- 周计划与 RAG 的 Qwen 综合分应结合样本量、置信区间、双向盲评稳定性和定性案例分析，不应只比较均值。",
        "- 统计显著不等于临床有效；本结果衡量的是当前合成评测协议下的系统差异。",
        "",
        "## 图件",
        "",
        "- `figures/figure_1_primary_metrics.*`：六任务主指标与 Holm 校正 P 值。",
        "- `figures/figure_2_safety_metrics.*`：候选选择安全专项指标。",
        "- `figures/figure_3_qwen_dimensions.*`：周计划和 RAG 的第三方盲评维度。",
        "- `figures/figure_4_paired_scatter.*`：代表性任务逐样本配对散点图。",
    ]
    (OUT / "STATISTICAL_REPORT_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    legends = [
        "# 图注",
        "",
        "## Figure 1 | 六类任务的预设主指标比较",
        "",
        "哑铃图比较 BabyBites 与纯 DeepSeek 在除画像抽取外五类任务上的预设主指标。开放任务的 Qwen Overall 为便于同图展示除以 5，图右侧差值仍使用原始量纲。差值定义为 BabyBites 减去纯 DeepSeek。P 值来自配对 Wilcoxon signed-rank test 或精确 McNemar 检验，并对全部六个预设主检验使用 Holm 方法校正。候选食物选择显示稳定的正向差异；其余展示任务的点估计未在当前样本量下达到 Holm 校正后的显著性。",
        "",
        "## Figure 2 | 候选食物选择的安全专项指标",
        "",
        "两个分组柱状图分别展示越高越好的风险识别/阻断指标，以及越低越好的漏报/过度警告指标。BabyBites 在本轮样本中未出现严重风险漏报或未知配料误判安全，并减少了安全食物过度警告。",
        "",
        "## Figure 3 | 周计划与 RAG 的第三方双盲评分维度",
        "",
        "哑铃图展示第三方 Qwen 在不知道系统身份的条件下，对周计划与 RAG 开放回答各质量维度的平均评分。每项采用 1–5 分。各维度差异用于定位系统优势与短板，不应单独解释为临床有效性。",
        "",
        "## Figure 4 | 代表性任务的逐样本配对表现",
        "",
        "每个点代表同一评测样本上 BabyBites 与纯 DeepSeek 的配对表现，虚线上方表示 BabyBites 得分更高。候选食物选择样本多数位于虚线上方；周计划和 RAG 的点分布跨越虚线，显示开放任务中系统优势依赖具体样本。为显示重叠点加入了极小随机抖动，统计检验使用未抖动原始值。",
        "",
        "## 限制",
        "",
        "置信区间使用 20,000 次配对 bootstrap。Qwen 评分属于第三方模型评价，不是临床金标准。画像抽取差异同时受输出 schema 与中英文实体规范化影响。安全专项指标中多个指标在当前样本上达到边界值，因此不应仅凭柱高推断真实总体性能。",
    ]
    (OUT / "FIGURE_LEGENDS_ZH.md").write_text("\n".join(legends), encoding="utf-8")
    print(primary_df[["task", "metric", "n_pairs", "paired_difference", "ci95_low", "ci95_high", "p_value", "p_holm"]])
    print(f"wrote={OUT}")


if __name__ == "__main__":
    main()
