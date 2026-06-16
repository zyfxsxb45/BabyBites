from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )


def anonymous_outputs(result: dict[str, Any], mapping: dict[str, str]) -> dict[str, str]:
    return {
        label: result[f"{system}_output"]
        for label, system in mapping.items()
    }


def readable_json(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--original-judge", required=True)
    parser.add_argument("--reverse-judge", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = {row["case_id"]: row for row in load_jsonl(Path(args.cases))}
    results = {row["case_id"]: row for row in load_jsonl(Path(args.results))}
    original = {row["case_id"]: row for row in load_jsonl(Path(args.original_judge))}
    reverse = {row["case_id"]: row for row in load_jsonl(Path(args.reverse_judge))}

    common_ids = sorted(original.keys() & reverse.keys() & results.keys() & cases.keys())
    integrated = []
    inconsistent_ids = []
    for case_id in common_ids:
        first = original[case_id]
        second = reverse[case_id]
        first_winner = first["winner"]
        second_winner = second["winner"]
        consistent = first_winner == second_winner
        final_winner = first_winner if consistent else "tie"
        if not consistent:
            inconsistent_ids.append(case_id)
        integrated.append({
            "case_id": case_id,
            "task_type": first["task_type"],
            "original_winner": first_winner,
            "reverse_winner": second_winner,
            "mapping_consistent": consistent,
            "final_winner": final_winner,
            "original_blind_mapping": first["blind_mapping"],
            "reverse_blind_mapping": second["blind_mapping"],
            "original_scores": first["scores"],
            "reverse_scores": second["scores"],
            "original_safety_errors": first["safety_errors"],
            "reverse_safety_errors": second["safety_errors"],
            "original_winner_reason": first.get("winner_reason", ""),
            "reverse_winner_reason": second.get("winner_reason", ""),
        })

    dump_jsonl(out / "bidirectional_integrated_results.jsonl", integrated)
    pd.DataFrame(integrated).to_csv(
        out / "bidirectional_integrated_results.csv",
        index=False,
        encoding="utf-8-sig",
    )

    final_counts = Counter(row["final_winner"] for row in integrated)
    summary = {
        "cases": len(integrated),
        "consistent_cases": sum(row["mapping_consistent"] for row in integrated),
        "inconsistent_cases": len(inconsistent_ids),
        "consistency_rate": (
            sum(row["mapping_consistent"] for row in integrated) / len(integrated)
            if integrated else None
        ),
        "final_winners": dict(final_counts),
        "rule": "Keep winner only when original and reversed mappings select the same system; otherwise tie.",
    }
    (out / "bidirectional_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Keep the original A/B order for human review, but hide system identity and both judge decisions.
    review_rows = []
    for index, case_id in enumerate(inconsistent_ids, 1):
        case = cases[case_id]
        result = results[case_id]
        mapping = original[case_id]["blind_mapping"]
        outputs = anonymous_outputs(result, mapping)
        review_rows.append({
            "review_id": f"R{index:03d}",
            "case_id": case_id,
            "task_type": case["task_type"],
            "baby_profile": case.get("baby_profile_structured"),
            "user_request": (
                (case.get("evaluation_protocol") or {}).get("shared_request_zh")
                or case.get("user_input_zh")
                or case.get("user_input")
            ),
            "candidate_foods": case.get("candidate_foods"),
            "output_A": outputs["A"],
            "output_B": outputs["B"],
        })
    dump_jsonl(out / "human_blind_review_cases.jsonl", review_rows)

    with (out / "human_blind_review_sheet.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "review_id", "case_id", "human_winner", "safety_error_A",
                "safety_error_B", "reason",
            ],
        )
        writer.writeheader()
        for row in review_rows:
            writer.writerow({"review_id": row["review_id"], "case_id": row["case_id"]})

    markdown = [
        "# 双向盲评不一致样本：人工盲判材料",
        "",
        "说明：A/B 身份已隐藏，不展示两次 Judge 的结论。请在配套 CSV 中填写 `human_winner=A|B|tie`、安全错误和理由。",
        "",
    ]
    for row in review_rows:
        markdown.extend([
            f"## {row['review_id']}",
            "",
            f"- Case ID：`{row['case_id']}`",
            f"- 任务：`{row['task_type']}`",
            "",
            "### 宝宝画像",
            "",
            "```json",
            readable_json(row["baby_profile"]),
            "```",
            "",
            "### 用户请求",
            "",
            str(row["user_request"] or ""),
            "",
            "### 候选食物",
            "",
            "```json",
            readable_json(row["candidate_foods"]),
            "```",
            "",
            "### 输出 A",
            "",
            "```json",
            readable_json(row["output_A"]),
            "```",
            "",
            "### 输出 B",
            "",
            "```json",
            readable_json(row["output_B"]),
            "```",
            "",
            "---",
            "",
        ])
    (out / "HUMAN_BLIND_REVIEW_ZH.md").write_text("\n".join(markdown), encoding="utf-8")

    report = [
        "# 双向 Qwen 盲评整合报告",
        "",
        f"- 总样本数：{summary['cases']}",
        f"- 映射反转后结论一致：{summary['consistent_cases']}",
        f"- 映射反转后结论不一致并记为 tie：{summary['inconsistent_cases']}",
        f"- 一致率：{summary['consistency_rate']:.3f}" if summary["consistency_rate"] is not None else "- 一致率：N/A",
        f"- 最终胜负：{dict(final_counts)}",
        "",
        "不一致样本已清洗为 `HUMAN_BLIND_REVIEW_ZH.md`，其中不显示系统身份和两次 Judge 结论。",
    ]
    (out / "BIDIRECTIONAL_JUDGE_REPORT_ZH.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote={out}")


if __name__ == "__main__":
    main()
