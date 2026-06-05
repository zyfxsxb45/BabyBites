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
safety_agent = SafetyBoundaryAgent(kb=kb, rule_engine=engine)
plan_agent = PlanGenerationAgent(kb=kb, llm=llm)
label_agent = LabelParsingAgent(kb=kb, llm=llm)
chat_agent = ChatAgent(kb=kb, llm=llm)
feedback_store = FeedbackStore()
print("✅ 初始化完成")

app = FastAPI(title="宝宝巴适 BabyBites API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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


class AssessRequest(BaseModel):
    profile: BabyProfile


class PlanRequest(BaseModel):
    profile: BabyProfile


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
    }


# ---------- 周度计划 ----------

@app.post("/api/plan")
def generate_plan(req: PlanRequest):
    """生成一周辅食计划"""
    profile = req.profile.model_dump()
    stage = kb.get_age_stage(profile["age_months"])

    # 安全食材池
    all_foods = kb.list_foods_by_age(profile["age_months"])
    safe_foods = []
    for f in all_foods:
        result = engine.evaluate_food(f, profile)
        if result.overall_tag != "avoid":
            safe_foods.append({"food_data": f, "tag": result.overall_tag})

    # 应用反馈调整
    adjusted = get_feedback_adjusted_foods(safe_foods, feedback_store, kb=kb)
    filtered = [f for f in adjusted if f.get("tag") != "avoid"]

    result = plan_agent.process({
        "profile": profile,
        "safe_foods": filtered,
        "stage": stage,
    })

    return {
        "plan": result["plan"],
        "new_foods_this_week": result["new_foods_this_week"],
        "stage_label": result["stage_label"],
        "nutrition_notes": result["nutrition_notes"],
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
# 启动
# ================================================================

if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
