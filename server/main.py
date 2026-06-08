"""
BabyBites FastAPI 后端。

将所有 Agent 封装为 REST API，供 React 前端调用。
启动：python server/main.py
"""

import sys
from pathlib import Path

# 确保项目根在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from utils.loader import init_kb, init_llm
from agents.safety_boundary import SafetyBoundaryAgent
from agents.plan_generation import PlanGenerationAgent
from agents.label_parsing import LabelParsingAgent
from agents.chat import ChatAgent
from rules.engine import RuleEngine
from data.feedback_store import FeedbackStore
from rules.feedback import get_feedback_adjusted_foods

# ===== 全局初始化 =====
print("🔧 初始化 BabyBites 后端...")
kb = init_kb()
llm = init_llm()
engine = RuleEngine(kb)
safety_agent = SafetyBoundaryAgent(kb=kb, rule_engine=engine, llm=llm)
plan_agent = PlanGenerationAgent(kb=kb, llm=llm)
label_agent = LabelParsingAgent(kb=kb, llm=llm)
chat_agent = ChatAgent(kb=kb, llm=llm)
feedback_store = FeedbackStore()
print("✅ 初始化完成")

app = FastAPI(title="宝宝巴适 BabyBites API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================================================
# Pydantic 模型
# ================================================================

class BabyProfile(BaseModel):
    age_months: int = 6
    corrected_age_months: Optional[int] = None
    allergies: list[str] = []
    feeding_method: str = "breast"
    tried_foods: list[str] = []
    notes: str = ""
    preterm: bool = False
    budget: Optional[str] = None
    prefer_homemade: Optional[bool] = None
    avoid_categories: list[str] = []
    feedback_food_name: Optional[str] = None
    feedback_reaction: Optional[str] = None
    feedback_date: Optional[str] = None


class AssessRequest(BaseModel):
    profile: BabyProfile


class PlanRequest(BaseModel):
    profile: BabyProfile
    candidates: Optional[list[dict]] = None  # 候选食材列表，不传则用全量KB


class LabelRequest(BaseModel):
    ingredient_text: str
    age_months: int = 6


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class FeedbackRequest(BaseModel):
    food_name: str
    reaction: str  # none / rash / diarrhea / vomiting / refusal / other
    severity: str = "mild"  # mild / moderate / severe
    notes: str = ""


# ================================================================
# API 路由
# ================================================================

@app.get("/")
def root():
    """根路由重定向到 API 文档"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")

@app.get("/api/health")
def health():
    return {"status": "ok", "kb_stats": kb.get_stats()}


# ---------- 安全评估 ----------

@app.post("/api/assess")
def assess(req: AssessRequest):
    """评估宝宝辅食准备状态 + 食材安全标签"""
    profile = req.profile.model_dump()

    # 获取所有适龄食材
    all_foods = kb.list_foods_by_age(profile["age_months"])
    candidate_foods = [{"food_data": f} for f in all_foods]

    result = safety_agent.process({
        "profile": profile,
        "candidate_foods": candidate_foods,
    })

    # 整理返回
    food_tags = {}
    for fid, fr in result.get("food_safety_results", {}).items():
        food = kb.get_food(fid) or kb.get_food_by_name(fid)
        name = food.get("name_zh", fid) if food else fid
        food_tags[name] = {
            "tag": fr["tag"],
            "reasons": fr["reasons"],
            "iron_rich": bool(food.get("iron_rich")) if food else False,
            "potential_allergen": bool(food.get("potential_allergen")) if food else False,
        }

    return {
        "can_start": result["can_start"],
        "stage": result.get("stage"),
        "effective_age_months": result["effective_age_months"],
        "readiness_signals": result["readiness_signals"],
        "blocking_reasons": result["blocking_reasons"],
        "recommendation": result["recommendation"],
        "food_tags": food_tags,
        "notes_avoid_foods": result.get("notes_avoid_foods", []),
        "direct_avoid_foods": result.get("direct_avoid_foods", []),
    }


# ---------- 周度计划 ----------

@app.post("/api/plan")
def generate_plan(req: PlanRequest):
    """生成一周辅食计划。candidates 非空时只从候选池生成，否则用全量KB。"""
    profile = req.profile.model_dump()
    effective_age = profile.get("corrected_age_months") if profile.get("preterm") else None
    effective_age = effective_age if effective_age is not None else profile["age_months"]
    stage = kb.get_age_stage(effective_age)
    if effective_age < 6:
        return {
            "plan": [],
            "new_foods_this_week": [],
            "stage_label": (stage or {}).get("label", ""),
            "nutrition_notes": ["矫正月龄不足6个月，暂不生成常规辅食计划。"],
            "validated": True,
            "validation_warnings": ["矫正月龄不足6个月，尚未达到常规辅食引入阶段。"],
            "validation_violations": [],
        }

    # 从备注中提取过敏/不耐受食材，注入过敏原列表（以便 engine 统一拦截）
    notes = profile.get("notes", "")
    if notes:
        all_foods_for_notes = kb.list_foods_by_age(profile["age_months"])
        candidate_for_notes = [{"food_data": f} for f in all_foods_for_notes]
        llm_avoid = safety_agent._llm_extract_allergies_from_notes(notes, candidate_for_notes)
        kw_avoid = safety_agent._extract_avoid_foods_from_notes(notes, candidate_for_notes)
        notes_avoid = llm_avoid | kw_avoid
        if notes_avoid:
            profile["allergies"] = list(set(profile.get("allergies", [])) | notes_avoid)

    safe_foods = []

    if req.candidates:
        # 评测/约束模式：只从给定候选池中选，只用 safe
        from kb.external_food import resolve_food
        for c in req.candidates:
            resolved = resolve_food(c, kb=kb)
            if not resolved:
                continue
            result = engine.evaluate_food(resolved, profile)
            category = str(c.get("food_category") or resolved.get("category") or "").lower()
            if category in {str(x).lower() for x in profile.get("avoid_categories", [])}:
                continue
            if result.overall_tag == "suitable":
                safe_foods.append({"food_data": resolved, "tag": result.overall_tag})
    else:
        # 正常模式：全量KB
        all_foods = kb.list_foods_by_age(profile["age_months"])
        for f in all_foods:
            result = engine.evaluate_food(f, profile)
            if result.overall_tag != "avoid":
                safe_foods.append({"food_data": f, "tag": result.overall_tag})

    # 应用反馈调整
    adjusted = get_feedback_adjusted_foods(safe_foods, feedback_store, kb=kb)
    feedback_name = str(profile.get("feedback_food_name") or "").strip().lower()
    feedback_reaction = str(profile.get("feedback_reaction") or "").strip().lower()
    if feedback_name and feedback_reaction not in {"", "none", "unknown"}:
        adjusted = [
            item for item in adjusted
            if feedback_name not in {
                str(item["food_data"].get("name_zh") or "").strip().lower(),
                str(item["food_data"].get("name_en") or "").strip().lower(),
                str(item["food_data"].get("id") or "").strip().lower(),
            }
        ]
    filtered = [f for f in adjusted if f.get("tag") == "suitable"]

    result = plan_agent.process({
        "profile": profile,
        "safe_foods": filtered,
        "stage": stage,
        "use_llm": bool(req.candidates),  # 评测模式开 LLM
    })

    # 二次校验：规则引擎重新验证计划
    from agents.validation import ValidationAgent
    validator = ValidationAgent(kb=kb, rule_engine=engine)
    validation = validator.process({"plan": result["plan"], "profile": profile})

    return {
        "plan": result["plan"],
        "new_foods_this_week": result["new_foods_this_week"],
        "stage_label": result["stage_label"],
        "nutrition_notes": result["nutrition_notes"],
        "validated": validation["passed"],
        "validation_warnings": validation.get("warnings", []),
        "validation_violations": validation.get("violations", []),
    }


# ---------- 配料解析 ----------

@app.post("/api/parse-label")
def parse_label(req: LabelRequest):
    """解析商品配料表"""
    result = label_agent.process({
        "ingredient_text": req.ingredient_text,
        "age_months": req.age_months,
    })
    return result


# ---------- 智能问答 ----------

@app.post("/api/chat")
def chat(req: ChatRequest):
    """智能问答"""
    result = chat_agent.process({
        "message": req.message,
        "history": req.history,
    })
    return result


# ---------- 知识库查询 ----------

@app.get("/api/foods")
def list_foods(age: Optional[int] = None, category: Optional[str] = None):
    """查询食材列表"""
    if age:
        foods = kb.list_foods_by_age(age)
    elif category:
        foods = kb.list_foods_by_category(category)
    else:
        foods = kb.list_all_foods()
    return {"foods": foods, "count": len(foods)}


@app.get("/api/allergens")
def list_allergens():
    return {"allergens": kb.list_allergens()}


# ---------- 用户反馈 ----------

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    """提交宝宝食物反馈"""
    record = feedback_store.add(
        food_name=req.food_name,
        reaction=req.reaction,
        severity=req.severity,
        notes=req.notes,
    )
    return {"record": record, "summary": feedback_store.summary}


@app.get("/api/feedback")
def get_feedback():
    """获取反馈汇总"""
    return feedback_store.summary


@app.delete("/api/feedback")
def clear_feedback():
    """清除所有反馈"""
    for r in list(feedback_store.get_all()):
        feedback_store.delete(r["id"])
    return {"status": "cleared"}


# ================================================================
# LLM 设置（热重载）
# ================================================================

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "llm_settings.json"


def _load_llm_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            import json as _json
            return _json.loads(open(SETTINGS_PATH, encoding="utf-8").read())
        except Exception:
            pass
    return {}


def _save_llm_settings(settings: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        _json.dump(settings, f, ensure_ascii=False, indent=2)


def _reload_llm(api_key: str, base_url: str, model: str):
    """热重载 LLM：更新全局 llm 实例和所有已初始化的 Agent"""
    global llm, safety_agent, plan_agent, label_agent, chat_agent
    from llm.openai_adapter import OpenAIAdapter
    new_llm = OpenAIAdapter(api_key=api_key, base_url=base_url, model=model)
    llm = new_llm
    safety_agent._llm = new_llm
    plan_agent.llm = new_llm
    label_agent.llm = new_llm
    chat_agent.llm = new_llm
    return new_llm


@app.get("/api/settings/llm")
def get_llm_settings():
    """获取当前 LLM 配置（API Key 脱敏）"""
    saved = _load_llm_settings()
    api_key = saved.get("api_key", llm.api_key if hasattr(llm, "api_key") else "")
    # 脱敏：只显示前4后4
    masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"
    return {
        "api_key": api_key,
        "api_key_masked": masked,
        "base_url": saved.get("base_url", llm.base_url if hasattr(llm, "base_url") else ""),
        "model": saved.get("model", llm.model if hasattr(llm, "model") else ""),
    }


class LLMSettingsRequest(BaseModel):
    api_key: str
    base_url: str
    model: str


@app.post("/api/settings/llm")
def update_llm_settings(req: LLMSettingsRequest):
    """更新 LLM 配置并热重载"""
    try:
        # 保存到文件
        settings = {
            "api_key": req.api_key,
            "base_url": req.base_url,
            "model": req.model,
        }
        _save_llm_settings(settings)

        # 热重载
        _reload_llm(req.api_key, req.base_url, req.model)

        return {
            "status": "ok",
            "message": f"LLM 配置已更新，当前模型：{req.model}",
            "model": req.model,
            "base_url": req.base_url,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"配置更新失败：{str(e)}")


# ================================================================
# 启动
# ================================================================

if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
