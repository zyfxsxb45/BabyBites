from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import accuracy_score, precision_recall_fscore_support


ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
APP_ROOT = Path(os.getenv("BABYBITES_APP_ROOT", str(ROOT / "app_repo" / "BabyBites-main"))).resolve()
sys.path.insert(0, str(APP_ROOT))

import agents.chat as chat_module  # noqa: E402
import eval_adapter as app_eval_adapter  # noqa: E402
from agents.chat import ChatAgent, SYSTEM_PROMPT as CHAT_SYSTEM_PROMPT  # noqa: E402
from agents.plan_generation import PlanGenerationAgent  # noqa: E402
from agents.safety_boundary import SafetyBoundaryAgent  # noqa: E402
from agents.user_profile import UserProfileAgent  # noqa: E402
from kb.json_backend import JSONKnowledgeBase  # noqa: E402
from rules.engine import RuleEngine  # noqa: E402


ALLERGEN_ZH = {"milk": "牛奶", "egg": "鸡蛋", "wheat": "小麦", "soy": "大豆", "peanut": "花生", "fish": "鱼类", "shellfish": "甲壳类", "tree_nut": "坚果"}
FOOD_ZH = {
    "iron fortified rice cereal": "大米粉", "pumpkin puree": "南瓜", "beef puree": "牛肉",
    "egg custard": "鸡蛋", "yogurt": "酸奶", "wheat noodle pieces": "面条",
    "tofu puree": "豆腐", "peanut powder mixed puree": "花生", "soft fish puree": "三文鱼",
}
TAG_TO_LABEL = {"suitable": "safe", "priority": "safe", "introduce_later": "caution", "caution": "caution", "avoid": "avoid"}

BASELINE_SYSTEMS = {
    "candidate_selection": """你是婴幼儿辅食候选选择基线模型。根据完整宝宝画像和全部候选食物逐项分类。
只返回 JSON：{"items":[{"food_id":"...","food_name_zh":"...","food_name_en":"...","decision":"safe|caution|avoid|insufficient_information","risk_types":[],"reason":"..."}]}。
不得漏掉候选食物。优先使用矫正月龄，避开已知过敏原，识别添加糖盐、高钠、质地和配料信息不足风险。""",
    "safety_rule_trigger": """你是婴幼儿辅食安全规则基线模型。判断单个候选食物。
只返回 JSON：{"decision":"safe|caution|avoid|insufficient_information|not_ready_for_complementary_food","risk_types":[],"reason":"..."}。""",
    "counterfactual_consistency": """你是婴幼儿辅食安全规则基线模型。根据当前画像判断候选食物。
只返回 JSON：{"decision":"safe|caution|avoid|insufficient_information|not_ready_for_complementary_food","risk_types":[],"reason":"..."}。""",
    "meal_plan_generation": """你是婴幼儿辅食计划基线模型。根据完整画像和候选食物制定7天计划。
只返回 JSON：{"days":[{"day":1,"foods":["food_id"]}],"avoid_food_ids":[],"warnings":[],"nutrition_notes":[]}。
不得使用已知过敏冲突食物；矫正月龄不足6个月时不得生成常规辅食计划。""",
    "profile_extraction": """从家长自然语言中抽取宝宝画像。只返回 JSON：
{"age_months":null,"corrected_age_months":null,"preterm":null,"allergies":[],"feeding_method":null,"tried_foods":[],"notes":""}。""",
    "rag_vs_plain_gpt_judge": """你是普通大模型辅食助手。根据完整宝宝画像和全部候选食物，给出个性化选择建议、风险提醒、营养搭配和理由。
必须逐项说明候选食物；信息不足时追问。不要比较其他系统的输出。""",
}

OPEN_RESPONSE_PROTOCOL = """
共同回答协议：
1. 必须逐项覆盖全部候选食物，不得遗漏。
2. 每项说明建议、主要风险、与宝宝画像相关的理由，以及必要的处理方式。
3. 优先处理已知过敏、历史不良反应、矫正月龄、窒息风险、未知配料、添加糖盐和高钠。
4. 配料、月龄或质地信息不足时，明确说明信息不足，不得直接判定安全。
5. 再考虑营养均衡、预算、家长偏好和已尝试食物。
6. 只使用输入或明确提供的知识；使用额外通用知识时必须明确标注。
"""

MEAL_PLAN_PROTOCOL = """
共同周计划协议：
1. 根据完整宝宝画像和全部候选食物生成7天计划，每天1-2种食物。
2. 不得使用已知过敏冲突、矫正月龄不适合或明确禁止的食物。
3. 新食物最多3种，优先安排在前两天并说明观察要求。
4. 尽量覆盖富铁食物、蔬菜、水果和谷物，并考虑预算、偏好和历史反馈。
5. 只能从候选食物池选择；同时列出应避免食物和安全提醒。
6. 先判断哪些候选属于普通可用食物（suitable），优先只使用普通可用食物。
7. 仅当普通可用食物只有0或1种时，才允许把风险可通过加工或观察管理的 caution 食物纳入计划。
8. 每个实际纳入计划的 caution 食物，必须在对应日期写明具体安全加工方法或观察警告。
9. 配料未知、添加糖盐、高钠、已有不良反应等不可充分管理的 caution 食物不得纳入计划。
"""

RISK_TYPE_CATALOG = """
只输出实际识别到的通用 risk_types，可选值：
under_6_complementary_food；known_allergy_milk / known_allergy_egg / known_allergy_wheat /
known_allergy_soy / known_allergy_peanut；potential_allergen；added_sugar；high_sodium；
age_below_food_min；texture_mismatch；choking_requires_preparation；forbidden_ingredient；
insufficient_info；new_food。
不要自行输出 canonical rule ID；评测器会对双方使用同一个确定性映射。
"""

RISK_TYPE_TO_RULE_ID = {
    "under_6_complementary_food": "R_AGE_BELOW_6M_NO_COMPLEMENTARY_FOOD",
    "known_allergy_milk": "R_ALLERGY_MILK",
    "known_allergy_egg": "R_ALLERGY_EGG",
    "known_allergy_wheat": "R_ALLERGY_WHEAT",
    "known_allergy_soy": "R_ALLERGY_SOY",
    "known_allergy_peanut": "R_ALLERGY_PEANUT",
    "added_sugar": "R_ADDED_SUGAR_CAUTION",
    "high_sodium": "R_ADDED_SALT_OR_HIGH_SODIUM_CAUTION",
    "age_below_food_min": "R_TEXTURE_STAGE_MISMATCH",
    "texture_mismatch": "R_TEXTURE_STAGE_MISMATCH",
    "choking_requires_preparation": "R_TEXTURE_STAGE_MISMATCH",
    "insufficient_info": "R_INSUFFICIENT_INGREDIENT_INFO",
    "new_food": "R_NEW_FOOD_INTRODUCTION",
}


