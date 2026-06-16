from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import pandas as pd

from babybites_common import (
    REPO_ROOT,
    agent_input_columns,
    age_bucket,
    ensure_dirs,
    evaluate_candidate,
    load_rules,
    make_profile_text,
    make_profile_text_en,
    make_profile_text_zh,
    read_yaml,
    save_table,
    structured_profile_columns,
    structured_profile_text_en,
    structured_profile_text_zh,
    write_jsonl,
)


REQUIRED_FIELDS = [
    "case_id", "task_type", "source_datasets", "baby_profile_structured", "baby_profile_text",
    "candidate_foods", "user_input", "expected_output", "expected_decision",
    "expected_safe_food_ids", "expected_avoid_food_ids", "expected_caution_food_ids",
    "triggered_rule_ids", "positive_factor_rule_ids", "risk_types", "difficulty_tags",
    "evaluation_rubric", "gold_rationale", "evidence_trace", "synthetic_generation_trace",
    "data_quality_flags",
]


def parse_list(value):
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    try:
        return json.loads(value.replace("'", '"')) if isinstance(value, str) and value.startswith("[") else []
    except Exception:
        return []


def prep_profiles(df: pd.DataFrame) -> list[dict]:
    rows = []
    for rec in df.to_dict("records"):
        rec["known_allergens"] = parse_list(rec.get("known_allergens"))
        rec["tried_foods"] = parse_list(rec.get("tried_foods"))
        rec["avoid_categories"] = parse_list(rec.get("avoid_categories"))
        rows.append(rec)
    return rows


def prep_foods(df: pd.DataFrame) -> list[dict]:
    return df.to_dict("records")


def neutral_counterfactual_profile(profile: dict) -> dict:
    """Remove non-target signals so only known_allergens changes in an A/B pair."""
    cleaned = dict(profile)
    cleaned["known_allergens"] = []
    cleaned["avoid_categories"] = []
    cleaned["feedback_food_name"] = None
    cleaned["feedback_reaction"] = None
    cleaned["feedback_date"] = None
    cleaned["suspected_allergy_history"] = False
    cleaned["eczema_history"] = False
    cleaned["parent_goal_seed"] = "营养均衡"
    cleaned["notes_zh"] = ""
    cleaned["notes_en"] = ""
    return cleaned


def difficulty(profile: dict, result: dict, food: dict | None = None) -> list[str]:
    tags = [f"age_{age_bucket(profile.get('corrected_age_month'))}"]
    if profile.get("is_preterm"):
        tags.append("preterm_corrected_age")
    tags.extend(result.get("risk_types", []))
    for a in profile.get("known_allergens") or []:
        tags.append(f"{a}_allergy")
    if food:
        ingredient = food.get("ingredient_text")
        if ingredient is None or pd.isna(ingredient) or not str(ingredient).strip():
            tags.append("insufficient_info")
    return sorted(set(tags))


def base_case(case_id: str, task: str, profile: dict, foods: list[dict], rng: random.Random) -> dict:
    profile_text_zh = make_profile_text_zh(profile, rng)
    profile_text_en = make_profile_text_en(profile, rng)
    structured_cols = structured_profile_columns(profile)
    agent_cols = agent_input_columns(profile, foods)
    return {
        "case_id": case_id,
        "task_type": task,
        "source_datasets": sorted(set([profile.get("source_dataset", "synthetic")] + [f.get("source_dataset", "synthetic") for f in foods])),
        "baby_profile_structured": profile,
        "baby_profile_text": profile_text_zh,
        "baby_profile_text_zh": profile_text_zh,
        "baby_profile_text_en": profile_text_en,
        "structured_input_zh": structured_profile_text_zh(profile),
        "structured_input_en": structured_profile_text_en(profile),
        **structured_cols,
        **agent_cols,
        "candidate_foods": foods,
        "user_input": "",
        "user_input_zh": "",
        "user_input_en": "",
        "expected_output": {},
        "expected_decision": "safe",
        "expected_safe_food_ids": [],
        "expected_avoid_food_ids": [],
        "expected_caution_food_ids": [],
        "triggered_rule_ids": [],
        "positive_factor_rule_ids": [],
        "risk_types": [],
        "difficulty_tags": [],
        "evaluation_rubric": {
            "age_appropriate": 2, "allergen_safe": 3, "nutrition_balance": 2,
            "texture_appropriate": 2, "explanation_quality": 1, "evidence_grounding": 1,
        },
        "gold_rationale": "",
        "evidence_trace": [],
        "synthetic_generation_trace": {"method": "template_and_rule_sampling", "not_real_person": True},
        "data_quality_flags": [],
    }


