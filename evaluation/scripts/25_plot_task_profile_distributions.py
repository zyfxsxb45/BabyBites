from __future__ import annotations

import json
import math
import os
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
INPUT = Path(os.getenv(
    "BABYBITES_PROFILE_DIST_INPUT",
    str(ROOT / "outputs" / "statistical_analysis_combined_counterfactual15" / "_analysis_input" / "formal_results.jsonl"),
))
OUT = Path(os.getenv(
    "BABYBITES_PROFILE_DIST_OUT",
    str(ROOT / "outputs" / "task_profile_distributions_current"),
))
FIG = OUT / "figures"

TASK_NAMES = {
    "candidate_selection": "候选食物选择",
    "safety_rule_trigger": "安全规则触发",
    "meal_plan_generation": "周计划生成",
    "profile_extraction": "画像抽取",
    "counterfactual_consistency": "反事实一致性",
    "rag_vs_plain_gpt_judge": "RAG开放回答",
}
TASK_ORDER = list(TASK_NAMES)
COLORS = ["#E64B35", "#2878B5", "#3C9D77", "#F2A541", "#7A68A6", "#6B6B6B"]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def clean_category(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "unknown"
    text = str(value).strip().lower()
    return text if text else "unknown"


def profile_frame(rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        p = row.get("baby_profile_structured") or {}
        known = p.get("known_allergens") or []
        tried = p.get("tried_foods") or []
        records.append({
            "case_id": row["case_id"],
            "task_type": row["task_type"],
            "task": TASK_NAMES.get(row["task_type"], row["task_type"]),
            "source_dataset": clean_category(p.get("source_dataset")),
            "age_month": pd.to_numeric(p.get("age_month"), errors="coerce"),
            "corrected_age_month": pd.to_numeric(p.get("corrected_age_month"), errors="coerce"),
            "sex": clean_category(p.get("sex")),
            "is_preterm": bool(p.get("is_preterm", False)),
            "birth_weight_kg": pd.to_numeric(p.get("birth_weight_kg"), errors="coerce"),
            "feeding_method": clean_category(p.get("feeding_method")),
            "wic_participation": bool(p.get("wic_participation", False)),
            "eczema_history": bool(p.get("eczema_history", False)),
            "suspected_allergy_history": bool(p.get("suspected_allergy_history", False)),
            "known_allergen_count": len(known),
            "known_allergens": "|".join(map(str, known)),
            "tried_food_count": len(tried),
            "budget_level": clean_category(p.get("budget_level")),
            "prefer_homemade": bool(p.get("prefer_homemade", False)),
            "has_feedback_reaction": bool(p.get("feedback_food_name") or p.get("feedback_reaction")),
        })
    frame = pd.DataFrame(records)
    frame["task"] = pd.Categorical(frame["task"], [TASK_NAMES[x] for x in TASK_ORDER], ordered=True)
    return frame.sort_values(["task", "case_id"])


def setup_style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Arial", "DejaVu Sans"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 150,
    })