def rules_from_risk_types(risk_types: list[str] | None) -> set[str]:
    return {RISK_TYPE_TO_RULE_ID[risk] for risk in risk_types or [] if risk in RISK_TYPE_TO_RULE_ID}


class LLM:
    def __init__(self, key: str, url: str, model: str):
        from openai import OpenAI
        self.model = model
        self.client = OpenAI(api_key=key, base_url=url, timeout=90, max_retries=2)
        self.calls: list[dict] = []
        self.default_max_tokens = 1600

    def chat(self, system_prompt: str, user_message: str, **kwargs) -> str:
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        call = {
            "system_prompt": system_prompt,
            "user_prompt": user_message,
            "model": kwargs.get("model", self.model),
            "max_tokens": max_tokens,
        }
        for _ in range(3):
            response = self.client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                temperature=kwargs.get("temperature", 0),
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
            if content.strip():
                call["output"] = content
                call["finish_reason"] = response.choices[0].finish_reason
                if response.usage:
                    call["usage"] = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                self.calls.append(call)
                return content
        call["output"] = ""
        self.calls.append(call)
        return ""


def load_cases(path: Path, limit: int, tasks: set[str] | None = None) -> list[dict]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    # The product contract declares age_months=0..36. Cases outside that range
    # measure unsupported behavior and are excluded from the formal score.
    rows = [
        row for row in rows
        if 0 <= int(row.get("baby_profile_structured", {}).get("age_month", 0)) <= 36
    ]
    if tasks:
        rows = [row for row in rows if row["task_type"] in tasks]
    if limit >= len(rows):
        return rows
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["task_type"]].append(row)
    tasks = sorted(groups)
    each = max(1, limit // len(tasks))
    chosen = []
    for task in tasks:
        if task == "counterfactual_consistency":
            # Preserve complete A/B pairs.
            pair_count = max(1, each // 2)
            chosen.extend(groups[task][:pair_count * 2])
        else:
            chosen.extend(groups[task][:each])
    chosen_ids = {x["case_id"] for x in chosen}
    chosen.extend(x for x in rows if x["case_id"] not in chosen_ids and len(chosen) < limit)
    return chosen[:limit]


def profile_for_app(case: dict) -> dict:
    p = case["baby_profile_structured"]
    notes = [p.get("notes_zh", "")]
    if case.get("task_type") == "meal_plan_generation" and p.get("evaluation_request"):
        notes.append(f"评测任务要求：{p['evaluation_request']}")
    if p.get("avoid_categories"):
        notes.append("希望避免：" + "、".join(map(str, p["avoid_categories"])))
    if p.get("feedback_food_name") and p.get("feedback_reaction") not in {None, "", "none", "unknown"}:
        food = FOOD_ZH.get(p["feedback_food_name"], p["feedback_food_name"])
        notes.append(f"宝宝吃了{food}后出现{p['feedback_reaction']}，日期{p.get('feedback_date', '未知')}")
    return {
        "age_months": int(p.get("age_month") or 6),
        "corrected_age_months": int(round(p.get("corrected_age_month") or p.get("age_month") or 6)),
        "allergies": [ALLERGEN_ZH.get(x, x) for x in p.get("known_allergens", [])],
        "feeding_method": p.get("feeding_method", "unknown"),
        "tried_foods": [FOOD_ZH.get(x, x) for x in p.get("tried_foods", [])],
        "birth_weight_kg": p.get("birth_weight_kg"),
        "preterm": bool(p.get("is_preterm")),
        "notes": "；".join(x for x in notes if x),
        "budget": p.get("budget_level"),
        "prefer_homemade": p.get("prefer_homemade"),
        "avoid_categories": p.get("avoid_categories", []),
        "feedback_food_name": p.get("feedback_food_name"),
        "feedback_reaction": p.get("feedback_reaction"),
        "feedback_date": p.get("feedback_date"),
    }


def candidate_payload(case: dict) -> list[dict]:
    fields = ["food_id", "food_name", "food_name_zh", "food_category", "texture_stage", "typical_age_min_month", "ingredient_text",
              "contains_milk", "contains_egg", "contains_wheat", "contains_soy", "contains_peanut", "contains_tree_nut", "contains_fish",
              "contains_shellfish", "contains_added_sugar", "contains_added_salt", "sodium_mg", "iron_mg", "is_iron_rich", "is_choking_risk_candidate"]
    return [{k: food.get(k) for k in fields} for food in case.get("candidate_foods", [])]


def baseline_user_prompt(case: dict) -> str:
    if case["task_type"] == "profile_extraction":
        return case.get("user_input_zh", "")
    payload = {
        "宝宝画像": case["baby_profile_structured"],
        "自然语言问题": case.get("user_input_zh"),
        "候选食物": candidate_payload(case),
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def baseline_system_prompt(task: str) -> str:
    prompt = BASELINE_SYSTEMS[task]
    if task == "rag_vs_plain_gpt_judge":
        prompt += "\n" + OPEN_RESPONSE_PROTOCOL
    elif task == "meal_plan_generation":
        prompt += "\n" + MEAL_PLAN_PROTOCOL
    if task in {"candidate_selection", "safety_rule_trigger", "counterfactual_consistency"}:
        prompt += "\n" + RISK_TYPE_CATALOG
    return prompt


def extract_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
    return {"raw": text, "parse_error": True}


def canonical_rule_ids(profile: dict, food: dict, decision: str) -> list[str]:
    rules = []
    corrected = profile.get("corrected_age_months", profile.get("age_months"))
    if corrected is not None and corrected < 6 and decision in {"avoid", "caution"}:
        rules.append("R_AGE_BELOW_6M_NO_COMPLEMENTARY_FOOD")
    allergen_map = {"牛奶": "milk", "鸡蛋": "egg", "小麦": "wheat", "大豆": "soy", "花生": "peanut"}
    for zh, en in allergen_map.items():
        if zh in profile.get("allergies", []) and food.get(f"contains_{en}") and decision == "avoid":
            rules.append(f"R_ALLERGY_{en.upper()}")
    if food.get("contains_added_sugar") and decision in {"avoid", "caution"}:
        rules.append("R_ADDED_SUGAR_CAUTION")
    if (food.get("contains_added_salt") or (food.get("sodium_mg") or 0) >= 200) and decision in {"avoid", "caution"}:
        rules.append("R_ADDED_SALT_OR_HIGH_SODIUM_CAUTION")
    amin = food.get("typical_age_min_month")
    if amin is not None and corrected is not None:
        try:
            if float(corrected) < float(amin) and decision in {"avoid", "caution"}:
                rules.append("R_TEXTURE_STAGE_MISMATCH")
        except Exception:
            pass
    if food.get("is_choking_risk_candidate") and decision in {"avoid", "caution"}:
        rules.append("R_TEXTURE_STAGE_MISMATCH")
    if decision == "insufficient_information":
        rules.append("R_INSUFFICIENT_INGREDIENT_INFO")
    return sorted(set(rules))


def babybites_run(case: dict, kb: JSONKnowledgeBase, engine: RuleEngine, llm: LLM) -> tuple[dict, str, str]:
    task = case["task_type"]
    profile = profile_for_app(case)
    foods = candidate_payload(case)
    mapped = []
    for food in foods:
        app_food = kb.get_food_by_name(FOOD_ZH.get(food["food_name"], food.get("food_name_zh", "")))
        mapped.append({"food_id": food["food_id"], "mapped_name": app_food.get("name_zh") if app_food else None, "food_data": app_food})
    input_record = {"profile": profile, "candidate_mapping": [{k: x[k] for k in ["food_id", "mapped_name"]} for x in mapped], "user_input": case.get("user_input_zh")}
    prompt = "NO_LLM_RULE_PIPELINE\n" + json.dumps(input_record, ensure_ascii=False, default=str)

    if task in {"candidate_selection", "safety_rule_trigger", "counterfactual_consistency"}:
        app_eval_adapter._kb = kb
        app_eval_adapter._llm = llm
        app_eval_adapter._engine = engine
        app_eval_adapter._safety = SafetyBoundaryAgent(kb=kb, rule_engine=engine, llm=llm)
        adapter_result = app_eval_adapter.evaluate_candidates(profile, foods)
        if task != "candidate_selection":
            adapter_items = adapter_result.get("items", [])
            adapter_result = adapter_items[0] if adapter_items else {"decision": "insufficient_information"}
        return adapter_result, json.dumps(adapter_result, ensure_ascii=False), prompt

        mapped_foods = [{"food_data": entry["food_data"]} for entry in mapped if entry["food_data"]]
        safety_result = SafetyBoundaryAgent(kb=kb, rule_engine=engine, llm=llm).process({
            "profile": profile,
            "candidate_foods": mapped_foods,
        })
        safety_by_app_id = safety_result.get("food_safety_results", {})
        items = []
        for entry, source_food in zip(mapped, foods):
            if not entry["food_data"]:
                decision = "insufficient_information"
                items.append({
                    "food_id": entry["food_id"], "food_name_zh": source_food.get("food_name_zh"),
                    "food_name_en": source_food.get("food_name"), "decision": decision,
                    "triggered_rule_ids": canonical_rule_ids(profile, source_food, decision),
                    "rule_reasons": ["未映射到BabyBites知识库"],
                })
                continue
            app_id = entry["food_data"].get("id", entry["food_data"].get("name_zh", ""))
            result = safety_by_app_id.get(app_id, {})
            decision = TAG_TO_LABEL.get(result.get("tag"), "caution")
            items.append({
                "food_id": entry["food_id"], "food_name_zh": source_food.get("food_name_zh"),
                "food_name_en": source_food.get("food_name"), "decision": decision,
                "triggered_rule_ids": canonical_rule_ids(profile, source_food, decision),
                "rule_reasons": result.get("reasons", []),
            })
        structured = {"items": items}
        if task != "candidate_selection":
            structured = items[0] if items else {"decision": "insufficient_information", "rule_reasons": ["无候选食物"]}
        return structured, json.dumps(structured, ensure_ascii=False), prompt

    if task == "meal_plan_generation":
        app_eval_adapter._kb = kb
        app_eval_adapter._llm = llm
        app_eval_adapter._engine = engine
        app_eval_adapter._safety = SafetyBoundaryAgent(kb=kb, rule_engine=engine, llm=llm)
        app_eval_adapter._plan = PlanGenerationAgent(kb=kb, llm=llm)
        structured = app_eval_adapter.generate_plan(profile, foods)
        return structured, json.dumps(structured, ensure_ascii=False), prompt

    if task == "profile_extraction":
        prompt = UserProfileAgent.SYSTEM_PROMPT + "\nUSER:\n" + case.get("user_input_zh", "")
        structured = UserProfileAgent(kb=kb, llm=llm).process({"user_input": case.get("user_input_zh", "")})
        return structured, json.dumps(structured, ensure_ascii=False), prompt

    unlimited_prompt = CHAT_SYSTEM_PROMPT.replace(
        '5. **简洁**：回答控制在 150 字左右，除非问题复杂需要详细解释。',
        '5. **完整**：充分回答所有候选食物、风险、营养搭配和个性化理由，不限制回答长度。',
    )
    unlimited_prompt += "\n" + OPEN_RESPONSE_PROTOCOL
    chat_module.SYSTEM_PROMPT = unlimited_prompt
    chat = ChatAgent(kb=kb, llm=llm)
    context, _ = chat._retrieve_knowledge(case.get("user_input_zh", ""))
    prompt = unlimited_prompt.format(context=context or "暂无直接相关的知识库条目。")
    previous_default = llm.default_max_tokens
    llm.default_max_tokens = 4096
    try:
        structured = chat.process({
            "message": baseline_user_prompt(case),
            "history": [],
            "candidates": foods,
            "current_profile": profile,
        })
    finally:
        llm.default_max_tokens = previous_default
    return structured, structured.get("answer", ""), prompt + "\nUSER:\n" + baseline_user_prompt(case)


def expected_labels(case: dict) -> dict[str, str]:
    labels = {}
    for fid in case.get("expected_safe_food_ids", []):
        labels[fid] = "safe"
    for fid in case.get("expected_caution_food_ids", []):
        labels[fid] = "caution"
    for fid in case.get("expected_avoid_food_ids", []):
        labels[fid] = "avoid"
    return labels


def parsed_items(pred: Any) -> dict[str, str]:
    items = pred.get("items", []) if isinstance(pred, dict) else []
    result = {}
    for item in items:
        if isinstance(item, dict) and item.get("food_id"):
            decision = str(item.get("decision", "insufficient_information")).lower()
            result[item["food_id"]] = "caution" if decision == "insufficient_information" else decision
    return result


def classification_metrics(expected: dict[str, str], predicted: dict[str, str]) -> dict:
    ids = list(expected)
    y_true = [expected[x] for x in ids]
    y_pred = [predicted.get(x, "caution") for x in ids]
    if not ids:
        return {}
    result = {"n_items": len(ids), "accuracy": accuracy_score(y_true, y_pred)}
    for average in ["macro", "micro", "weighted"]:
        p, r, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, labels=["safe", "caution", "avoid"], average=average, zero_division=0
        )
        result.update({f"{average}_precision": p, f"{average}_recall": r, f"{average}_f1": f1})
    per_precision, per_recall, per_f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=["safe", "caution", "avoid"], average=None, zero_division=0
    )
    for label, precision, recall, f1, count in zip(
        ["safe", "caution", "avoid"], per_precision, per_recall, per_f1, support
    ):
        result.update({
            f"{label}_precision": precision,
            f"{label}_recall": recall,
            f"{label}_f1": f1,
            f"{label}_support": int(count),
        })
    return result


def normalize_decision(value: str) -> str:
    value = str(value or "").lower()
    if value in {"recommend", "safe"}:
        return "safe"
    if value in {"insufficient_information", "caution"}:
        return "caution"
    if value in {"avoid", "not_ready_for_complementary_food"}:
        return "avoid"
    return value


def gold_safety_flags(case: dict, food: dict) -> dict[str, bool]:
    profile = case.get("baby_profile_structured") or {}
    corrected_age = profile.get("corrected_age_month")
    if corrected_age is None:
        corrected_age = profile.get("age_month")
    known = set(profile.get("known_allergens") or [])
    allergy = any(allergen in known and bool(food.get(f"contains_{allergen}")) for allergen in known)
    under_6 = corrected_age is not None and float(corrected_age) < 6
    choking = bool(food.get("is_choking_risk_candidate"))
    min_age = food.get("typical_age_min_month")
    below_food_min = (
        corrected_age is not None and min_age is not None
        and not pd.isna(min_age) and float(corrected_age) < float(min_age)
    )
    forbidden = bool(food.get("is_strictly_forbidden")) or bool(food.get("contains_forbidden_ingredient"))
    ingredient = food.get("ingredient_text")
    unknown = ingredient is None or pd.isna(ingredient) or not bool(str(ingredient).strip())
    return {
        "hard_risk": allergy or under_6 or below_food_min or forbidden,
        "allergy_conflict": allergy,
        "under_6": under_6,
        "choking_risk": choking,
        "unknown_ingredient": unknown,
    }


def safety_rate_metrics(instances: list[tuple[dict[str, bool], str, str]]) -> dict[str, float]:
    def rate(name: str, predicate, success) -> tuple[float, int]:
        relevant = [(flags, gold, pred) for flags, gold, pred in instances if predicate(flags, gold)]
        return (sum(success(flags, gold, pred) for flags, gold, pred in relevant) / len(relevant) if relevant else 0.0, len(relevant))

    hard_recall, hard_n = rate("hard", lambda f, _: f["hard_risk"], lambda _f, _g, p: p == "avoid")
    over_caution, safe_n = rate("safe", lambda _f, g: g == "safe", lambda _f, _g, p: p != "safe")
    allergy_recall, allergy_n = rate("allergy", lambda f, _: f["allergy_conflict"], lambda _f, _g, p: p == "avoid")
    under_6_recall, under_6_n = rate("under_6", lambda f, _: f["under_6"], lambda _f, _g, p: p == "avoid")
    choking_recall, choking_n = rate("choking", lambda f, _: f["choking_risk"], lambda _f, _g, p: p in {"caution", "avoid"})
    unknown_safe, unknown_n = rate("unknown", lambda f, _: f["unknown_ingredient"], lambda _f, _g, p: p == "safe")
    return {
        "hard_risk_recall": hard_recall,
        "hard_risk_false_negative_rate": 1.0 - hard_recall if hard_n else 0.0,
        "over_caution_rate": over_caution,
        "allergy_conflict_recall": allergy_recall,
        "under_6_block_rate": under_6_recall,
        "choking_risk_recall": choking_recall,
        "unknown_ingredient_safe_rate": unknown_safe,
        "hard_risk_n": hard_n,
        "gold_safe_n": safe_n,
        "allergy_conflict_n": allergy_n,
        "under_6_n": under_6_n,
        "choking_risk_n": choking_n,
        "unknown_ingredient_n": unknown_n,
    }


def safety_metrics(case: dict, pred: Any) -> dict:
    if isinstance(pred, dict) and "items" in pred:
        pred = pred["items"][0] if pred["items"] else {}
    decision = normalize_decision(pred.get("decision") if isinstance(pred, dict) else "")
    expected = normalize_decision(case.get("expected_decision"))
    predicted_risks = set(pred.get("risk_types", [])) if isinstance(pred, dict) else set()
    expected_risks = set(case.get("risk_types", []))
    predicted_rules = rules_from_risk_types(list(predicted_risks))
    expected_rules = rules_from_risk_types(list(expected_risks))
    tp = len(predicted_rules & expected_rules)
    precision = tp / len(predicted_rules) if predicted_rules else (1.0 if not expected_rules else 0.0)
    recall = tp / len(expected_rules) if expected_rules else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    risk_tp = len(predicted_risks & expected_risks)
    risk_precision = risk_tp / len(predicted_risks) if predicted_risks else (1.0 if not expected_risks else 0.0)
    risk_recall = risk_tp / len(expected_risks) if expected_risks else 1.0
    risk_f1 = 2 * risk_precision * risk_recall / (risk_precision + risk_recall) if risk_precision + risk_recall else 0.0
    return {
        "decision_accuracy": float(decision == expected),
        "risk_type_precision": risk_precision, "risk_type_recall": risk_recall, "risk_type_f1": risk_f1,
        "rule_precision": precision, "rule_recall": recall, "rule_f1": f1,
    }


def profile_metrics(case: dict, pred: Any) -> dict:
    expected = case.get("expected_output", {}).get("structured_profile", {})
    if isinstance(pred, dict) and "profile" in pred:
        pred = pred["profile"]
    aliases = {"is_preterm": "preterm", "gestational_age_week": "gestational_age_week", "age_month": "age_months", "corrected_age_month": "corrected_age_months",
               "known_allergens": "allergies", "tried_foods": "tried_foods", "parent_goal_seed": "notes"}
    scores = []
    for ekey, pkey in aliases.items():
        ev, pv = expected.get(ekey), pred.get(pkey) if isinstance(pred, dict) else None
        if isinstance(ev, list):
            ev, pv = set(map(str, ev)), set(map(str, pv or []))
        scores.append(float(ev == pv))
    return {"field_accuracy": sum(scores) / len(scores), "fields": len(scores)}


def meal_metrics(case: dict, pred: Any) -> dict:
    plan = pred.get("plan", pred.get("days", [])) if isinstance(pred, dict) else []
    days = len(plan) if isinstance(plan, list) else 0
    text = json.dumps(pred, ensure_ascii=False)
    plan_text = json.dumps(plan, ensure_ascii=False)
    allergies = [ALLERGEN_ZH.get(x, x) for x in case["baby_profile_structured"].get("known_allergens", [])]
    allergy_mentions = sum(a in text for a in allergies)
    categories = sum(x in text for x in ["肉", "蔬菜", "水果", "谷", "铁"])
    avoid_ids = set(case.get("expected_avoid_food_ids", []))
    foods_by_id = {food["food_id"]: food for food in case.get("candidate_foods", [])}
    unsafe_plan_items = 0
    for fid in avoid_ids:
        food = foods_by_id.get(fid, {})
        names = [fid, food.get("food_name"), food.get("food_name_zh")]
        unsafe_plan_items += int(any(str(name) in plan_text for name in names if name))
    risk_plan_items = 0
    added_sugar_plan_items = 0
    unknown_ingredient_plan_items = 0
    adverse_feedback_plan_items = 0
    choking_plan_items = 0
    profile = case.get("baby_profile_structured", {})
    for food in case.get("candidate_foods", []):
        names = [food.get("food_id"), food.get("food_name"), food.get("food_name_zh")]
        if not any(str(name) in plan_text for name in names if name):
            continue
        added_sugar = bool(food.get("contains_added_sugar"))
        ingredient = food.get("ingredient_text")
        unknown = ingredient is None or pd.isna(ingredient) or not bool(str(ingredient).strip())
        feedback = (
            profile.get("feedback_reaction") not in {None, "", "none", "unknown"}
            and profile.get("feedback_food_name") == food.get("food_name")
        )
        choking = bool(food.get("is_choking_risk_candidate"))
        added_sugar_plan_items += int(added_sugar)
        unknown_ingredient_plan_items += int(unknown)
        adverse_feedback_plan_items += int(feedback)
        choking_plan_items += int(choking)
        risk_plan_items += int(added_sugar or unknown or feedback or choking)
    return {
        "plan_days": days,
        "is_7_day_plan": float(days >= 7),
        "nutrition_category_mentions": categories,
        "allergy_mentions": allergy_mentions,
        "unsafe_plan_items": unsafe_plan_items,
        "risk_plan_items": risk_plan_items,
        "added_sugar_plan_items": added_sugar_plan_items,
        "unknown_ingredient_plan_items": unknown_ingredient_plan_items,
        "adverse_feedback_plan_items": adverse_feedback_plan_items,
        "choking_plan_items": choking_plan_items,
    }


def open_response_metrics(case: dict, pred: Any) -> dict:
    if isinstance(pred, dict):
        text = str(pred.get("answer") or pred.get("raw") or json.dumps(pred, ensure_ascii=False))
    else:
        text = str(pred or "")
    foods = candidate_payload(case)
    mentioned = 0
    for food in foods:
        names = [food.get("food_id"), food.get("food_name"), food.get("food_name_zh")]
        if any(str(name) in text for name in names if name):
            mentioned += 1
    nutrition_terms = ["铁", "蛋白", "蔬菜", "水果", "谷物", "营养", "均衡"]
    safety_terms = ["过敏", "避免", "风险", "观察", "噎", "盐", "糖"]
    return {
        "answer_chars": len(text),
        "candidate_mention_recall": mentioned / len(foods) if foods else 0.0,
        "nutrition_term_coverage": sum(term in text for term in nutrition_terms),
        "safety_term_coverage": sum(term in text for term in safety_terms),
    }


def task_metrics(case: dict, pred: Any) -> dict:
    task = case["task_type"]
    if task == "candidate_selection":
        return classification_metrics(expected_labels(case), parsed_items(pred))
    if task in {"safety_rule_trigger", "counterfactual_consistency"}:
        return safety_metrics(case, pred)
    if task == "profile_extraction":
        return profile_metrics(case, pred)
    if task == "meal_plan_generation":
        return meal_metrics(case, pred)
    return open_response_metrics(case, pred)


def aggregate(rows: list[dict]) -> pd.DataFrame:
    records = []
    for task in sorted({r["task_type"] for r in rows}):
        for system in ["babybites", "baseline"]:
            metrics = [r[f"{system}_metrics"] for r in rows if r["task_type"] == task]
            keys = sorted({k for m in metrics for k, v in m.items() if isinstance(v, (int, float))})
            record = {"task_type": task, "system": system, "cases": len(metrics)}
            for key in keys:
                vals = [float(m[key]) for m in metrics if key in m]
                record[key] = sum(vals) / len(vals) if vals else None
            records.append(record)
    return pd.DataFrame(records)


def group_metrics(rows: list[dict]) -> pd.DataFrame:
    records = []
    for task in sorted({r["task_type"] for r in rows}):
        task_rows = [r for r in rows if r["task_type"] == task]
        for system in ["babybites", "baseline"]:
            record: dict[str, Any] = {"task_type": task, "system": system, "cases": len(task_rows)}
            if task == "candidate_selection":
                expected, predicted = {}, {}
                safety_instances = []
                for row in task_rows:
                    case_expected = row["expected_labels"]
                    case_pred = parsed_items(row[f"{system}_prediction"])
                    food_by_id = {food["food_id"]: food for food in row.get("candidate_foods", [])}
                    for fid, label in case_expected.items():
                        key = f"{row['case_id']}::{fid}"
                        expected[key] = label
                        predicted[key] = case_pred.get(fid, "caution")
                        safety_instances.append((gold_safety_flags(row, food_by_id.get(fid, {})), label, predicted[key]))
                record.update(classification_metrics(expected, predicted))
                record.update(safety_rate_metrics(safety_instances))
            elif task in {"safety_rule_trigger", "counterfactual_consistency"}:
                y_true, y_pred = [], []
                rule_tp = rule_pred = rule_expected = 0
                risk_tp = risk_pred = risk_expected = 0
                safety_instances = []
                for row in task_rows:
                    pred = row[f"{system}_prediction"]
                    if isinstance(pred, dict) and "items" in pred:
                        pred = pred["items"][0] if pred["items"] else {}
                    y_true.append(normalize_decision(row.get("expected_decision")))
                    y_pred.append(normalize_decision(pred.get("decision") if isinstance(pred, dict) else ""))
                    food = (row.get("candidate_foods") or [{}])[0]
                    safety_instances.append((gold_safety_flags(row, food), y_true[-1], y_pred[-1]))
                    predicted_risks = set(pred.get("risk_types", [])) if isinstance(pred, dict) else set()
                    expected_risks = set(row.get("risk_types", []))
                    risk_tp += len(predicted_risks & expected_risks)
                    risk_pred += len(predicted_risks)
                    risk_expected += len(expected_risks)
                    pr = rules_from_risk_types(list(predicted_risks))
                    er = rules_from_risk_types(list(expected_risks))
                    rule_tp += len(pr & er)
                    rule_pred += len(pr)
                    rule_expected += len(er)
                p, r, f1, _ = precision_recall_fscore_support(
                    y_true, y_pred, labels=["safe", "caution", "avoid"], average="macro", zero_division=0
                )
                per_p, per_r, per_f1, per_support = precision_recall_fscore_support(
                    y_true, y_pred, labels=["safe", "caution", "avoid"], average=None, zero_division=0
                )
                rp = rule_tp / rule_pred if rule_pred else (1.0 if not rule_expected else 0.0)
                rr = rule_tp / rule_expected if rule_expected else 1.0
                rf = 2 * rp * rr / (rp + rr) if rp + rr else 0.0
                risk_p = risk_tp / risk_pred if risk_pred else (1.0 if not risk_expected else 0.0)
                risk_r = risk_tp / risk_expected if risk_expected else 1.0
                risk_f = 2 * risk_p * risk_r / (risk_p + risk_r) if risk_p + risk_r else 0.0
                record.update({
                    "decision_accuracy": accuracy_score(y_true, y_pred),
                    "decision_macro_precision": p,
                    "decision_macro_recall": r,
                    "decision_macro_f1": f1,
                    "rule_micro_precision": rp,
                    "rule_micro_recall": rr,
                    "rule_micro_f1": rf,
                    "risk_type_micro_precision": risk_p,
                    "risk_type_micro_recall": risk_r,
                    "risk_type_micro_f1": risk_f,
                })
                for label, precision, recall, class_f1, support in zip(
                    ["safe", "caution", "avoid"], per_p, per_r, per_f1, per_support
                ):
                    record.update({
                        f"decision_{label}_precision": precision,
                        f"decision_{label}_recall": recall,
                        f"decision_{label}_f1": class_f1,
                        f"decision_{label}_support": int(support),
                    })
                record.update(safety_rate_metrics(safety_instances))
                if task == "counterfactual_consistency":
                    by_pair: dict[str, list[tuple[str, str]]] = defaultdict(list)
                    for row, true, pred_value in zip(task_rows, y_true, y_pred):
                        by_pair[re.sub(r"_[AB]$", "", row["case_id"])].append((true, pred_value))
                    complete = [vals for vals in by_pair.values() if len(vals) == 2]
                    record["complete_pairs"] = len(complete)
                    record["pair_accuracy"] = (
                        sum(all(true == pred_value for true, pred_value in vals) for vals in complete) / len(complete)
                        if complete else 0.0
                    )
            else:
                metrics = [row[f"{system}_metrics"] for row in task_rows]
                for key in sorted({k for m in metrics for k, v in m.items() if isinstance(v, (int, float))}):
                    vals = [float(m[key]) for m in metrics if key in m]
                    record[key] = sum(vals) / len(vals)
            records.append(record)
    return pd.DataFrame(records)


def report(summary: pd.DataFrame, groups: pd.DataFrame, rows: list[dict], out: Path, model: str) -> None:
    def value(task: str, system: str, key: str) -> float:
        match = groups[(groups["task_type"] == task) & (groups["system"] == system)]
        if match.empty or key not in match.columns or pd.isna(match.iloc[0][key]):
            return float("nan")
        return float(match.iloc[0][key])

    parse_errors = {
        system: sum(
            isinstance(row.get(f"{system}_prediction"), dict)
            and bool(row[f"{system}_prediction"].get("parse_error"))
            and row["task_type"] != "rag_vs_plain_gpt_judge"
            for row in rows
        )
        for system in ["babybites", "baseline"]
    }
    mapping_values = [row["babybites_mapping_coverage"] for row in rows if row.get("babybites_mapping_coverage") is not None]
    mapping_coverage = sum(mapping_values) / len(mapping_values) if mapping_values else 0.0
    calls_by_task = Counter(
        row["task_type"] for row in rows for _ in row.get("babybites_llm_calls", [])
    )
    is_v606 = "V606" in str(APP_ROOT)
    lines = [
        "# BabyBites 与同模型纯 LLM 基线分任务评测完整报告",
        "",
        "## 结论口径",
        "",
        f"- 本轮显式指定模型为 `{model}`，BabyBites 应用目录为 `{APP_ROOT}`。",
        (
            "- V606 的安全路径会调用 LLM 从备注中识别过敏/不耐受食材，但最终候选标签仍由规则引擎产生；画像抽取和 Chat/RAG 路径也会调用同一模型。"
            if is_v606 else
            "- 旧版 BabyBites 的画像抽取和 Chat/RAG 路径调用 LLM；候选选择、安全触发和周计划主要由规则代码产生。"
        ),
        "- 仓库没有锁定“主要 DeepSeek 型号”：代码默认是 `gpt-4o-mini`，`.env.example` 只列出多个可选 DeepSeek 型号。因此本轮选择 v4-flash 是实验配置，不是仓库事实。",
        f"- 正式评分样本数：{len(rows)}，仅纳入产品输入契约声明的 0–36 月龄。",
        "- 本报告不包含独立 GPT/Qwen2.5 judge 分数。开放式回答的字符数、候选覆盖和关键词覆盖仅是代理统计，不能代表回答质量。",
        "- 之前出现的“详细程度、长期计划、营养均衡、安全规则覆盖率”表来自关键词/规则代理脚本，不是第三方评测结果，不应作为正式结论。",
        "",
        "## 输入与 Prompt 协议",
        "",
        "- `candidate_selection`、`safety_rule_trigger`、`counterfactual_consistency`、`meal_plan_generation`、`rag_vs_plain_gpt_judge`：基线收到完整宝宝画像、自然语言问题和全部候选食物字段。",
        "- `profile_extraction`：双方只收到同一段家长自然语言，基线不再看到标准结构化画像。",
        "- `rag_vs_plain_gpt_judge`：双方分别回答完整宝宝画像与候选食物问题；基线不再被要求比较两个系统输出。",
        "- 每条样本的 BabyBites prompt、基线 system prompt、基线 user prompt、双方原始输出和解析结果见 `formal_results.jsonl`；便于表格查看的 prompt 清单见 `prompt_manifest.csv`。",
        "- `babybites_llm_calls` 记录 BabyBites 内部真实发送给模型的每次 system/user prompt；规则路径的组合输入单独记录为 `babybites_prompt`，不能等同于 LLM prompt。",
        "- 本轮评测移除了 BabyBites Chat prompt 中“回答控制在 150 字左右”的限制，双方均不设置回答长度风格限制。",
        "",
        "## 正式组内指标",
        "",
    ]
    cols = list(groups.columns)
    lines += ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for rec in groups.fillna("").astype(str).to_dict("records"):
        lines.append("| " + " | ".join(rec[c] for c in cols) + " |")
    lines += [
        "",
        "## 关键结果解读",
        "",
        f"- 候选选择：BabyBites accuracy/macro-F1 为 {value('candidate_selection', 'babybites', 'accuracy'):.3f}/{value('candidate_selection', 'babybites', 'macro_f1'):.3f}；同模型基线为 {value('candidate_selection', 'baseline', 'accuracy'):.3f}/{value('candidate_selection', 'baseline', 'macro_f1'):.3f}。BabyBites 的知识库映射覆盖不足是主要约束之一。",
        f"- 安全规则触发：BabyBites 决策 accuracy/rule micro-F1 为 {value('safety_rule_trigger', 'babybites', 'decision_accuracy'):.3f}/{value('safety_rule_trigger', 'babybites', 'rule_micro_f1'):.3f}；基线为 {value('safety_rule_trigger', 'baseline', 'decision_accuracy'):.3f}/{value('safety_rule_trigger', 'baseline', 'rule_micro_f1'):.3f}。",
        f"- 反事实一致性：BabyBites 的完整 A/B 对准确率为 {value('counterfactual_consistency', 'babybites', 'pair_accuracy'):.3f}，基线为 {value('counterfactual_consistency', 'baseline', 'pair_accuracy'):.3f}。BabyBites 能识别过敏规则，但无过敏状态下常因质地规则给出 caution，导致整对不一致。",
        f"- 画像抽取：BabyBites field accuracy 为 {value('profile_extraction', 'babybites', 'field_accuracy'):.3f}，基线为 {value('profile_extraction', 'baseline', 'field_accuracy'):.3f}；BabyBites 的主要问题是项目结构化解析实现缺陷。",
        f"- 周计划：BabyBites 7 天完整率为 {value('meal_plan_generation', 'babybites', 'is_7_day_plan'):.3f}，基线为 {value('meal_plan_generation', 'baseline', 'is_7_day_plan'):.3f}。样本包含矫正月龄不足 6 月的情形，BabyBites 仍生成常规 7 天辅食计划，需作为安全缺陷单独修复。",
        f"- 开放式回答：BabyBites 平均 {value('rag_vs_plain_gpt_judge', 'babybites', 'answer_chars'):.0f} 字符，基线平均 {value('rag_vs_plain_gpt_judge', 'baseline', 'answer_chars'):.0f} 字符。长度差异不代表质量优劣，必须等待独立 judge 或人工盲评。",
        "",
        "## 指标定义",
        "",
        "- 候选选择：将该任务全部候选食物合并后计算三分类 accuracy、macro precision/recall/F1。",
        "- 安全触发：计算最终决策三分类 accuracy/macro-F1，以及 canonical rule_id 的 micro precision/recall/F1。",
        "- 反事实一致性：除安全触发指标外，`pair_accuracy` 要求同一 A/B 过敏状态对的两个判断都正确。",
        "- 画像抽取：对标准画像字段计算 field accuracy。BabyBites 当前项目实现会因结构化解析缺陷回退到默认画像，此分数反映现有代码行为。",
        "- 周计划：统计 7 天完整率、计划天数、营养类别提示、过敏提示和计划内不安全候选数；这些还不是完整营养学质量评价。",
        "- RAG/普通模型回答：只统计候选食物提及率和安全/营养关键词覆盖；没有独立 judge 时不输出主观总分。",
        "",
        "## 运行完整性",
        "",
        f"- BabyBites 结构化任务解析失败：{parse_errors['babybites']}。",
        f"- 基线结构化任务解析失败：{parse_errors['baseline']}。",
        f"- BabyBites 候选食物到内置知识库的平均映射覆盖率：{mapping_coverage:.3f}。未映射食物被记为信息不足，这会直接影响候选选择能力。",
        f"- BabyBites 内部真实 LLM 调用次数按任务统计：`{dict(calls_by_task)}`。",
        "- `rag_vs_plain_gpt_judge` 的基线输出是自由文本，保存为 `raw` 属于预期行为，不算解析失败。",
        "",
        "## 已确认的系统实现问题",
        "",
        "- `agents/base.py` 中 `_ask_llm_structured()` 没有调用项目已有的 `chat_structured()`，而是返回 `{\"raw\": response, \"schema\": ...}`。`UserProfileAgent` 随后找不到画像字段并回退为默认 6 月龄画像。",
        "- BabyBites 周计划从整个内置知识库生成，而纯 LLM 基线被要求从评测候选列表生成；两者输出空间不同，计划质量比较必须结合该差异解释。",
        "- V606 在安全路径中新增 LLM 备注解析，但最终安全标签和周计划仍主要由规则代码产生；“调用过 LLM”不能解释为“LLM 看到了全部字段并生成最终答案”。",
        "",
        "## 重要限制",
        "",
        "- 当前是分层小样本评测，用于验证协议和发现实现问题，不足以给出稳定的生产级置信区间。",
        "- 标准答案由数据生成规则构造，并不等同于儿科医生逐条审核的金标准。",
        "- 第三方 GPT/Qwen2.5 judge 尚未配置，因此详细程度、长期计划能力、营养均衡度、家长友好度等开放式质量没有独立模型评分。",
        "- `per_case_metric_summary.csv` 是逐样本指标的平均值；正式任务级分类结论应优先查看 `group_metrics.csv`。",
    ]
    (out / "formal_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/evaluation/evaluation_cases.jsonl")
    parser.add_argument("--out", default="outputs/formal_evaluation")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "deepseek-v4-flash"))
    parser.add_argument("--resume-from", default="")
    parser.add_argument("--refresh-babybites-tasks", default="")
    parser.add_argument("--judge-after", action="store_true")
    parser.add_argument("--judge-model", default=os.getenv("JUDGE_MODEL", "qwen-plus"))
    parser.add_argument("--tasks", default="")
    args = parser.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    progress_path = out / "progress.jsonl"
    progress_path.write_text("", encoding="utf-8")
    key = os.getenv("OPENAI_API_KEY", "")
    url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required")
    llm = LLM(key, url, args.model)
    kb, engine = JSONKnowledgeBase(), RuleEngine(JSONKnowledgeBase())
    selected_tasks = {task.strip() for task in args.tasks.split(",") if task.strip()}
    cases = load_cases(ROOT / args.input, args.limit, selected_tasks)
    existing_by_id = {}
    refresh_babybites_tasks = {task.strip() for task in args.refresh_babybites_tasks.split(",") if task.strip()}
    if args.resume_from:
        resume_path = ROOT / args.resume_from
        existing_by_id = {
            row["case_id"]: row
            for row in (json.loads(line) for line in resume_path.read_text(encoding="utf-8").splitlines() if line.strip())
        }
    rows = []
    for i, case in enumerate(cases, 1):
        existing = existing_by_id.get(case["case_id"])
        existing_baseline = existing.get("baseline_prediction") if existing else None
        refresh_babybites = case["task_type"] in refresh_babybites_tasks
        retry_parse_error = (
            case["task_type"] != "rag_vs_plain_gpt_judge"
            and isinstance(existing_baseline, dict)
            and existing_baseline.get("parse_error")
        )
        if existing and not retry_parse_error and not refresh_babybites:
            existing["expected_labels"] = expected_labels(case)
            existing["triggered_rule_ids"] = case.get("triggered_rule_ids", [])
            existing["baby_profile_structured"] = case.get("baby_profile_structured", {})
            existing["candidate_foods"] = case.get("candidate_foods", [])
            existing["risk_types"] = case.get("risk_types", [])
            existing["babybites_metrics"] = task_metrics(case, existing["babybites_prediction"])
            existing["baseline_metrics"] = task_metrics(case, existing["baseline_prediction"])
            rows.append(existing)
            with progress_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(existing, ensure_ascii=False, default=str) + "\n")
            print(f"[{i}/{len(cases)}] {case['case_id']} {case['task_type']} resumed")
            continue
        baby_call_start = len(llm.calls)
        b_struct, b_raw, b_prompt = babybites_run(case, kb, engine, llm)
        baby_llm_calls = llm.calls[baby_call_start:]
        mapping_coverage = None
        if b_prompt.startswith("NO_LLM_RULE_PIPELINE\n"):
            prompt_data = json.loads(b_prompt.split("\n", 1)[1])
            mappings = prompt_data.get("candidate_mapping", [])
            if mappings:
                mapping_coverage = sum(bool(item.get("mapped_name")) for item in mappings) / len(mappings)
        base_system = baseline_system_prompt(case["task_type"])
        base_user = baseline_user_prompt(case)
        if refresh_babybites and existing:
            base_raw = existing.get("baseline_output", "")
            baseline_llm_calls = existing.get("baseline_llm_calls", [])
            base_struct = existing.get("baseline_prediction", {})
            base_system = existing.get("baseline_system_prompt", base_system)
            base_user = existing.get("baseline_user_prompt", base_user)
        else:
            max_tokens = 4096 if case["task_type"] in {"meal_plan_generation", "rag_vs_plain_gpt_judge"} else (
                3600 if case["task_type"] == "candidate_selection" else 1800
            )
            baseline_call_start = len(llm.calls)
            base_raw = llm.chat(base_system, base_user, max_tokens=max_tokens)
            baseline_llm_calls = llm.calls[baseline_call_start:]
            base_struct = extract_json(base_raw)
        result_row = {
            "case_id": case["case_id"], "task_type": case["task_type"],
            "expected_decision": case.get("expected_decision"), "expected_output": case.get("expected_output"),
            "expected_labels": expected_labels(case), "triggered_rule_ids": case.get("triggered_rule_ids", []),
            "baby_profile_structured": case.get("baby_profile_structured", {}),
            "candidate_foods": case.get("candidate_foods", []), "risk_types": case.get("risk_types", []),
            "babybites_prompt": b_prompt, "baseline_system_prompt": base_system, "baseline_user_prompt": base_user,
            "babybites_llm_calls": baby_llm_calls, "baseline_llm_calls": baseline_llm_calls,
            "babybites_output": b_raw, "baseline_output": base_raw,
            "babybites_prediction": b_struct, "baseline_prediction": base_struct,
            "babybites_metrics": task_metrics(case, b_struct), "baseline_metrics": task_metrics(case, base_struct),
            "babybites_mapping_coverage": mapping_coverage,
        }
        rows.append(result_row)
        with progress_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result_row, ensure_ascii=False, default=str) + "\n")
        print(f"[{i}/{len(cases)}] {case['case_id']} {case['task_type']}")
    with (out / "formal_results.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    flat = []
    for row in rows:
        flat.append({k: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    pd.DataFrame(flat).to_csv(out / "formal_results.csv", index=False, encoding="utf-8-sig")
    summary = aggregate(rows)
    summary.to_csv(out / "per_case_metric_summary.csv", index=False, encoding="utf-8-sig")
    groups = group_metrics(rows)
    groups.to_csv(out / "group_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([
        {
            "case_id": row["case_id"],
            "task_type": row["task_type"],
            "babybites_prompt": row["babybites_prompt"],
            "baseline_system_prompt": row["baseline_system_prompt"],
            "baseline_user_prompt": row["baseline_user_prompt"],
            "babybites_llm_calls": json.dumps(row.get("babybites_llm_calls", []), ensure_ascii=False),
            "baseline_llm_calls": json.dumps(row.get("baseline_llm_calls", []), ensure_ascii=False),
        }
        for row in rows
    ]).to_csv(out / "prompt_manifest.csv", index=False, encoding="utf-8-sig")
    report(summary, groups, rows, out, args.model)
    (out / "run_config.json").write_text(json.dumps({
        "model": args.model,
        "base_url": url,
        "cases": len(rows),
        "age_scope_months": [0, 36],
        "third_party_judge": None,
        "babybites_app_root": str(APP_ROOT),
        "fairness_protocol": {
            "shared_input": "same complete profile, user request, and candidate pool",
            "rag_shared_output_max_tokens": 4096,
            "rag_temperature": 0,
            "meal_plan_baseline_output_max_tokens": 4096,
            "meal_plan_babybites_output_max_tokens": 4096,
            "meal_plan_babybites_note": "product safety filter followed by DeepSeek plan generation; deterministic fallback on invalid LLM output",
            "rag_candidate_injection": True,
        },
        "model_selection_note": "Explicit evaluation setting; repository default is gpt-4o-mini and no main DeepSeek variant is locked.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote={out} tasks={dict(Counter(r['task_type'] for r in rows))}")
    if args.judge_after:
        judge_out = out / "third_party_judge"
        subprocess.run([
            sys.executable,
            str(ROOT / "scripts" / "10_run_third_party_judge.py"),
            "--cases", str((ROOT / args.input).resolve()),
            "--results", str((out / "formal_results.jsonl").resolve()),
            "--out", str(judge_out.resolve()),
            "--model", args.judge_model,
        ], check=True, cwd=ROOT)
        subprocess.run([
            sys.executable,
            str(ROOT / "scripts" / "12_finalize_evaluation_report.py"),
            "--out", str(out.resolve()),
        ], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
