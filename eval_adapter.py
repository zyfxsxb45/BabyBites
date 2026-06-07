"""
评测适配器。

将标准评测输入格式转换为 BabyBites 系统调用，输出评测期望的格式。
供评测框架直接调用，无需手动拼接 agent 调用链。
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.json_backend import JSONKnowledgeBase
from kb.external_food import external_food_to_internal, resolve_food
from rules.engine import RuleEngine
from agents.safety_boundary import SafetyBoundaryAgent
from agents.plan_generation import PlanGenerationAgent
from agents.label_parsing import LabelParsingAgent
from agents.chat import ChatAgent
from agents.user_profile import UserProfileAgent
from utils.loader import init_kb, init_llm

# 全局单例（避免每次调用重复初始化）
_kb: JSONKnowledgeBase | None = None
_llm: Any = None
_engine: RuleEngine | None = None
_safety: SafetyBoundaryAgent | None = None
_plan: PlanGenerationAgent | None = None
_label: LabelParsingAgent | None = None
_chat: ChatAgent | None = None
_profile_agent: UserProfileAgent | None = None


def _ensure_init():
    global _kb, _llm, _engine, _safety, _plan, _label, _chat, _profile_agent
    if _kb is None:
        _kb = init_kb()
        try:
            _llm = init_llm()
        except Exception:
            _llm = None  # LLM 不可用时降级
        _engine = RuleEngine(_kb)
        _safety = SafetyBoundaryAgent(kb=_kb, rule_engine=_engine, llm=_llm)
        _plan = PlanGenerationAgent(kb=_kb, llm=_llm)
        _label = LabelParsingAgent(kb=_kb, llm=_llm)
        _chat = ChatAgent(kb=_kb, llm=_llm)
        _profile_agent = UserProfileAgent(kb=_kb, llm=_llm)


def evaluate_candidates(
    profile: dict[str, Any],
    candidates: list[dict[str, Any]],
    strict_mode: bool = False,
) -> dict[str, Any]:
    """
    评测核心入口：对候选食材列表逐一评估。

    Args:
        profile: 宝宝画像
            {
                age_months: int,
                corrected_age_months: int | None,
                allergies: list[str],
                feeding_method: str,
                tried_foods: list[str],
                notes: str,
            }
        candidates: 候选食材列表（eval 格式）
            [{
                food_name: str,
                food_name_zh: str,
                contains_milk: bool,
                contains_egg: bool,
                ...
                contains_added_salt: bool,
                contains_added_sugar: bool,
                is_choking_risk_candidate: bool,
            }]
        strict_mode: 是否严格模式（收敛潜在过敏原判定）

    Returns:
        {
            items: [{food_id, food_name_zh, decision, triggered_rule_ids, reasons}],
            profile_summary: {...},
        }
    """
    _ensure_init()

    # 1. 安全评估
    candidate_foods = [{"food_data": c} for c in candidates]
    safety_result = _safety.process({
        "profile": profile,
        "candidate_foods": candidate_foods,
        "strict_mode": strict_mode,
    })

    # 2. 构建逐项输出
    items = []
    for c in candidates:
        name_zh = c.get("food_name_zh") or c.get("food_name") or ""
        name_en = c.get("food_name") or ""
        food_id = c.get("food_id", "")

        # 查安全评估结果（支持多个可能的名称键）
        tag_info = (
            safety_result.get("food_safety_results", {}).get(name_zh, {})
            or safety_result.get("food_safety_results", {}).get(name_en, {})
        )
        # 如果还没找到，用 resolve_food 后的名字再查
        resolved = resolve_food(c, kb=_kb)
        if not tag_info and resolved:
            tag_info = safety_result.get("food_safety_results", {}).get(
                resolved.get("name_zh", ""), {}
            )
        decision_map = {"suitable": "safe", "avoid": "avoid", "caution": "caution"}
        decision = decision_map.get(tag_info.get("tag"), "insufficient_information")

        # 提取触发的规则 ID
        reasons = tag_info.get("reasons", [])
        rule_ids = _map_reasons_to_rule_ids(reasons)

        # 补充来自原始字段的规则（仅外部食材）
        if resolved and resolved.get("_external"):
            if resolved.get("_contains_added_salt") or (resolved.get("_sodium_mg") or 0) > 200:
                rule_ids.append("R_ADDED_SALT_OR_HIGH_SODIUM_CAUTION")
            if resolved.get("_contains_added_sugar"):
                rule_ids.append("R_ADDED_SUGAR_CAUTION")
            if resolved.get("_is_choking_risk"):
                rule_ids.append("R_CHOKING_RISK_CAUTION")
            for ext_key, rule_id in [
                ("contains_milk", "R_ALLERGY_MILK"),
                ("contains_egg", "R_ALLERGY_EGG"),
                ("contains_wheat", "R_ALLERGY_WHEAT"),
                ("contains_soy", "R_ALLERGY_SOY"),
                ("contains_peanut", "R_ALLERGY_PEANUT"),
                ("contains_tree_nut", "R_ALLERGY_TREE_NUT"),
                ("contains_fish", "R_ALLERGY_FISH"),
                ("contains_shellfish", "R_ALLERGY_SHELLFISH"),
            ]:
                if resolved["_allergen_flags"].get(ext_key) and decision == "avoid":
                    rule_ids.append(rule_id)

        items.append({
            "food_id": food_id or f"ext_{name_zh}",
            "food_name_zh": name_zh,
            "food_name": name_en,
            "decision": decision,
            "triggered_rule_ids": list(set(rule_ids)),
            "reasons": reasons,
        })

        # 未知食材补充规则 ID
        if decision == "insufficient_information":
            items[-1]["triggered_rule_ids"].append("R_INSUFFICIENT_INGREDIENT_INFO")

    # 全局年龄阻断
    age = profile.get("corrected_age_months") or profile.get("age_months", 6)
    if age < 6:
        for item in items:
            if item["decision"] != "avoid":
                item["decision"] = "not_ready_for_complementary_food"
                item["triggered_rule_ids"].append("R_AGE_BELOW_6M_NO_COMPLEMENTARY_FOOD")

    return {
        "items": items,
        "profile_summary": {
            "can_start": safety_result.get("can_start"),
            "effective_age": safety_result.get("effective_age_months"),
            "stage": safety_result.get("stage", {}).get("label", ""),
        },
    }


def extract_profile(user_input: str) -> dict[str, Any]:
    """从自然语言提取结构化画像"""
    _ensure_init()
    result = _profile_agent.process({"user_input": user_input})
    return result.get("profile", {})


def generate_plan(profile: dict[str, Any], candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """生成周计划（可选限制候选池）"""
    _ensure_init()
    stage = _kb.get_age_stage(profile.get("age_months", 6))

    # 构建安全食材池
    if candidates:
        safe_foods = []
        for c in candidates:
            resolved = resolve_food(c, kb=_kb)
            if resolved:
                result = _engine.evaluate_food(resolved, profile)
                if result.overall_tag != "avoid":
                    safe_foods.append({"food_data": resolved, "tag": result.overall_tag})
    else:
        all_foods = _kb.list_foods_by_age(profile.get("age_months", 6))
        safe_foods = [{"food_data": f, "tag": "suitable"} for f in all_foods]

    plan_result = _plan.process({
        "profile": profile,
        "safe_foods": safe_foods,
        "stage": stage,
    })
    return plan_result


def parse_label(ingredient_text: str, age_months: int = 6) -> dict[str, Any]:
    """解析配料表"""
    _ensure_init()
    return _label.process({"ingredient_text": ingredient_text, "age_months": age_months})


def chat(message: str, history: list[dict] | None = None) -> dict[str, Any]:
    """智能问答"""
    _ensure_init()
    return _chat.process({"message": message, "history": history or []})


def _map_reasons_to_rule_ids(reasons: list[str]) -> list[str]:
    """从中文原因文本映射到标准规则 ID"""
    mapping = [
        ("过敏", "R_ALLERGY_KNOWN"),
        ("牛奶", "R_ALLERGY_MILK"),
        ("鸡蛋", "R_ALLERGY_EGG"),
        ("小麦", "R_ALLERGY_WHEAT"),
        ("大豆", "R_ALLERGY_SOY"),
        ("花生", "R_ALLERGY_PEANUT"),
        ("坚果", "R_ALLERGY_TREE_NUT"),
        ("鱼类", "R_ALLERGY_FISH"),
        ("虾", "R_ALLERGY_SHELLFISH"),
        ("芝麻", "R_ALLERGY_SESAME"),
        ("高钠", "R_ADDED_SALT_OR_HIGH_SODIUM_CAUTION"),
        ("盐", "R_ADDED_SALT_OR_HIGH_SODIUM_CAUTION"),
        ("添加糖", "R_ADDED_SUGAR_CAUTION"),
        ("窒息", "R_CHOKING_RISK_CAUTION"),
        ("未满 6 个月", "R_AGE_BELOW_6M_NO_COMPLEMENTARY_FOOD"),
        ("月龄", "R_AGE_UNDER_RECOMMENDED"),
        ("质地", "R_TEXTURE_STAGE_MISMATCH"),
        ("配料未知", "R_INSUFFICIENT_INGREDIENT_INFO"),
        ("信息不足", "R_INSUFFICIENT_INGREDIENT_INFO"),
        ("未收录", "R_INSUFFICIENT_INGREDIENT_INFO"),
    ]
    ids = []
    for reason in reasons:
        for keyword, rule_id in mapping:
            if keyword in reason:
                ids.append(rule_id)
    return ids
