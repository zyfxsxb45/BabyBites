from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd

from babybites_common import (
    FOOD_LIBRARY,
    REPO_ROOT,
    default_rules,
    ensure_dirs,
    normalize_food_record,
    save_table,
    stable_hash,
    write_yaml,
    read_yaml,
)


def feeding_statuses(mode: str, rng: random.Random) -> tuple[str, str]:
    if mode == "母乳":
        return "current", "not_current"
    if mode == "配方奶":
        return "not_current", "current"
    if mode == "混合喂养":
        return "current", "current"
    return rng.choice(["current", "not_current", "unknown"]), rng.choice(["current", "not_current", "unknown"])


def build_profiles(n: int, seed: int, empirical: dict | None = None) -> pd.DataFrame:
    rng = random.Random(seed)
    goals = ["第一口辅食", "补铁", "便秘", "湿疹/过敏担心", "预算低", "方便快捷", "营养均衡"]
    feeding = ["母乳", "配方奶", "混合喂养", "未知"]
    tried_sets = [[], ["rice cereal", "pumpkin puree"], ["rice cereal", "pumpkin puree", "beef puree", "banana"], ["rice cereal", "tofu puree", "yogurt"]]
    allergen_sets = [[], ["milk"], ["egg"], ["wheat"], ["soy"], ["milk", "egg"], ["suspected_eczema_related"]]
    avoid_sets = [[], ["seafood"], ["dairy"], ["sweetened_food"], ["high_sodium"], ["seafood", "dairy"]]
    feedback_foods = ["", "beef puree", "pumpkin puree", "yogurt", "egg custard", "iron fortified rice cereal"]
    feedback_reactions = ["unknown", "diarrhea", "rash", "vomiting", "none"]
    rows = []
    for i in range(n):
        empirical_months = (((empirical or {}).get("wic_itfps2") or {}).get("available_months") or [])
        infant_months = [4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 18, 22]
        older_months = [m for m in empirical_months if isinstance(m, int) and 12 <= m <= 72]
        age = rng.choice(infant_months if rng.random() < 0.85 or not older_months else older_months)
        is_preterm = rng.random() < 0.22
        gest = rng.choice([30, 32, 34, 35, 36]) if is_preterm else rng.choice([39, 40])
        corrected = max(0, round(age - max(0, 40 - gest) / 4.345, 1)) if is_preterm else age
        allergens = rng.choice(allergen_sets)
        mode = rng.choice(feeding)
        breastfeeding_status, formula_status = feeding_statuses(mode, rng)
        birth_weight_g = rng.choice([2300, 2600, 3000, 3300, 3600, None])
        goal = rng.choice(goals)
        feedback_food = rng.choice(feedback_foods)
        feedback_reaction = "unknown" if not feedback_food else rng.choice(feedback_reactions)
        rows.append({
            "seed_id": f"B{i:04d}",
            "source_dataset": rng.choice(["nhanes1999_distribution_seed", "wic_itfps2_distribution_seed", "ifps2_document_seed"]),
            "source_record_id_hash": stable_hash(f"profile-{seed}-{i}"),
            "age_month": age,
            "age_week": round(age * 4.345, 1),
            "sex": rng.choice(["female", "male", "unknown"]),
            "gestational_age_week": gest,
            "is_preterm": is_preterm,
            "corrected_age_month": corrected,
            "birth_weight_g": birth_weight_g,
            "birth_weight_kg": round(birth_weight_g / 1000, 2) if birth_weight_g else None,
            "feeding_mode": mode,
            "feeding_method": {"母乳": "breast", "配方奶": "formula", "混合喂养": "mixed", "未知": "unknown"}.get(mode, "unknown"),
            "breastfeeding_status": breastfeeding_status,
            "formula_status": formula_status,
            "wic_participation": rng.choice([True, False, None]),
            "eczema_history": "suspected_eczema_related" in allergens or rng.random() < 0.12,
            "suspected_allergy_history": bool(allergens),
            "known_allergens": allergens if "suspected_eczema_related" not in allergens else [],
            "tried_foods": rng.choice(tried_sets),
            "not_tried_foods": [],
            "parent_goal_seed": goal,
            "notes_zh": f"家长目标：{goal}",
            "notes_en": {
                "第一口辅食": "Parent goal: first complementary food",
                "补铁": "Parent goal: increase iron intake",
                "便秘": "Parent goal: support bowel regularity",
                "湿疹/过敏担心": "Parent goal: eczema or allergy concern",
                "预算低": "Parent goal: low budget",
                "方便快捷": "Parent goal: convenience",
                "营养均衡": "Parent goal: balanced nutrition",
            }.get(goal, "Parent goal: balanced nutrition"),
            "budget_level": rng.choice(["low", "medium", "high", "unknown"]),
            "prefer_homemade": rng.choice([True, False]),
            "avoid_categories": rng.choice(avoid_sets),
            "feedback_food_name": feedback_food,
            "feedback_reaction": feedback_reaction,
            "feedback_date": "" if not feedback_food else rng.choice(["2026-05-27", "2026-05-28", "2026-06-01"]),
            "socioeconomic_context": rng.choice(["WIC participant", "income unknown", "general population"]),
            "raw_variable_trace": {"synthetic": True, "source": "distribution_and_rule_sampling", "empirical_distribution_sources": list((empirical or {}).keys())},
            "synthetic_injected": True,
        })
    return pd.DataFrame(rows)


def build_foods() -> pd.DataFrame:
    rows = [normalize_food_record(i + 1, rec) for i, rec in enumerate(FOOD_LIBRARY)]
    return pd.DataFrame(rows)


def build_rules(out: Path) -> pd.DataFrame:
    rules = default_rules()
    write_yaml(out / "rules.yaml", rules)
    rows = [{"rule_id": rid, **body} for rid, body in rules.items()]
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="evaluation/configs/generation_config.yaml")
    parser.add_argument("--out", default="outputs/normalized")
    parser.add_argument("--n-profiles", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    ensure_dirs()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text("n_total: 1000\nseed: 42\nuse_empirical_distributions: true\n", encoding="utf-8")
    thresholds = REPO_ROOT / "evaluation" / "configs" / "rule_thresholds.yaml"
    if not thresholds.exists():
        thresholds.write_text("high_sodium_mg: 200\nmin_complementary_food_age_month: 6\n", encoding="utf-8")
    empirical = {}
    empirical_path = REPO_ROOT / "outputs/empirical/empirical_distributions.json"
    if empirical_path.exists():
        import json
        empirical = json.loads(empirical_path.read_text(encoding="utf-8"))
    profiles = build_profiles(args.n_profiles, args.seed, empirical)
    foods = build_foods()
    rules = build_rules(out)
    save_table(profiles, out / "baby_profile_seeds.csv", out / "baby_profile_seeds.parquet")
    save_table(foods, out / "food_candidate_pool.csv", out / "food_candidate_pool.parquet")
    save_table(rules, out / "rules.csv")
    print(f"profiles={len(profiles)} foods={len(foods)} rules={len(rules)}")


if __name__ == "__main__":
    main()
