from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from babybites_common import ALLERGENS


def load_cases(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalized_decision(value: str) -> str:
    if value in {"safe", "recommend"}:
        return "safe"
    if value in {"caution", "insufficient_information"}:
        return "caution"
    if value in {"avoid", "not_ready_for_complementary_food"}:
        return "avoid"
    return str(value)


def candidate_decision(case: dict, food_id: str) -> str:
    if food_id in set(case.get("expected_safe_food_ids") or []):
        return "safe"
    if food_id in set(case.get("expected_avoid_food_ids") or []):
        return "avoid"
    if food_id in set(case.get("expected_caution_food_ids") or []):
        return "caution"
    if len(case.get("candidate_foods") or []) == 1:
        return normalized_decision(case.get("expected_decision"))
    return "unlabeled"


def review_reasons(case: dict, food: dict, expected: str) -> tuple[list[str], list[str]]:
    profile = case.get("baby_profile_structured") or {}
    corrected_age = profile.get("corrected_age_month")
    if corrected_age is None:
        corrected_age = profile.get("age_month")
    known = set(profile.get("known_allergens") or [])
    risk_reasons: list[str] = []
    conflicts: list[str] = []

    allergy_hits = [a for a in ALLERGENS if a in known and bool(food.get(f"contains_{a}"))]
    if allergy_hits:
        risk_reasons.append("known_allergy_conflict:" + ",".join(allergy_hits))
        if expected not in {"avoid", "unlabeled"}:
            conflicts.append("known allergy conflict is not avoid")
    if corrected_age is not None and float(corrected_age) < 6:
        risk_reasons.append("corrected_age_under_6")
        if expected not in {"avoid", "unlabeled"}:
            conflicts.append("under-6 complementary food is not blocked")
    min_age = food.get("typical_age_min_month")
    if corrected_age is not None and min_age is not None and not pd.isna(min_age) and float(corrected_age) < float(min_age):
        risk_reasons.append("below_food_min")
        if expected not in {"avoid", "unlabeled"}:
            conflicts.append("below recommended food age is not avoid")
    if bool(food.get("is_choking_risk_candidate")):
        risk_reasons.append("choking_requires_preparation")
        if expected == "safe":
            conflicts.append("choking risk is safe without preparation caution")
    if bool(food.get("is_strictly_forbidden")) or bool(food.get("contains_forbidden_ingredient")):
        risk_reasons.append("explicit_forbidden_ingredient")
        if expected not in {"avoid", "unlabeled"}:
            conflicts.append("forbidden ingredient is not avoid")
    ingredient = food.get("ingredient_text")
    if ingredient is None or pd.isna(ingredient) or not bool(str(ingredient).strip()):
        risk_reasons.append("unknown_ingredient")
        if expected == "safe":
            conflicts.append("unknown ingredient is safe")
    return risk_reasons, conflicts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/evaluation/evaluation_cases.jsonl")
    parser.add_argument("--out", default="outputs/evaluation/manual_review")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for case in load_cases(Path(args.input)):
        for food in case.get("candidate_foods") or []:
            expected = candidate_decision(case, food.get("food_id"))
            risks, conflicts = review_reasons(case, food, expected)
            if not risks and not conflicts:
                continue
            rows.append({
                "case_id": case.get("case_id"),
                "task_type": case.get("task_type"),
                "food_id": food.get("food_id"),
                "food_name_zh": food.get("food_name_zh"),
                "food_name_en": food.get("food_name"),
                "expected_decision": expected,
                "high_risk": any(
                    reason.startswith(("known_allergy_conflict", "corrected_age_under_6", "explicit_forbidden_ingredient", "below_food_min"))
                    for reason in risks
                ),
                "label_conflict": bool(conflicts),
                "review_reasons": " | ".join(risks),
                "conflict_reasons": " | ".join(conflicts),
                "review_status": "",
                "reviewer_decision": "",
                "reviewer_notes": "",
                "profile_json": json.dumps(case.get("baby_profile_structured") or {}, ensure_ascii=False),
                "food_json": json.dumps(food, ensure_ascii=False),
            })

    frame = pd.DataFrame(rows)
    conflicts = frame[frame["label_conflict"]].copy() if not frame.empty else frame.copy()
    frame.to_csv(out / "high_risk_and_unknown_samples.csv", index=False, encoding="utf-8-sig")
    conflicts.to_csv(out / "label_conflicts.csv", index=False, encoding="utf-8-sig")
    with (out / "high_risk_and_unknown_samples.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    reason_counts = Counter(reason for row in rows for reason in row["review_reasons"].split(" | ") if reason)
    report = [
        "# Manual Review Export",
        "",
        f"- Review rows: {len(frame)}",
        f"- Label conflicts: {len(conflicts)}",
        f"- High-risk rows: {int(frame['high_risk'].sum()) if not frame.empty else 0}",
        "",
        "## Reason Counts",
        "",
        *[f"- `{name}`: {count}" for name, count in sorted(reason_counts.items())],
        "",
        "人工复核时填写 `review_status`、`reviewer_decision` 和 `reviewer_notes`。"
    ]
    (out / "README.md").write_text("\n".join(report), encoding="utf-8")
    print(f"review_rows={len(frame)} conflicts={len(conflicts)} out={out}")


if __name__ == "__main__":
    main()