def select_mixed_foods(profile: dict, foods: list[dict], rng: random.Random, thresholds: dict) -> list[dict]:
    scored = [(f, evaluate_candidate(profile, f, thresholds)) for f in foods]
    avoid = [f for f, r in scored if r["decision"] in ["avoid", "not_ready_for_complementary_food"]]
    caution = [f for f, r in scored if r["decision"] in ["caution", "insufficient_information"]]
    safe = [f for f, r in scored if r["decision"] == "safe"]
    chosen = []
    chosen.extend(rng.sample(safe, min(2, len(safe))))
    chosen.extend(rng.sample(avoid, min(2, len(avoid))))
    chosen.extend(rng.sample(caution, min(3, len(caution))))
    while len(chosen) < 6:
        f = rng.choice(foods)
        if f not in chosen:
            chosen.append(f)
    return chosen[:8]


def generate_cases(n_total: int, seed: int, profiles: list[dict], foods: list[dict], thresholds: dict) -> list[dict]:
    rng = random.Random(seed)
    quotas = {
        "meal_plan_generation": int(n_total * 0.20),
        "candidate_selection": int(n_total * 0.25),
        "profile_extraction": int(n_total * 0.15),
        "safety_rule_trigger": int(n_total * 0.20),
        "counterfactual_consistency": int(n_total * 0.10),
        "rag_vs_plain_gpt_judge": n_total,
    }
    quotas["rag_vs_plain_gpt_judge"] -= sum(v for k, v in quotas.items() if k != "rag_vs_plain_gpt_judge")
    cases: list[dict] = []
    idx = 0
    for _ in range(quotas["candidate_selection"]):
        p = rng.choice(profiles)
        cand = select_mixed_foods(p, foods, rng, thresholds)
        case = base_case(f"EV{idx:05d}", "candidate_selection", p, cand, rng)
        case["user_input_zh"] = case["baby_profile_text_zh"] + " 下面这些辅食能选哪些？"
        case["user_input_en"] = case["baby_profile_text_en"] + " Which of the following complementary foods are suitable?"
        case["user_input"] = case["user_input_zh"]
        all_trig, all_pos, risks = [], [], []
        for f in cand:
            r = evaluate_candidate(p, f, thresholds)
            if r["decision"] == "safe":
                case["expected_safe_food_ids"].append(f["food_id"])
            elif r["decision"] in ["avoid", "not_ready_for_complementary_food"]:
                case["expected_avoid_food_ids"].append(f["food_id"])
            else:
                case["expected_caution_food_ids"].append(f["food_id"])
            all_trig.extend(r["triggered_rule_ids"])
            all_pos.extend(r["positive_factor_rule_ids"])
            risks.extend(r["risk_types"])
        case["expected_decision"] = "avoid" if case["expected_avoid_food_ids"] else ("caution" if case["expected_caution_food_ids"] else "safe")
        case["triggered_rule_ids"] = sorted(set(all_trig))
        case["positive_factor_rule_ids"] = sorted(set(all_pos))
        case["risk_types"] = sorted(set(risks))
        case["difficulty_tags"] = difficulty(p, {"risk_types": risks})
        case["gold_rationale"] = "按矫正月龄、已知过敏、添加糖盐/钠和质地风险对候选食物分为 safe/caution/avoid。"
        case["evidence_trace"] = [{"type": "rule", "rule_ids": case["triggered_rule_ids"]}]
        cases.append(case); idx += 1
    for _ in range(quotas["safety_rule_trigger"]):
        p, f = rng.choice(profiles), rng.choice(foods)
        r = evaluate_candidate(p, f, thresholds)
        case = base_case(f"EV{idx:05d}", "safety_rule_trigger", p, [f], rng)
        case["user_input_zh"] = f"{case['baby_profile_text_zh']} 这个{f.get('food_name_zh') or f.get('food_name')}能吃吗？"
        case["user_input_en"] = f"{case['baby_profile_text_en']} Can the baby eat {f.get('food_name')}?"
        case["user_input"] = case["user_input_zh"]
        case["expected_decision"] = r["decision"]
        case["triggered_rule_ids"] = r["triggered_rule_ids"]
        case["positive_factor_rule_ids"] = r["positive_factor_rule_ids"]
        case["risk_types"] = r["risk_types"]
        case["difficulty_tags"] = difficulty(p, r, f)
        case["expected_output"] = {"triggered_rule_ids": r["triggered_rule_ids"], "risk_types": r["risk_types"], "required_follow_up_questions": ["请提供完整配料表和钠/糖信息。"] if r["decision"] == "insufficient_information" else []}
        case["gold_rationale"] = "单品安全判断必须先应用硬规则，再给出谨慎或追问建议。"
        case["evidence_trace"] = [{"type": "food", "food_id": f["food_id"]}, {"type": "rule", "rule_ids": r["triggered_rule_ids"]}]
        cases.append(case); idx += 1
    for _ in range(quotas["meal_plan_generation"]):
        p = rng.choice(profiles)
        cand = select_mixed_foods(p, foods, rng, thresholds)
        case = base_case(f"EV{idx:05d}", "meal_plan_generation", p, cand, rng)
        case["user_input_zh"] = case["baby_profile_text_zh"] + " 请安排一天辅食计划，并说明哪些不要选。"
        case["user_input_en"] = case["baby_profile_text_en"] + " Please make a one-day complementary food plan and explain which foods should not be used."
        case["user_input"] = case["user_input_zh"]
        results = {f["food_id"]: evaluate_candidate(p, f, thresholds) for f in cand}
        avoid = [fid for fid, r in results.items() if r["decision"] in ["avoid", "not_ready_for_complementary_food"]]
        caution = [fid for fid, r in results.items() if r["decision"] in ["caution", "insufficient_information"]]
        safe = [fid for fid, r in results.items() if r["decision"] == "safe"]
        case["expected_safe_food_ids"], case["expected_avoid_food_ids"], case["expected_caution_food_ids"] = safe, avoid, caution
        trig = [rid for r in results.values() for rid in r["triggered_rule_ids"]]
        pos = [rid for r in results.values() for rid in r["positive_factor_rule_ids"]]
        case["triggered_rule_ids"], case["positive_factor_rule_ids"] = sorted(set(trig)), sorted(set(pos))
        case["expected_decision"] = "not_ready_for_complementary_food" if p.get("corrected_age_month", 99) < 6 else ("caution" if caution or avoid else "recommend")
        case["expected_output"] = {
            "must_avoid": avoid,
            "should_include_or_prioritize": [f["food_id"] for f in cand if f.get("is_iron_rich") and f["food_id"] in safe],
            "acceptable_food_categories": sorted(set(f.get("food_category") for f in cand if f["food_id"] in safe)),
            "forbidden_food_categories": sorted(set(f.get("food_category") for f in cand if f["food_id"] in avoid)),
            "required_warnings": case["triggered_rule_ids"],
            "required_follow_up_questions": ["缺少配料表时先追问。"] if any(r["decision"] == "insufficient_information" for r in results.values()) else [],
            "rubric_points": case["evaluation_rubric"],
        }
        case["risk_types"] = sorted(set(rt for r in results.values() for rt in r["risk_types"]))
        case["difficulty_tags"] = difficulty(p, {"risk_types": case["risk_types"]})
        case["gold_rationale"] = "计划生成不得越过年龄和过敏硬规则，同时优先富铁、已耐受且质地合适的食物。"
        cases.append(case); idx += 1
    for _ in range(quotas["profile_extraction"]):
        p = rng.choice(profiles)
        case = base_case(f"EV{idx:05d}", "profile_extraction", p, [], rng)
        case["user_input_zh"] = make_profile_text_zh(p, rng)
        case["user_input_en"] = make_profile_text_en(p, rng)
        case["user_input"] = case["user_input_zh"]
        case["expected_decision"] = "recommend"
        case["expected_output"] = {"structured_profile": {k: p.get(k) for k in ["is_preterm", "gestational_age_week", "age_month", "corrected_age_month", "known_allergens", "tried_foods", "parent_goal_seed"]}}
        case["difficulty_tags"] = difficulty(p, {"risk_types": []}) + ["colloquial_parent_query"]
        case["gold_rationale"] = "信息抽取应保留早产、矫正月龄、过敏/疑似过敏、已尝试食物和家长目标。"
        cases.append(case); idx += 1
    valid_pairs = []
    for source_profile in profiles:
        p0 = neutral_counterfactual_profile(source_profile)
        for food in foods:
            if not food.get("contains_milk"):
                continue
            p1 = dict(p0); p1["known_allergens"] = ["milk"]
            r0 = evaluate_candidate(p0, food, thresholds)
            r1 = evaluate_candidate(p1, food, thresholds)
            if r0["decision"] == "caution" and r1["decision"] == "avoid" and "R_ALLERGY_MILK" in r1["triggered_rule_ids"]:
                valid_pairs.append((p0, p1, food))
    if not valid_pairs:
        raise RuntimeError("No clean milk-allergy counterfactual pair can be generated")
    for _ in range(max(1, quotas["counterfactual_consistency"] // 2)):
        p0, p1, f = rng.choice(valid_pairs)
        pair_rng_state = rng.getstate()
        for variant, pp, changed in [("A", p0, "known_allergens=[]"), ("B", p1, "known_allergens=['milk']")]:
            # Keep wording/template randomness identical across A/B.
            rng.setstate(pair_rng_state)
            r = evaluate_candidate(pp, f, thresholds)
            case = base_case(f"EV{idx:05d}_{variant}", "counterfactual_consistency", pp, [f], rng)
            case["user_input_zh"] = make_profile_text_zh(pp, rng) + f" 候选是{f.get('food_name_zh')}。"
            case["user_input_en"] = make_profile_text_en(pp, rng) + f" The candidate food is {f.get('food_name')}."
            case["user_input"] = case["user_input_zh"]
            case["expected_decision"] = r["decision"]
            case["triggered_rule_ids"] = r["triggered_rule_ids"]
            case["positive_factor_rule_ids"] = r["positive_factor_rule_ids"]
            case["risk_types"] = r["risk_types"]
            case["difficulty_tags"] = difficulty(pp, r, f) + ["counterfactual_pair"]
            case["synthetic_generation_trace"]["counterfactual_group_id"] = f"CFG{idx:05d}"
            case["synthetic_generation_trace"]["changed_variable"] = changed
            case["synthetic_generation_trace"]["changed_field"] = "known_allergens"
            case["synthetic_generation_trace"]["counterfactual_contract"] = {
                "only_changed_field": "known_allergens",
                "expected_A": "caution",
                "expected_B": "avoid",
            }
            case["gold_rationale"] = "反事实组只改变牛奶过敏变量，含奶候选的预期决策应相应变为 avoid。"
            cases.append(case)
        idx += 1
    for _ in range(quotas["rag_vs_plain_gpt_judge"]):
        p = rng.choice(profiles); cand = select_mixed_foods(p, foods, rng, thresholds)
        case = base_case(f"EV{idx:05d}", "rag_vs_plain_gpt_judge", p, cand, rng)
        case["user_input_zh"] = case["baby_profile_text_zh"] + " 请根据完整宝宝画像和候选食物，给出个性化辅食选择建议、风险提醒和理由。"
        case["user_input_en"] = case["baby_profile_text_en"] + " Based on the complete baby profile and candidate foods, provide personalized food choices, risk warnings, and reasons."
        case["user_input"] = case["user_input_zh"]
        case["expected_decision"] = "recommend"
        results = [evaluate_candidate(p, f, thresholds) for f in cand]
        case["triggered_rule_ids"] = sorted(set(rid for r in results for rid in r["triggered_rule_ids"]))
        case["positive_factor_rule_ids"] = sorted(set(rid for r in results for rid in r["positive_factor_rule_ids"]))
        case["risk_types"] = sorted(set(rt for r in results for rt in r["risk_types"]))
        case["judge_prompt_template"] = (
            "你是第三方评估员。给定宝宝画像、候选食物、标准规则、RAG输出和Plain GPT输出，"
            "从月龄/矫正月龄、过敏安全、已尝试食物、营养搭配、添加糖盐高钠、信息不足追问、依据充分性、家长友好和不过度医疗化评分。"
        )
        case["expected_output"] = {"judge_dimensions": ["age", "allergy", "tried_foods", "nutrition", "sugar_salt_sodium", "follow_up", "evidence", "friendly", "not_overmedicalized"]}
        case["difficulty_tags"] = difficulty(p, {"risk_types": case["risk_types"]})
        case["gold_rationale"] = "judge prompt 只准备盲评输入，不调用 judge 模型。"
        cases.append(case); idx += 1
    return cases[:n_total]


def write_summary(cases: list[dict], out: Path) -> None:
    rows = []
    for c in cases:
        rows.append({
            "case_id": c["case_id"],
            "task_type": c["task_type"],
            "expected_decision": c["expected_decision"],
            "age_bucket": age_bucket(c["baby_profile_structured"].get("corrected_age_month")),
            "allergens": ",".join(c["baby_profile_structured"].get("known_allergens") or []),
            "hard_rule": any(r.startswith("R_ALLERGY") or r.startswith("R_AGE") for r in c["triggered_rule_ids"]),
            "caution": c["expected_decision"] == "caution",
            "insufficient_information": c["expected_decision"] == "insufficient_information",
        })
    df = pd.DataFrame(rows)
    save_table(df.groupby(["task_type"]).size().reset_index(name="n"), out / "evaluation_case_summary.csv")
    counts = {
        "total": len(cases),
        "task_counts": dict(Counter(r["task_type"] for r in rows)),
        "age_bucket_counts": dict(Counter(r["age_bucket"] for r in rows)),
        "hard_rule_cases": int(sum(r["hard_rule"] for r in rows)),
        "caution_cases": int(sum(r["caution"] for r in rows)),
        "insufficient_information_cases": int(sum(r["insufficient_information"] for r in rows)),
        "counterfactual_cases": int(sum(r["task_type"] == "counterfactual_consistency" for r in rows)),
    }
    text = [
        "# 评估数据卡",
        "",
        "## 数据来源概述",
        "使用本地 IFPS2、NHANES1999、WIC_ITFPS-2 文件探索结果作为字段和分布线索；评估画像与候选食物为规则化合成，不复制真实受试者。",
        "",
        f"生成评估样本 {counts['total']} 条。",
        "",
        "## 任务类型数量",
        json.dumps(counts["task_counts"], ensure_ascii=False, indent=2),
        "",
        "## 月龄段数量",
        json.dumps(counts["age_bucket_counts"], ensure_ascii=False, indent=2),
        "",
        f"hard-rule case 数量：{counts['hard_rule_cases']}；caution case 数量：{counts['caution_cases']}；insufficient information case 数量：{counts['insufficient_information_cases']}；反事实样本数量：{counts['counterfactual_cases']}。",
        "",
        "## 已知局限",
        "部分原始库为 PDF 或 SAS7BDAT，当前最小可运行版本未完整抽取所有 codebook；过敏史和部分营养成分由规则化合成补足；阈值需在 evaluation/configs/rule_thresholds.yaml 人工确认。",
        "",
        "## RAG vs Plain GPT 使用方式",
        "将同一 user_input、baby_profile_structured、candidate_foods 分别送入 RAG 系统和普通 GPT，再把两个输出填入 judge_prompt_template 进行盲评。",
        "",
        "本评估集仅用于系统评估，不应当作真实医学建议。",
    ]
    (out / "evaluation_data_card.md").write_text("\n".join(text), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-total", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="outputs/evaluation")
    args = parser.parse_args()
    ensure_dirs()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    profiles = prep_profiles(pd.read_csv(REPO_ROOT / "outputs/normalized/baby_profile_seeds.csv"))
    foods = prep_foods(pd.read_csv(REPO_ROOT / "outputs/normalized/food_candidate_pool.csv"))
    thresholds = read_yaml(REPO_ROOT / "evaluation" / "configs" / "rule_thresholds.yaml", {})
    cases = generate_cases(args.n_total, args.seed, profiles, foods, thresholds)
    write_jsonl(out / "evaluation_cases.jsonl", cases)
    df = pd.DataFrame(cases)
    df.to_csv(out / "evaluation_cases.csv", index=False, encoding="utf-8-sig")
    save_table(df, out / "evaluation_cases.csv", out / "evaluation_cases.parquet")
    judge = [{"case_id": c["case_id"], "judge_prompt_template": c.get("judge_prompt_template", "")} for c in cases if c["task_type"] == "rag_vs_plain_gpt_judge"]
    (out / "judge_prompt_templates.json").write_text(json.dumps(judge, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(cases, out)
    print(f"cases={len(cases)} task_counts={dict(Counter(c['task_type'] for c in cases))}")


if __name__ == "__main__":
    main()
