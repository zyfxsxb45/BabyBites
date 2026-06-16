from __future__ import annotations

import argparse
import json
from pathlib import Path


WEEKLY_REQUEST_ZH = (
    "请根据完整宝宝画像和全部候选食物生成七天辅食计划，每天安排1-2种食物；"
    "只从候选食物中选择，并说明应避免或需要谨慎处理的食物及原因；"
    "优先只使用普通可用食物，仅当普通可用食物只有0或1种时，才可纳入风险可通过加工或观察管理的"
    "谨慎食物，且必须写明对应安全加工方法或观察警告。"
)
WEEKLY_REQUEST_EN = (
    "Create a seven-day complementary feeding plan from the complete baby profile "
    "and all candidate foods. Schedule 1-2 foods per day, use only candidate foods, "
    "and explain which foods should be avoided or handled with caution and why. Prefer "
    "ordinary suitable foods. Only when zero or one suitable food remains may a manageable "
    "caution food be scheduled, and its preparation or observation warning must be stated."
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="outputs/evaluation/evaluation_cases_meal_plan_all_remaining68_v20260609.jsonl",
    )
    parser.add_argument(
        "--output",
        default="outputs/evaluation/evaluation_cases_meal_plan_remaining68_unified_weekly_v20260609.jsonl",
    )
    parser.add_argument(
        "--manifest",
        default="outputs/evaluation/evaluation_cases_meal_plan_remaining68_unified_weekly_v20260609_manifest.json",
    )
    args = parser.parse_args()

    rows = load_jsonl(Path(args.input))
    changed = []
    for row in rows:
        if row.get("task_type") != "meal_plan_generation":
            continue
        updated = dict(row)
        profile = dict(updated.get("baby_profile_structured") or {})
        profile["evaluation_request"] = WEEKLY_REQUEST_ZH
        updated["baby_profile_structured"] = profile
        updated["user_input"] = WEEKLY_REQUEST_ZH
        updated["user_input_zh"] = WEEKLY_REQUEST_ZH
        updated["user_input_en"] = WEEKLY_REQUEST_EN
        updated["evaluation_protocol"] = {
            "name": "unified_weekly_plan_caution_fallback_v2",
            "shared_request_zh": WEEKLY_REQUEST_ZH,
            "shared_request_en": WEEKLY_REQUEST_EN,
            "days_required": 7,
            "candidate_only": True,
            "minimum_suitable_without_caution": 2,
            "caution_requires_guidance": True,
        }
        changed.append(updated)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in changed),
        encoding="utf-8",
    )
    manifest = {
        "source": args.input,
        "output": args.output,
        "cases": len(changed),
        "case_ids": [row["case_id"] for row in changed],
        "shared_request_zh": WEEKLY_REQUEST_ZH,
        "shared_request_en": WEEKLY_REQUEST_EN,
        "changes": [
            "Replaced user_input, user_input_zh, and user_input_en with a seven-day request.",
            "Added baby_profile_structured.evaluation_request so BabyBites receives the same task request.",
            "Added evaluation_protocol metadata for auditability.",
        ],
    }
    Path(args.manifest).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
