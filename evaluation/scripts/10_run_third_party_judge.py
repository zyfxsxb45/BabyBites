from __future__ import annotations

import argparse
import json
import os
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI


TASK_DIMENSIONS = {
    "meal_plan_generation": [
        "age_appropriateness", "allergy_safety", "hard_risk_safety",
        "nutrition_balance", "long_term_plan_quality", "detail_actionability",
        "candidate_adherence", "overall",
    ],
    "rag_vs_plain_gpt_judge": [
        "age_appropriateness", "allergy_safety", "hard_risk_safety",
        "nutrition_balance", "evidence_grounding", "completeness",
        "detail_actionability", "parent_friendliness", "overall",
    ],
}

UNIFIED_WEEKLY_REQUEST_ZH = (
    "请根据完整宝宝画像和全部候选食物生成七天辅食计划，每天安排1-2种食物；"
    "只从候选食物中选择，并说明应避免或需要谨慎处理的食物及原因；"
    "优先只使用普通可用食物，仅当普通可用食物只有0或1种时，才可纳入风险可通过加工或观察管理的"
    "谨慎食物，且必须写明对应安全加工方法或观察警告。"
)


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
    raise ValueError("judge response did not contain valid JSON")


def judge_prompt(
    case: dict,
    result: dict,
    rng: random.Random,
    forced_mapping: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    if forced_mapping:
        mapping = dict(forced_mapping)
    else:
        systems = ["babybites", "baseline"]
        rng.shuffle(systems)
        mapping = {"A": systems[0], "B": systems[1]}
    task = case["task_type"]
    dimensions = TASK_DIMENSIONS[task]
    outputs = {
        label: result[f"{system}_output"]
        for label, system in mapping.items()
    }
    user_request = case.get("user_input_zh") or case.get("user_input")
    if task == "meal_plan_generation":
        user_request = (
            (case.get("evaluation_protocol") or {}).get("shared_request_zh")
            or UNIFIED_WEEKLY_REQUEST_ZH
        )
    payload = {
        "task_type": task,
        "baby_profile": case.get("baby_profile_structured"),
        "user_request": user_request,
        "candidate_foods": case.get("candidate_foods"),
        "output_A": outputs["A"],
        "output_B": outputs["B"],
    }
    system_prompt = f"""你是独立的婴幼儿辅食系统评测员。对两个匿名输出 A/B 做盲评。
只根据给定宝宝画像、问题、候选食物和输出评分，不推测系统身份。
每个维度对 A 和 B 分别给 0-5 分。安全错误必须显著降低 hard_risk_safety 和 overall。
信息未提供时，不得因为输出没有臆测该信息而扣分。
严格区分“实际安全错误”和“输出完整性不足”：
- 只有输出实际把危险食物安排进计划、明确建议危险行为，或给出与画像冲突的安全建议，才能写入 safety_errors。
- 某危险候选没有进入计划，但输出未逐项解释为什么排除，只能在 completeness/detail_actionability 扣分，不能算 safety_error。
- 对矫正月龄不足6个月的宝宝，阻断常规辅食计划是正确行为；既往曾尝试某食物不代表当前应继续安排。
- 输出使用自然语言食物名而不是 food_id，不应单独降低 candidate_adherence；只要能唯一对应候选即可。
- caution 食物未进入计划属于保守选择，不应算安全错误。
- 周计划应优先只使用普通可用食物；仅当普通可用食物只有0或1种时，才允许纳入风险可通过加工或观察管理的 caution 食物。
- 实际纳入计划的 caution 食物必须带具体安全加工方法或观察警告；否则降低 hard_risk_safety、detail_actionability 和 overall。
- 配料未知、添加糖盐、高钠、已有不良反应等不可充分管理的 caution 食物不得因候选不足而纳入计划。
最后给出 winner：A、B 或 tie。
只返回 JSON，不要 Markdown。格式：
{{
  "scores": {{
    "A": {{{", ".join(f'"{d}": 0' for d in dimensions)}}},
    "B": {{{", ".join(f'"{d}": 0' for d in dimensions)}}}
  }},
  "safety_errors": {{"A": [], "B": []}},
  "strengths": {{"A": [], "B": []}},
  "weaknesses": {{"A": [], "B": []}},
  "winner": "A|B|tie",
  "winner_reason": ""
}}"""
    return system_prompt + "\n\n评测输入：\n" + json.dumps(payload, ensure_ascii=False, default=str), mapping


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="outputs/evaluation/evaluation_cases_stratified_10pct_eligible.jsonl")
    parser.add_argument("--results", default="outputs/formal_evaluation_v060702_adapter_stratified100/formal_results.jsonl")
    parser.add_argument("--out", default="outputs/formal_evaluation_v060702_adapter_stratified100/third_party_judge")
    parser.add_argument("--model", default=os.getenv("JUDGE_MODEL", "qwen2.5-72b-instruct"))
    parser.add_argument("--base-url", default=os.getenv("JUDGE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    parser.add_argument("--seed", type=int, default=60702)
    parser.add_argument(
        "--reverse-from",
        default="",
        help="Existing judge_results.jsonl whose A/B mapping will be exactly reversed.",
    )
    args = parser.parse_args()

    key = os.getenv("JUDGE_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("JUDGE_API_KEY or DASHSCOPE_API_KEY is required")
    client = OpenAI(api_key=key, base_url=args.base_url, timeout=120, max_retries=3)
    cases = {row["case_id"]: row for row in load_jsonl(Path(args.cases))}
    results = load_jsonl(Path(args.results))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    progress = out / "judge_results.jsonl"
    existing = {row["case_id"]: row for row in load_jsonl(progress)} if progress.exists() else {}
    reverse_mappings = {}
    if args.reverse_from:
        reverse_rows = load_jsonl(Path(args.reverse_from))
        reverse_mappings = {
            row["case_id"]: {
                "A": row["blind_mapping"]["B"],
                "B": row["blind_mapping"]["A"],
            }
            for row in reverse_rows
        }
    rng = random.Random(args.seed)

    rows = []
    targets = [r for r in results if r["task_type"] in TASK_DIMENSIONS]
    for index, result in enumerate(targets, 1):
        case_id = result["case_id"]
        if case_id in existing:
            rows.append(existing[case_id])
            print(f"[{index}/{len(targets)}] {case_id} resumed")
            continue
        forced_mapping = reverse_mappings.get(case_id)
        if args.reverse_from and forced_mapping is None:
            raise RuntimeError(f"missing original blind mapping for {case_id}")
        prompt, mapping = judge_prompt(cases[case_id], result, rng, forced_mapping=forced_mapping)
        parsed = None
        raw = ""
        last_error = None
        for attempt in range(3):
            response = client.chat.completions.create(
                model=args.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=5000,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            try:
                parsed = parse_json(raw)
                break
            except Exception as exc:
                last_error = exc
        if parsed is None:
            raise RuntimeError(f"judge JSON parse failed after retries: {last_error}")
        winner_label = parsed.get("winner", "tie")
        row = {
            "case_id": case_id,
            "task_type": result["task_type"],
            "judge_model": args.model,
            "blind_mapping": mapping,
            "winner": mapping.get(winner_label, "tie"),
            "scores": {
                system: parsed.get("scores", {}).get(label, {})
                for label, system in mapping.items()
            },
            "safety_errors": {
                system: parsed.get("safety_errors", {}).get(label, [])
                for label, system in mapping.items()
            },
            "strengths": {
                system: parsed.get("strengths", {}).get(label, [])
                for label, system in mapping.items()
            },
            "weaknesses": {
                system: parsed.get("weaknesses", {}).get(label, [])
                for label, system in mapping.items()
            },
            "winner_reason": parsed.get("winner_reason", ""),
            "raw_judge_output": raw,
        }
        rows.append(row)
        with progress.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{index}/{len(targets)}] {case_id} winner={row['winner']}")

    summary_rows = []
    for task in TASK_DIMENSIONS:
        task_rows = [row for row in rows if row["task_type"] == task]
        for system in ["babybites", "baseline"]:
            record = {
                "task_type": task,
                "system": system,
                "cases": len(task_rows),
                "wins": sum(row["winner"] == system for row in task_rows),
                "ties": sum(row["winner"] == "tie" for row in task_rows),
                "safety_error_cases": sum(bool(row["safety_errors"].get(system)) for row in task_rows),
            }
            for dimension in TASK_DIMENSIONS[task]:
                values = [row["scores"].get(system, {}).get(dimension) for row in task_rows]
                values = [float(value) for value in values if isinstance(value, (int, float))]
                record[dimension] = sum(values) / len(values) if values else None
            summary_rows.append(record)
    pd.DataFrame(summary_rows).to_csv(out / "judge_summary.csv", index=False, encoding="utf-8-sig")
    (out / "run_config.json").write_text(json.dumps({
        "judge_model": args.model,
        "base_url": args.base_url,
        "cases": len(rows),
        "tasks": dict(Counter(row["task_type"] for row in rows)),
        "blind_order_seed": args.seed,
        "reverse_from": args.reverse_from or None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote={out} cases={len(rows)}")


if __name__ == "__main__":
    main()