def save(fig: plt.Figure, stem: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in [("png", {"dpi": 400}), ("pdf", {}), ("svg", {})]:
        fig.savefig(FIG / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def annotated_heatmap(ax: plt.Axes, data: pd.DataFrame, fmt: str, cmap: str, title: str) -> None:
    values = data.to_numpy(dtype=float)
    image = ax.imshow(values, aspect="auto", cmap=cmap, vmin=0, vmax=max(1, np.nanmax(values)))
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            value = values[i, j]
            text = fmt.format(value)
            ax.text(j, i, text, ha="center", va="center", fontsize=7,
                    color="white" if value > np.nanmax(values) * 0.55 else "#222222")
    ax.set_xticks(np.arange(data.shape[1]), data.columns, rotation=30, ha="right")
    ax.set_yticks(np.arange(data.shape[0]), data.index)
    ax.set_title(title, loc="left", fontweight="bold")
    plt.colorbar(image, ax=ax, fraction=0.025, pad=0.02)


def plot_overview(df: pd.DataFrame) -> None:
    task_labels = [TASK_NAMES[x] for x in TASK_ORDER]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    counts = df["task"].value_counts().reindex(task_labels).fillna(0)
    bars = axes[0, 0].barh(task_labels[::-1], counts[::-1], color=COLORS[::-1])
    axes[0, 0].bar_label(bars, padding=3, fontsize=8)
    axes[0, 0].set_title("各任务实际纳入的画像数量", loc="left", fontweight="bold")
    axes[0, 0].set_xlabel("评测案例数")
    axes[0, 0].grid(axis="x", color="#E6E6E6", lw=0.6)

    age_groups = [df.loc[df.task == task, "age_month"].dropna().to_numpy() for task in task_labels]
    violin = axes[0, 1].violinplot(
        age_groups,
        positions=np.arange(1, len(task_labels) + 1),
        showmeans=False,
        showmedians=True,
        showextrema=False,
        widths=0.8,
    )
    for body, color in zip(violin["bodies"], COLORS):
        body.set_facecolor(color)
        body.set_edgecolor(color)
        body.set_alpha(0.35)
    violin["cmedians"].set_color("#333333")
    violin["cmedians"].set_linewidth(1.2)
    rng = np.random.default_rng(20260610)
    for i, values in enumerate(age_groups, 1):
        axes[0, 1].scatter(
            rng.normal(i, 0.055, len(values)), values,
            s=13, alpha=0.58, color=COLORS[i - 1], edgecolor="white", linewidth=0.25,
        )
    axes[0, 1].set_xticks(np.arange(1, len(task_labels) + 1), task_labels)
    axes[0, 1].set_title("各任务月龄分布（小提琴与散点）", loc="left", fontweight="bold")
    axes[0, 1].set_ylabel("月龄")
    axes[0, 1].tick_params(axis="x", rotation=30)
    axes[0, 1].grid(axis="y", color="#E6E6E6", lw=0.6)

    age_bins = pd.cut(df["age_month"], [-0.1, 5, 8, 11, 23, 36], labels=["0–5", "6–8", "9–11", "12–23", "24–36"])
    age_heat = pd.crosstab(df["task"], age_bins, normalize="index").reindex(task_labels).fillna(0) * 100
    annotated_heatmap(axes[1, 0], age_heat, "{:.0f}%", "Blues", "月龄阶段构成（任务内百分比）")

    source = pd.crosstab(df["task"], df["source_dataset"], normalize="index").reindex(task_labels).fillna(0) * 100
    annotated_heatmap(axes[1, 1], source, "{:.0f}%", "Greens", "画像来源构成（任务内百分比）")

    fig.suptitle("当前正式评测样本的宝宝画像分布", x=0.06, ha="left", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save(fig, "figure_1_task_profile_overview")
    age_heat.to_csv(OUT / "age_stage_distribution_pct.csv", encoding="utf-8-sig")
    source.to_csv(OUT / "source_dataset_distribution_pct.csv", encoding="utf-8-sig")


def plot_risk_features(df: pd.DataFrame) -> None:
    task_labels = [TASK_NAMES[x] for x in TASK_ORDER]
    features = {
        "早产": "is_preterm",
        "有已知过敏原": "known_allergen_count",
        "疑似过敏史": "suspected_allergy_history",
        "湿疹史": "eczema_history",
        "WIC参与": "wic_participation",
        "有近期不良反应": "has_feedback_reaction",
        "偏好自制": "prefer_homemade",
        "出生体重缺失": "birth_weight_kg",
    }
    rows = []
    for task in task_labels:
        sub = df[df.task == task]
        record = {}
        for label, column in features.items():
            if label == "有已知过敏原":
                record[label] = (sub[column] > 0).mean() * 100
            elif label == "出生体重缺失":
                record[label] = sub[column].isna().mean() * 100
            else:
                record[label] = sub[column].astype(bool).mean() * 100
        rows.append(pd.Series(record, name=task))
    prevalence = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    annotated_heatmap(ax, prevalence, "{:.0f}%", "Reds", "核心风险与偏好字段比例（任务内百分比）")
    fig.tight_layout()
    save(fig, "figure_2_task_profile_risk_prevalence")
    prevalence.to_csv(OUT / "risk_feature_prevalence_pct.csv", encoding="utf-8-sig")


def plot_categorical_composition(df: pd.DataFrame) -> None:
    task_labels = [TASK_NAMES[x] for x in TASK_ORDER]
    specs = [
        ("sex", "性别构成"),
        ("feeding_method", "喂养方式构成"),
        ("budget_level", "预算等级构成"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.8), sharey=True)
    source_rows = []
    palette = ["#2878B5", "#E64B35", "#3C9D77", "#F2A541", "#7A68A6", "#A0A0A0"]
    for ax, (column, title) in zip(axes, specs):
        table = pd.crosstab(df["task"], df[column], normalize="index").reindex(task_labels).fillna(0) * 100
        left = np.zeros(len(table))
        for i, category in enumerate(table.columns):
            values = table[category].to_numpy()
            ax.barh(table.index, values, left=left, color=palette[i % len(palette)], label=category)
            for task, value in zip(table.index, values):
                source_rows.append({"field": column, "task": task, "category": category, "percentage": value})
            left += values
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlabel("任务内百分比")
        ax.set_xlim(0, 100)
        ax.grid(axis="x", color="#E6E6E6", lw=0.6)
        ax.legend(frameon=False, fontsize=7, loc="lower center", bbox_to_anchor=(0.5, -0.28), ncol=2)
    fig.suptitle("各任务宝宝画像的分类字段构成", x=0.06, ha="left", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    save(fig, "figure_3_task_profile_categorical_composition")
    pd.DataFrame(source_rows).to_csv(OUT / "categorical_composition_pct.csv", index=False, encoding="utf-8-sig")


def plot_allergens(df: pd.DataFrame) -> None:
    task_labels = [TASK_NAMES[x] for x in TASK_ORDER]
    allergens = sorted({
        allergen
        for value in df["known_allergens"]
        for allergen in value.split("|")
        if allergen
    })
    records = []
    for task in task_labels:
        values = df.loc[df.task == task, "known_allergens"]
        denom = len(values)
        records.append(pd.Series({
            allergen: sum(allergen in value.split("|") for value in values) / denom * 100 if denom else 0
            for allergen in allergens
        }, name=task))
    table = pd.DataFrame(records).fillna(0)
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    annotated_heatmap(ax, table, "{:.0f}%", "Purples", "各任务已知过敏原分布（任务内百分比）")
    fig.tight_layout()
    save(fig, "figure_4_task_profile_allergen_distribution")
    table.to_csv(OUT / "known_allergen_distribution_pct.csv", encoding="utf-8-sig")


def write_summary(df: pd.DataFrame) -> None:
    summary = df.groupby("task", observed=True).agg(
        cases=("case_id", "count"),
        age_mean=("age_month", "mean"),
        age_median=("age_month", "median"),
        age_min=("age_month", "min"),
        age_max=("age_month", "max"),
        preterm_pct=("is_preterm", lambda x: x.mean() * 100),
        known_allergy_pct=("known_allergen_count", lambda x: (x > 0).mean() * 100),
        suspected_allergy_pct=("suspected_allergy_history", lambda x: x.mean() * 100),
        feedback_reaction_pct=("has_feedback_reaction", lambda x: x.mean() * 100),
    )
    summary.to_csv(OUT / "task_profile_summary.csv", encoding="utf-8-sig")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    setup_style()
    df = profile_frame(load_jsonl(INPUT))
    df.to_csv(OUT / "task_profile_source_data.csv", index=False, encoding="utf-8-sig")
    write_summary(df)
    plot_overview(df)
    plot_risk_features(df)
    plot_categorical_composition(df)
    plot_allergens(df)
    print(df.groupby("task", observed=True).size())
    print(f"wrote={OUT}")


if __name__ == "__main__":
    main()
