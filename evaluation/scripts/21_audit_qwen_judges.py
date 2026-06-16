from __future__ import annotations

import os
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
OUT = ROOT / "outputs" / "judge_audit_qwen_plus_vs_qwen37"

BATCHES = {
    "qwen-plus/base20": ROOT / "outputs" / "formal_evaluation_current_unseen_stratified100",
    "qwen-plus/extension50": ROOT / "outputs" / "formal_evaluation_targeted_unseen_extension70",
    "qwen3.7-plus/new-protocol68": ROOT / "outputs" / "formal_evaluation_meal_plan_caution_fallback_v2_68",
}


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def text_of(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    audit_rows = []

    for batch, root in BATCHES.items():
        formal = {
            row["case_id"]: row
            for row in load_jsonl(root / "formal_results.jsonl")
            if row["task_type"] == "meal_plan_generation"
        }
        judge_path = root / "third_party_judge" / "judge_results.jsonl"
        judges = [
            row for row in load_jsonl(judge_path)
            if row["task_type"] == "meal_plan_generation"
        ]
        for judge in judges:
            result = formal[judge["case_id"]]
            mapping = judge.get("blind_mapping", {})
            winner_label = next((label for label, system in mapping.items() if system == judge["winner"]), "tie")
            winner_overall = judge["scores"].get(judge["winner"], {}).get("overall") if judge["winner"] != "tie" else None
            loser = "baseline" if judge["winner"] == "babybites" else "babybites"
            loser_overall = judge["scores"].get(loser, {}).get("overall") if judge["winner"] != "tie" else None
            winner_score_contradiction = (
                judge["winner"] != "tie"
                and isinstance(winner_overall, (int, float))
                and isinstance(loser_overall, (int, float))
                and winner_overall < loser_overall
            )
            tie_score_contradiction = (
                judge["winner"] == "tie"
                and judge["scores"]["babybites"].get("overall") != judge["scores"]["baseline"].get("overall")
            )
            for system in ("babybites", "baseline"):
                prediction = result[f"{system}_prediction"]
                metrics = result[f"{system}_metrics"]
                safety_errors = judge["safety_errors"].get(system, [])
                judge_text = "；".join(map(str, safety_errors)) + "；" + text_of(judge.get("winner_reason", ""))
                output_text = text_of(result[f"{system}_output"])
                deterministic_unsafe = float(metrics.get("unsafe_plan_items") or 0) > 0
                deterministic_hard = any(
                    float(metrics.get(key) or 0) > 0
                    for key in (
                        "added_sugar_plan_items",
                        "unknown_ingredient_plan_items",
                        "adverse_feedback_plan_items",
                    )
                )
                grape_claim = "葡萄" in judge_text and bool(safety_errors)
                output_has_grape_warning = (
                    "葡萄" in output_text
                    and any(token in output_text for token in ("切成", "切小", "切碎", "不可整颗", "避免直接给整颗"))
                )
                caution_policy_claim = bool(
                    re.search(r"(普通可用食物|普通食物).{0,20}(充足|2种|>=2|有2种)", judge_text)
                    or "违反caution食物纳入条件" in judge_text
                    or "违规纳入了caution食物" in judge_text
                    or "违规纳入 caution 食物" in judge_text
                )
                audit_rows.append({
                    "batch": batch,
                    "judge_model": judge["judge_model"],
                    "case_id": judge["case_id"],
                    "system": system,
                    "blind_label": next((label for label, value in mapping.items() if value == system), ""),
                    "winner": judge["winner"],
                    "winner_blind_label": winner_label,
                    "overall": judge["scores"][system].get("overall"),
                    "hard_risk_safety": judge["scores"][system].get("hard_risk_safety"),
                    "judge_safety_error": bool(safety_errors),
                    "deterministic_unsafe_plan_item": deterministic_unsafe,
                    "deterministic_hard_risk_item": deterministic_hard,
                    "grape_safety_claim_with_processing_warning": grape_claim and output_has_grape_warning,
                    "caution_policy_claim": caution_policy_claim,
                    "winner_score_contradiction": winner_score_contradiction,
                    "tie_score_contradiction": tie_score_contradiction,
                    "safety_errors": "；".join(map(str, safety_errors)),
                    "winner_reason": judge.get("winner_reason", ""),
                })

    df = pd.DataFrame(audit_rows)
    df.to_csv(OUT / "judge_audit_per_system.csv", index=False, encoding="utf-8-sig")

    summaries = []
    for batch, sub in df.groupby("batch"):
        case_sub = sub.drop_duplicates("case_id")
        model = sub["judge_model"].iloc[0]
        errors = sub[sub["judge_safety_error"]]
        summaries.append({
            "batch": batch,
            "judge_model": model,
            "cases": case_sub["case_id"].nunique(),
            "system_outputs": len(sub),
            "judge_safety_error_outputs": int(sub["judge_safety_error"].sum()),
            "deterministic_unsafe_outputs": int(sub["deterministic_unsafe_plan_item"].sum()),
            "judge_errors_with_deterministic_unsafe": int(
                (sub["judge_safety_error"] & sub["deterministic_unsafe_plan_item"]).sum()
            ),
            "judge_errors_without_deterministic_unsafe": int(
                (sub["judge_safety_error"] & ~sub["deterministic_unsafe_plan_item"]).sum()
            ),
            "grape_claim_despite_processing_warning": int(sub["grape_safety_claim_with_processing_warning"].sum()),
            "caution_policy_claims": int(sub["caution_policy_claim"].sum()),
            "winner_score_contradiction_cases": int(case_sub["winner_score_contradiction"].sum()),
            "tie_score_contradiction_cases": int(case_sub["tie_score_contradiction"].sum()),
            "winner_A": int((case_sub["winner_blind_label"] == "A").sum()),
            "winner_B": int((case_sub["winner_blind_label"] == "B").sum()),
            "winner_tie": int((case_sub["winner_blind_label"] == "tie").sum()),
        })
    summary = pd.DataFrame(summaries)
    summary.to_csv(OUT / "judge_audit_summary.csv", index=False, encoding="utf-8-sig")

    qplus = df[df["judge_model"] == "qwen-plus"]
    q37 = df[df["judge_model"] == "qwen3.7-plus"]
    qplus_cases = qplus.drop_duplicates("case_id")
    q37_cases = q37.drop_duplicates("case_id")
    report = [
        "# qwen-plus 与 qwen3.7-plus Judge 合理性审计",
        "",
        "## 可比性限制",
        "",
        "- 两种 Judge 没有对同一批完整双方输出进行重复评分，因此不能直接用 BB 胜率判断哪个 Judge 更合理。",
        "- qwen-plus 使用的是此前协议；qwen3.7-plus 的 68 例使用新增 caution fallback 协议。模型、输出版本和协议同时变化。",
        "",
        "## 审计结论",
        "",
        f"- qwen-plus：{qplus_cases.case_id.nunique()} 个周计划样本，标记安全错误输出 {int(qplus.judge_safety_error.sum())} 个。",
        f"- qwen3.7-plus：{q37_cases.case_id.nunique()} 个周计划样本，标记安全错误输出 {int(q37.judge_safety_error.sum())} 个。",
        f"- qwen3.7-plus 有 {int(q37.grape_safety_claim_with_processing_warning.sum())} 个案例在输出已提供葡萄加工警告时仍将其判为安全错误，和当前 caution fallback 协议存在冲突。",
        f"- qwen3.7-plus 有 {int(q37.caution_policy_claim.sum())} 个系统输出被判词按“普通 suitable 食物充足时违规纳入 caution”评价，说明它主动重做了候选分类；如果其分类与 BB 规则引擎不同，会产生政策口径冲突。",
        f"- 胜者与 Overall 分数相反的内部矛盾：qwen-plus {int(qplus_cases.winner_score_contradiction.sum())} 例，qwen3.7-plus {int(q37_cases.winner_score_contradiction.sum())} 例。",
        "",
        "## 判断",
        "",
        "- 就本项目当前协议而言，qwen3.7-plus 的判词更严格、更主动推理，但它没有稳定遵守“可加工管理的 caution 可纳入”这一新规则，因此作为最终裁判不够可靠。",
        "- qwen-plus 的判词通常更保守地围绕输出质量评分，较少自行重定义候选标签；但因没有在同一输出上复评，不能证明它总体能力更强。",
        "- 更合理的做法不是直接换回某个 Judge，而是把确定性候选标签、可管理 caution 清单和加工要求显式提供给 Judge，禁止 Judge 自行重分类；然后让两种模型在同一输出上复评并计算一致率。",
    ]
    (OUT / "JUDGE_AUDIT_REPORT_ZH.md").write_text("\n".join(report), encoding="utf-8")
    print(summary.to_string(index=False))
    print(f"wrote={OUT}")


if __name__ == "__main__":
    main()
