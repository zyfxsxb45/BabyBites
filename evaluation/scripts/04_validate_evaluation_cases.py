from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from babybites_common import ALLERGENS, REPO_ROOT, load_rules


REQUIRED = [
    "case_id", "task_type", "source_datasets", "baby_profile_structured", "baby_profile_text",
    "candidate_foods", "user_input", "expected_output", "expected_decision",
    "expected_safe_food_ids", "expected_avoid_food_ids", "expected_caution_food_ids",
    "triggered_rule_ids", "positive_factor_rule_ids", "risk_types", "difficulty_tags",
    "evaluation_rubric", "gold_rationale", "evidence_trace", "synthetic_generation_trace",
    "data_quality_flags",
]
ALLOWED = {"recommend", "safe", "caution", "avoid", "insufficient_information", "not_ready_for_complementary_food"}


def normalized(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def validate_counterfactual_pairs(cases: list[dict]) -> list[dict]:
    errors = []
    groups = defaultdict(list)
    for case in cases:
        if case.get("task_type") == "counterfactual_consistency":
            gid = (case.get("synthetic_generation_trace") or {}).get("counterfactual_group_id")
            groups[gid].append(case)
    for gid, pair in groups.items():
        label = gid or "<missing_group_id>"
        if len(pair) != 2:
            errors.append({"case_id": label, "severity": "error", "message": f"counterfactual group must contain 2 cases, got {len(pair)}"})
            continue
        pair = sorted(pair, key=lambda c: c["case_id"])
        a, b = pair
        pa = normalized(a.get("baby_profile_structured") or {})
        pb = normalized(b.get("baby_profile_structured") or {})
        differing = {key for key in set(pa) | set(pb) if pa.get(key) != pb.get(key)}
        if differing != {"known_allergens"}:
            errors.append({"case_id": label, "severity": "error", "message": f"counterfactual profile differs outside target field: {sorted(differing)}"})
        if pa.get("known_allergens") != [] or pb.get("known_allergens") != ["milk"]:
            errors.append({"case_id": label, "severity": "error", "message": "counterfactual allergy values must be A=[] and B=['milk']"})
        neutral_contract = {
            "avoid_categories": [],
            "feedback_food_name": None,
            "feedback_reaction": None,
            "feedback_date": None,
            "suspected_allergy_history": False,
            "eczema_history": False,
            "parent_goal_seed": "营养均衡",
            "notes_zh": "",
            "notes_en": "",
        }
        for field, expected in neutral_contract.items():
            if pa.get(field) != expected or pb.get(field) != expected:
                errors.append({"case_id": label, "severity": "error", "message": f"counterfactual non-neutral field {field}"})
        foods_a = [f.get("food_id") for f in a.get("candidate_foods", [])]
        foods_b = [f.get("food_id") for f in b.get("candidate_foods", [])]
        if foods_a != foods_b:
            errors.append({"case_id": label, "severity": "error", "message": "counterfactual candidates differ"})
        if a.get("expected_decision") != "caution" or b.get("expected_decision") != "avoid":
            errors.append({"case_id": label, "severity": "error", "message": "counterfactual expected decisions must be A=caution and B=avoid"})
        if "R_ALLERGY_MILK" not in set(b.get("triggered_rule_ids") or []):
            errors.append({"case_id": label, "severity": "error", "message": "counterfactual B missing R_ALLERGY_MILK"})
    return errors


def load_jsonl(path: Path) -> tuple[list[dict], list[dict]]:
    rows, errors = [], []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                errors.append({"case_id": "", "severity": "error", "message": f"line {i} invalid json: {exc}"})
    return rows, errors


def validate_case(c: dict, valid_rules: set[str]) -> list[dict]:
    cid = c.get("case_id", "")
    errors = []
    for field in REQUIRED:
        if field not in c:
            errors.append({"case_id": cid, "severity": "error", "message": f"missing field {field}"})
    if c.get("expected_decision") not in ALLOWED:
        errors.append({"case_id": cid, "severity": "error", "message": "invalid expected_decision"})
    if c.get("task_type") == "candidate_selection":
        sets = [set(c.get("expected_safe_food_ids", [])), set(c.get("expected_caution_food_ids", [])), set(c.get("expected_avoid_food_ids", []))]
        if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
            errors.append({"case_id": cid, "severity": "error", "message": "safe/caution/avoid overlap"})
    known = set((c.get("baby_profile_structured") or {}).get("known_allergens") or [])
    age = (c.get("baby_profile_structured") or {}).get("corrected_age_month")
    foods = c.get("candidate_foods") or []
    triggered = set(c.get("triggered_rule_ids") or [])
    for food in foods:
        ingredient = food.get("ingredient_text")
        if ingredient is None or pd.isna(ingredient) or not str(ingredient).strip():
            if food.get("food_id") in set(c.get("expected_safe_food_ids") or []) or c.get("expected_decision") == "safe":
                errors.append({"case_id": cid, "severity": "error", "message": "missing ingredient_text cannot be labeled safe"})
        for a in ALLERGENS:
            if a in known and food.get(f"contains_{a}"):
                expected = f"R_ALLERGY_{a.upper()}" if a in ["milk", "egg", "wheat", "soy", "peanut"] else "R_ALLERGY_MILK"
                if expected not in triggered:
                    errors.append({"case_id": cid, "severity": "error", "message": f"missing allergy rule {expected}"})
        min_age = food.get("typical_age_min_month")
        if age is not None and min_age is not None and not pd.isna(min_age) and float(age) < float(min_age):
            fid = food.get("food_id")
            if fid in set(c.get("expected_safe_food_ids") or []) | set(c.get("expected_caution_food_ids") or []):
                errors.append({"case_id": cid, "severity": "error", "message": f"{fid} below recommended food age must be avoid"})
    if age is not None and age < 6 and c.get("expected_safe_food_ids"):
        errors.append({"case_id": cid, "severity": "error", "message": "corrected_age_month < 6 has expected safe foods"})
    if c.get("expected_decision") == "insufficient_information":
        follow = (c.get("expected_output") or {}).get("required_follow_up_questions", [])
        if not follow:
            errors.append({"case_id": cid, "severity": "warning", "message": "insufficient_information without follow-up questions"})
    for rid in list(c.get("triggered_rule_ids") or []) + list(c.get("positive_factor_rule_ids") or []):
        if rid not in valid_rules:
            errors.append({"case_id": cid, "severity": "error", "message": f"unknown rule_id {rid}"})
    if c.get("task_type") == "counterfactual_consistency":
        if not (c.get("synthetic_generation_trace") or {}).get("changed_variable"):
            errors.append({"case_id": cid, "severity": "error", "message": "counterfactual missing changed_variable"})
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/evaluation/evaluation_cases.jsonl")
    parser.add_argument("--out", default="outputs/evaluation")
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    cases, errors = load_jsonl(Path(args.input))
    rules = load_rules(REPO_ROOT / "outputs/normalized/rules.yaml")
    valid_rules = set(rules.keys())
    for c in cases:
        errors.extend(validate_case(c, valid_rules))
    errors.extend(validate_counterfactual_pairs(cases))
    err_df = pd.DataFrame(errors, columns=["case_id", "severity", "message"])
    err_df.to_csv(out / "validation_errors.csv", index=False, encoding="utf-8-sig")
    status = "PASS" if err_df[err_df["severity"].eq("error")].empty else "FAIL"
    lines = [
        "# Validation Report",
        "",
        f"Status: {status}",
        f"Cases checked: {len(cases)}",
        f"Errors: {int((err_df['severity'] == 'error').sum()) if not err_df.empty else 0}",
        f"Warnings: {int((err_df['severity'] == 'warning').sum()) if not err_df.empty else 0}",
    ]
    (out / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"validation_status={status} cases={len(cases)} findings={len(err_df)}")


if __name__ == "__main__":
    main()
