from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from babybites_common import ALLERGENS, age_bucket


def load_cases(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def add(failures: list[dict], case_id: str, check: str, severity: str, message: str) -> None:
    failures.append({"case_id": case_id, "check": check, "severity": severity, "message": message})


def check_case(c: dict) -> list[dict]:
    failures: list[dict] = []
    cid = c.get("case_id", "")
    p = c.get("baby_profile_structured") or {}
    foods = c.get("candidate_foods") or []
    safe = set(c.get("expected_safe_food_ids") or [])
    avoid = set(c.get("expected_avoid_food_ids") or [])
    caution = set(c.get("expected_caution_food_ids") or [])
    triggered = set(c.get("triggered_rule_ids") or [])
    age = p.get("age_month")
    corrected = p.get("corrected_age_month")
    gest = p.get("gestational_age_week")
    is_preterm = p.get("is_preterm")
    known = set(p.get("known_allergens") or [])

    if age is not None and not (0 <= float(age) <= 120):
        add(failures, cid, "age_range", "error", f"age_month out of range: {age}")
    if corrected is not None and not (0 <= float(corrected) <= 120):
        add(failures, cid, "corrected_age_range", "error", f"corrected_age_month out of range: {corrected}")
    if age is not None and corrected is not None and float(corrected) - float(age) > 0.01:
        add(failures, cid, "corrected_age_consistency", "error", "corrected_age_month exceeds actual age_month")
    if gest is not None:
        if is_preterm and float(gest) >= 37:
            add(failures, cid, "gestational_age_preterm", "error", "is_preterm true but gestational_age_week >= 37")
        if is_preterm is False and float(gest) < 37:
            add(failures, cid, "gestational_age_term", "error", "is_preterm false but gestational_age_week < 37")
    if corrected is not None and float(corrected) < 6:
        if safe:
            add(failures, cid, "under_6_no_safe_food", "error", "corrected_age_month < 6 but expected_safe_food_ids is non-empty")
        if "R_AGE_BELOW_6M_NO_COMPLEMENTARY_FOOD" not in triggered and foods:
            add(failures, cid, "under_6_rule_trace", "error", "under 6m case with foods missing age rule")

    if p.get("feeding_mode") == "母乳" and p.get("formula_status") == "current":
        add(failures, cid, "feeding_mode_status", "warning", "feeding_mode is 母乳 but formula_status is current")
    if p.get("feeding_mode") == "配方奶" and p.get("breastfeeding_status") == "current":
        add(failures, cid, "feeding_mode_status", "warning", "feeding_mode is 配方奶 but breastfeeding_status is current")

    food_by_id = {f.get("food_id"): f for f in foods}
    for fid, f in food_by_id.items():
        amin, amax = f.get("typical_age_min_month"), f.get("typical_age_max_month")
        if amin is not None and amax is not None and not pd.isna(amin) and not pd.isna(amax) and float(amin) > float(amax):
            add(failures, cid, "food_age_range", "error", f"{fid} typical min age exceeds max age")
        for allergen in ALLERGENS:
            if allergen in known and f.get(f"contains_{allergen}"):
                if fid in safe:
                    add(failures, cid, "allergen_safe_conflict", "error", f"{fid} is safe despite {allergen} allergy conflict")
                if fid not in avoid and c.get("task_type") in {"candidate_selection", "meal_plan_generation"}:
                    add(failures, cid, "allergen_classification", "error", f"{fid} allergy conflict not in avoid list")
        if f.get("contains_added_sugar") and fid in safe:
            add(failures, cid, "added_sugar_safe_conflict", "warning", f"{fid} contains added sugar but is safe")
        if f.get("contains_added_salt") and fid in safe:
            add(failures, cid, "added_salt_safe_conflict", "warning", f"{fid} contains added salt but is safe")
        if f.get("is_choking_risk_candidate") and fid in safe:
            add(failures, cid, "choking_safe_conflict", "error", f"{fid} choking risk candidate but is safe")
        if corrected is not None and amin is not None and not pd.isna(amin) and float(corrected) < float(amin):
            if fid in safe or fid in caution:
                add(failures, cid, "below_food_min_not_avoid", "error", f"{fid} is below recommended food age but not avoid")
        ingredient = f.get("ingredient_text")
        if (ingredient is None or pd.isna(ingredient) or not str(ingredient).strip()) and fid in safe:
            add(failures, cid, "missing_ingredient_safe_conflict", "error", f"{fid} missing ingredient_text but is safe")

    if safe & caution or safe & avoid or caution & avoid:
        add(failures, cid, "decision_set_overlap", "error", "safe/caution/avoid sets overlap")
    return failures


def normalized(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def check_counterfactual_pairs(cases: list[dict]) -> list[dict]:
    failures = []
    groups = defaultdict(list)
    for case in cases:
        if case.get("task_type") == "counterfactual_consistency":
            gid = (case.get("synthetic_generation_trace") or {}).get("counterfactual_group_id")
            groups[gid].append(case)
    for gid, pair in groups.items():
        if len(pair) != 2:
            add(failures, gid or "", "counterfactual_pair_size", "error", f"expected 2 cases, got {len(pair)}")
            continue
        a, b = sorted(pair, key=lambda c: c["case_id"])
        pa = normalized(a.get("baby_profile_structured") or {})
        pb = normalized(b.get("baby_profile_structured") or {})
        differing = {key for key in set(pa) | set(pb) if pa.get(key) != pb.get(key)}
        if differing != {"known_allergens"}:
            add(failures, gid or "", "counterfactual_single_variable", "error", f"profile differences: {sorted(differing)}")
        if a.get("expected_decision") != "caution" or b.get("expected_decision") != "avoid":
            add(failures, gid or "", "counterfactual_expected_flip", "error", "expected A=caution and B=avoid")
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
                add(failures, gid or "", "counterfactual_neutral_context", "error", f"non-neutral field: {field}")
    return failures


def write_report(cases: list[dict], failures: list[dict], out: Path) -> None:
    severities = Counter(f["severity"] for f in failures)
    checks = Counter(f["check"] for f in failures)
    age_counts = Counter(age_bucket((c.get("baby_profile_structured") or {}).get("corrected_age_month")) for c in cases)
    task_counts = Counter(c.get("task_type") for c in cases)
    lines = [
        "# Sanity Check Report",
        "",
        f"Cases checked: {len(cases)}",
        f"Errors: {severities.get('error', 0)}",
        f"Warnings: {severities.get('warning', 0)}",
        "",
        "## Task Counts",
        json.dumps(dict(task_counts), ensure_ascii=False, indent=2),
        "",
        "## Corrected Age Buckets",
        json.dumps(dict(age_counts), ensure_ascii=False, indent=2),
        "",
        "## Finding Counts",
        json.dumps(dict(checks), ensure_ascii=False, indent=2),
        "",
        "## Interpretation",
        "error 表示字段之间存在直接矛盾或规则 trace 缺失；warning 表示可能不理想但不一定违反硬规则，例如喂养方式状态表达不够一致。",
    ]
    (out / "sanity_check_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/evaluation/evaluation_cases.jsonl")
    parser.add_argument("--out", default="outputs/evaluation")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = load_cases(Path(args.input))
    failures: list[dict] = []
    for c in cases:
        failures.extend(check_case(c))
    failures.extend(check_counterfactual_pairs(cases))
    df = pd.DataFrame(failures, columns=["case_id", "check", "severity", "message"])
    df.to_csv(out / "sanity_check_findings.csv", index=False, encoding="utf-8-sig")
    write_report(cases, failures, out)
    err_count = int((df["severity"] == "error").sum()) if not df.empty else 0
    warn_count = int((df["severity"] == "warning").sum()) if not df.empty else 0
    print(f"sanity_errors={err_count} sanity_warnings={warn_count}")


if __name__ == "__main__":
    main()
