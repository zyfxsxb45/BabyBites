"""
宝宝巴适 BabyBites — Streamlit 主入口

启动方式：
    streamlit run ui/app.py
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.loader import init_kb, init_llm
from utils.format import safe_tag_emoji

# ===== 全局初始化（只执行一次）=====

if "kb" not in st.session_state:
    st.session_state.kb = init_kb()

if "llm" not in st.session_state:
    st.session_state.llm = init_llm()

if "rag" not in st.session_state:
    from kb.rag import RAGRetriever
    st.session_state.rag = RAGRetriever()

if "chat_agent" not in st.session_state:
    from agents.chat import ChatAgent
    st.session_state.chat_agent = ChatAgent(
        kb=st.session_state.kb,
        llm=st.session_state.llm,
        rag=st.session_state.rag,
    )

if "safety_agent" not in st.session_state:
    from agents.safety_boundary import SafetyBoundaryAgent
    from rules.engine import RuleEngine
    engine = RuleEngine(st.session_state.kb)
    st.session_state.safety_agent = SafetyBoundaryAgent(kb=st.session_state.kb, rule_engine=engine, llm=st.session_state.llm)

if "plan_agent" not in st.session_state:
    from agents.plan_generation import PlanGenerationAgent
    st.session_state.plan_agent = PlanGenerationAgent(kb=st.session_state.kb, llm=st.session_state.llm)

if "label_agent" not in st.session_state:
    from agents.label_parsing import LabelParsingAgent
    st.session_state.label_agent = LabelParsingAgent(kb=st.session_state.kb, llm=st.session_state.llm)

if "feedback_store" not in st.session_state:
    from data.feedback_store import FeedbackStore
    st.session_state.feedback_store = FeedbackStore()

if "feedback_history" not in st.session_state:
    st.session_state.feedback_history = []

# ===== 帮助函数 =====

def tag_badge(tag):
    """标签 → 彩色徽章"""
    colors = {"suitable": "green", "caution": "orange", "avoid": "red", "unknown": "grey"}
    labels = {"suitable": "✅ 安全", "caution": "⚠️ 注意", "avoid": "🚫 避免", "unknown": "❓ 未知"}
    color = colors.get(tag, "grey")
    label = labels.get(tag, tag)
    return f"<span style='background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.85em'>{label}</span>"


# ===== 页面配置 =====

st.set_page_config(
    page_title="宝宝巴适 BabyBites",
    page_icon="🍼",
    layout="wide",
)

st.title("🍼 宝宝巴适 BabyBites")
st.caption("AI 辅助 6–12 月龄婴儿辅食推荐与过敏预警系统")

# ===== 侧边栏：宝宝信息录入 =====

with st.sidebar:
    st.header("👶 宝宝信息")

    age_months = st.number_input("月龄", min_value=0, max_value=36, value=6)
    corrected_age = st.number_input("矫正月龄（早产儿需填）", min_value=0, max_value=36, value=0)
    feeding_method_raw = st.selectbox("喂养方式", ["纯母乳", "配方奶", "混合喂养"])
    allergies_raw = st.multiselect(
        "已知过敏原",
        ["鸡蛋", "牛奶", "花生", "鱼类", "虾", "大豆", "小麦", "坚果", "芝麻"],
    )
    # 自定义过敏原输入（支持日常口语，LLM自动解析）
    custom_allergen = st.text_input(
        "➕ 其他过敏/忌口（如：海鲜、面食、发物…）",
        placeholder="输入后回车 → LLM自动匹配",
        key="custom_allergen_input",
    )
    if custom_allergen:
        resolved = st.session_state.kb.resolve_allergen_query(
            custom_allergen, llm=st.session_state.llm
        )
        if resolved:
            names = []
            for aid in resolved:
                for aname, a in st.session_state.kb._allergens.items():
                    if not aname.startswith("_") and a.get("id") == aid:
                        names.append(aname)
                        break
            if names:
                st.caption(f"💡 「{custom_allergen}」已匹配：{'、'.join(names)}")
                # 自动合并到 allergies_raw
                allergies_raw = list(set(allergies_raw + names))
        else:
            st.caption(f"❓ 「{custom_allergen}」未能匹配到已知过敏原，已忽略")
    tried_foods_raw = st.multiselect(
        "已尝试食材",
        ["大米粉", "小米", "燕麦", "玉米",
         "猪肝", "鸡肝", "牛肉", "猪肉(瘦)", "鸡肉", "鸭肉",
         "三文鱼", "鳕鱼", "带鱼", "虾仁",
         "鸡蛋", "豆腐",
         "胡萝卜", "南瓜", "紫薯", "山药", "土豆",
         "菠菜", "西兰花", "花椰菜", "油菜", "番茄", "冬瓜", "豌豆",
         "苹果", "香蕉", "梨", "牛油果", "蓝莓", "草莓", "橙子", "木瓜",
         "酸奶", "奶酪", "核桃", "芝麻粉"],
    )
    notes = st.text_area("备注（发育信号等）", placeholder="如：宝宝能坐稳了，看我们吃饭会伸手…", height=80)

    # 构建宝宝画像
    feeding_map = {"纯母乳": "breast", "配方奶": "formula", "混合喂养": "mixed"}
    baby_profile = {
        "age_months": age_months,
        "corrected_age_months": corrected_age if corrected_age > 0 else None,
        "allergies": allergies_raw,
        "feeding_method": feeding_map.get(feeding_method_raw, "breast"),
        "tried_foods": tried_foods_raw,
        "notes": notes,
    }

    st.divider()
    assess_btn = st.button("🔍 开始评估", type="primary", use_container_width=True)

    # 存进 session_state 供其他 Tab 用
    st.session_state.baby_profile = baby_profile

# ===== 主区域：四 Tab =====

tab1, tab2, tab3, tab4 = st.tabs([
    "📋 安全评估",
    "📅 周度计划",
    "🔍 配料解析",
    "💬 智能问答",
])


# ================================================================
# Tab 1: 安全评估
# ================================================================
with tab1:
    if not assess_btn and "assessment_result" not in st.session_state:
        st.info("👈 在左侧填入宝宝信息后点击「开始评估」")
    else:
        if assess_btn or "assessment_result" not in st.session_state:
            with st.spinner("正在评估..."):
                # 获取所有适龄食材
                all_foods = st.session_state.kb.list_foods_by_age(age_months)
                candidate_foods = [{"food_data": f} for f in all_foods]

                result = st.session_state.safety_agent.process({
                    "profile": baby_profile,
                    "candidate_foods": candidate_foods,
                })
                st.session_state.assessment_result = result

        result = st.session_state.assessment_result

        # ---- 阶段判断 ----
        st.subheader("📊 阶段判断")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            emoji = "✅" if result["can_start"] else "🚫"
            st.metric("可开始辅食", emoji)
        with col2:
            stage = result.get("stage") or {}
            st.metric("当前阶段", stage.get("label", "—"))
        with col3:
            st.metric("矫正月龄", f"{result.get('effective_age_months', age_months)}个月")
        with col4:
            signals = result.get("readiness_signals", [])
            st.metric("就绪信号", f"{len(signals)}个")

        if result.get("recommendation"):
            if result["can_start"]:
                st.success(result["recommendation"])
            else:
                st.warning(result["recommendation"])

        # ---- 阻止原因 ----
        if result.get("blocking_reasons"):
            st.error("##### ⚠️ 以下原因阻止辅食添加：")
            for r in result["blocking_reasons"]:
                st.markdown(f"- {r}")

        # ---- 发育信号 ----
        if signals:
            with st.expander(f"📝 检测到 {len(signals)} 个发育就绪信号"):
                for s in signals:
                    st.markdown(f"- {s['label']}（关键词：{s['keyword']}）")

        # ---- 食材安全标签 ----
        food_results = result.get("food_safety_results", {})
        if food_results:
            st.subheader("🍽️ 食材安全标签")
            avoid_list = []
            caution_list = []
            suitable_list = []

            for fid, fr in food_results.items():
                tag = fr.get("tag", "unknown")
                display_name = fid
                food = st.session_state.kb.get_food(fid) or st.session_state.kb.get_food_by_name(fid)
                if food:
                    display_name = food.get("name_zh", fid)
                    # 高敏食材即使规则判 suitable，也升到 caution
                    if food.get("potential_allergen") and tag == "suitable":
                        tag = "caution"
                        fr["reasons"] = fr.get("reasons", []) + ["常见过敏原，首次引入需观察"]
                if tag == "avoid":
                    avoid_list.append((display_name, fr))
                elif tag == "caution":
                    caution_list.append((display_name, fr))
                elif food and food.get("iron_rich"):
                    recommended.append((display_name, fr))
                else:
                    later_list.append((display_name, fr))

            if avoid_list:
                st.error(f"🚫 必须避免 ({len(avoid_list)}种)：")
                for fid, fr in avoid_list:
                    reasons = "；".join(fr.get("reasons", []))
                    st.markdown(f"- **{fid}**：{reasons}")

            if caution_list:
                st.warning(f"⚠️ 需要注意 ({len(caution_list)}种)：")
                for fid, fr in caution_list[:5]:
                    reasons = "；".join(fr.get("reasons", []))
                    st.markdown(f"- **{fid}**：{reasons}")
                if len(caution_list) > 5:
                    st.caption(f"...还有 {len(caution_list) - 5} 种")

            if recommended:
                with st.expander(f"⭐ 优先推荐 ({len(recommended)}种) — 高铁、高营养、适合首尝"):
                    cols = st.columns(4)
                    for i, (fid, _) in enumerate(recommended):
                        with cols[i % 4]:
                            st.markdown(f"- {fid}")

            if later_list:
                with st.expander(f"🔜 可后续添加 ({len(later_list)}种) — 首轮辅食之后逐步引入"):
                    cols = st.columns(4)
                    for i, (fid, _) in enumerate(later_list):
                        with cols[i % 4]:
                            st.markdown(f"- {fid}")


# ================================================================
# Tab 2: 周度计划
# ================================================================
with tab2:
    st.subheader("📅 周度辅食计划")

    # 需要有评估结果
    if "assessment_result" not in st.session_state:
        st.info("👈 请先在「安全评估」Tab 点击「开始评估」")
    elif not st.session_state.assessment_result.get("can_start"):
        st.warning("宝宝暂不具备辅食添加条件，无法生成计划。")
    else:
        result = st.session_state.assessment_result
        food_results = result.get("food_safety_results", {})

        # 构建安全食材池
        safe_foods = []
        for fid, fr in food_results.items():
            if fr.get("tag") != "avoid":
                food_data = st.session_state.kb.get_food(fid) or st.session_state.kb.get_food_by_name(fid)
                if food_data:
                    safe_foods.append({"food_data": food_data, "tag": fr.get("tag", "suitable")})

        # 分开已尝试和推荐新食材
        tried_names = set(tried_foods_raw) if tried_foods_raw else set()
        tried_pool = [f for f in safe_foods if f["food_data"].get("name_zh") in tried_names]
        new_pool = [f for f in safe_foods if f["food_data"].get("name_zh") not in tried_names]

        # 新食材优先推荐高铁+该阶段关键品类
        stage_for_rank = st.session_state.kb.get_age_stage(age_months)
        key_nutrients = stage_for_rank.get("key_nutrients", ["铁"]) if stage_for_rank else ["铁"]
        def new_food_score(item):
            fd = item["food_data"]
            s = 0
            if fd.get("iron_rich"): s += 3
            for n in key_nutrients:
                if n in (fd.get("nutrients") or {}): s += 1
            return s
        new_pool.sort(key=new_food_score, reverse=True)
        recommended_new = new_pool[:5]

        # 合并：已尝试 + 推荐新食材
        plan_foods = tried_pool + recommended_new

        st.caption(f"已尝试 {len(tried_pool)} 种 + 推荐新食材 {len(recommended_new)} 种 = 共 {len(plan_foods)} 种可选")
        if len(plan_foods) < 3:
            st.info("💡 请先在侧边栏「已尝试食材」中选择更多宝宝吃过的食物")

        gen_btn = st.button("🔄 生成/刷新周计划", type="primary")

        if gen_btn or "weekly_plan" not in st.session_state:
            with st.spinner("正在生成一周计划..."):
                try:
                    from rules.feedback import get_feedback_adjusted_foods
                    adjusted = get_feedback_adjusted_foods(
                        plan_foods, st.session_state.feedback_store, kb=st.session_state.kb
                    )
                    filtered = [f for f in adjusted if f.get("tag") != "avoid"]

                    stage = st.session_state.kb.get_age_stage(age_months)
                    plan_result = st.session_state.plan_agent.process({
                        "profile": baby_profile,
                        "safe_foods": filtered if filtered else plan_foods,
                        "stage": stage,
                    })
                    st.session_state.weekly_plan = plan_result
                except Exception as e:
                    st.error(f"生成计划失败: {e}")
                    import traceback
                    st.code(traceback.format_exc())
                    st.session_state.weekly_plan = {"plan": [], "new_foods_this_week": [], "nutrition_notes": []}

        plan_result = st.session_state.weekly_plan
        plan = plan_result.get("plan", [])

        if plan:
            # 新食材提示
            new_foods = plan_result.get("new_foods_this_week", [])
            if new_foods:
                st.info(f"🆕 本周引入新食材：{'、'.join(new_foods)}。每次一种，观察3-5天。")

            # 周历视图
            cols = st.columns(7)
            day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

            for i, day_data in enumerate(plan):
                with cols[i]:
                    day_label = day_data.get("day", day_names[i])
                    foods = day_data.get("foods", [])
                    is_new = day_data.get("is_new_food", False)

                    # 背景色
                    bg = "#FFF3CD" if is_new else "#E8F5E9"
                    st.markdown(
                        f"""<div style='background:{bg};padding:8px;border-radius:6px;min-height:100px;color:#1a1a1a'>
                        <b>{day_label}</b>{' 🆕' if is_new else ''}<br>
                        {'<br>'.join(foods) if foods else '—'}
                        </div>""",
                        unsafe_allow_html=True,
                    )

            # 营养建议
            notes = plan_result.get("nutrition_notes", [])
            if notes:
                st.markdown("---")
                for n in notes:
                    if n.startswith("✅"):
                        st.success(n)
                    elif n.startswith("⚠️"):
                        st.warning(n)
                    elif n.startswith("💡"):
                        st.info(n)

            st.caption(plan_result.get("stage_label", ""))

        # ---- 反馈区域 ----
        if plan:
            st.markdown("---")
            with st.expander("📝 宝宝反馈（记录吃新食物后的反应）", expanded=False):
                all_plan_foods = []
                for d in plan:
                    for f in d.get("foods", []):
                        if f not in all_plan_foods:
                            all_plan_foods.append(f)

                if all_plan_foods:
                    plan_key = str(hash(str(plan)))[:6]
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        fb_food = st.selectbox("食材", all_plan_foods, key=f"fb_food_{plan_key}")
                    with col2:
                        fb_reaction = st.selectbox(
                            "反应",
                            ["没问题", "轻微皮疹", "腹泻", "呕吐", "拒绝吃", "其他不适"],
                            key=f"fb_reaction_{plan_key}",
                        )
                    with col3:
                        fb_severity = st.selectbox(
                            "严重程度",
                            ["mild", "moderate", "severe"],
                            format_func=lambda x: {"mild": "轻微", "moderate": "中度", "severe": "严重"}[x],
                            key=f"fb_severity_{plan_key}",
                        )

                    fb_notes = st.text_input("备注（可选）", placeholder="如：吃完2小时后脸上出红点", key=f"fb_notes_{plan_key}")

                    if st.button("📩 提交反馈", type="primary", key=f"fb_submit_{plan_key}"):
                        reaction_map = {
                            "没问题": "none", "轻微皮疹": "rash", "腹泻": "diarrhea",
                            "呕吐": "vomiting", "拒绝吃": "refusal", "其他不适": "other",
                        }
                        st.session_state.feedback_store.add(
                            food_name=fb_food,
                            reaction=reaction_map.get(fb_reaction, "other"),
                            severity=fb_severity,
                            notes=fb_notes,
                        )
                        st.success(f"已记录「{fb_food}」的反馈")
                        st.rerun()

        # ---- 反馈历史 ----
        summary = st.session_state.feedback_store.summary
        if summary["total"] > 0:
            with st.expander(f"📋 反馈历史（{summary['total']}条记录，覆盖{summary['foods_tracked']}种食材）"):
                if summary["avoid_foods"]:
                    st.error(f"🚫 已标记避免：{'、'.join(summary['avoid_foods'])}")
                if summary["caution_foods"]:
                    st.warning(f"⚠️ 已标记注意：{'、'.join(summary['caution_foods'])}")

                records = st.session_state.feedback_store.get_all()
                for r in reversed(records[-10:]):
                    icon = {"none": "✅", "rash": "🔴", "diarrhea": "🟠", "vomiting": "🟠", "refusal": "🟡", "other": "⚪"}
                    sev = {"mild": "轻", "moderate": "中", "severe": "重"}
                    rx_label = {"none": "没问题", "rash": "皮疹", "diarrhea": "腹泻", "vomiting": "呕吐", "refusal": "拒绝", "other": "不适"}
                    icon_str = icon.get(r.get("reaction", ""), "")
                    sev_str = sev.get(r.get("severity", ""), "")
                    rx_str = rx_label.get(r.get("reaction", ""), r.get("reaction", ""))
                    st.caption(
                        f"{icon_str} {r.get('date', '')} | "
                        f"**{r.get('food_name', '')}**: {rx_str} ({sev_str})"
                        f"{' — ' + r.get('notes', '') if r.get('notes') else ''}"
                    )

                if st.button("🗑️ 清除所有反馈", key="fb_clear_all"):
                    for r in list(st.session_state.feedback_store.get_all()):
                        st.session_state.feedback_store.delete(r["id"])
                    st.session_state.feedback_history = []
                    st.rerun()


# ================================================================
# Tab 3: 配料解析
# ================================================================
with tab3:
    st.subheader("🔍 配料表解析")
    st.caption("粘贴商品配料表，自动识别过敏原、添加糖和风险成分")

    ingredient_text = st.text_area(
        "配料表",
        placeholder="示例：大米(85%)、乳清蛋白、白砂糖、柠檬酸(330)、碳酸钙",
        height=100,
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        parse_age = st.number_input("适用月龄", value=age_months, min_value=0, max_value=36)
    with col2:
        parse_btn = st.button("🔬 解析配料", type="primary")

    if parse_btn and ingredient_text.strip():
        with st.spinner("解析中..."):
            result = st.session_state.label_agent.process({
                "ingredient_text": ingredient_text,
                "age_months": parse_age,
            })

        parsed = result.get("parsed", [])
        risk = result.get("risk_summary", {})

        # 汇总统计
        st.markdown(f"共识别 **{result.get('total_count', 0)}** 种成分，"
                    f"匹配 **{result.get('matched_count', 0)}** 种")

        # 风险摘要
        if risk.get("has_avoid"):
            st.error("🚫 含有需避免的成分")
        if risk.get("allergens"):
            st.warning(f"⚠️ 识别到过敏原：{'、'.join(risk['allergens'])}")
        if risk.get("added_sugars"):
            st.warning(f"⚠️ 识别到添加糖：{'、'.join(risk['added_sugars'])}")
        if risk.get("unknown"):
            st.info(f"❓ 未收录成分 ({len(risk['unknown'])}种)：{'、'.join(risk['unknown'][:5])}")

        # 逐项显示
        if parsed:
            st.markdown("---")
            st.markdown("##### 成分明细")

            for entry in parsed:
                name = entry["raw_name"]
                tags = entry.get("tags", [])
                matched = entry.get("matched", False)
                ingredient = entry.get("ingredient") or {}

                # 确定颜色和标签
                worst_tag = "suitable"
                for t in tags:
                    if t.get("tag") == "avoid":
                        worst_tag = "avoid"
                        break
                    elif t.get("tag") == "caution":
                        worst_tag = "caution"

                color_map = {"avoid": "red", "caution": "orange", "suitable": "green", "unknown": "grey"}
                color = color_map.get(worst_tag, "grey")

                col1, col2 = st.columns([1, 4])
                with col1:
                    st.markdown(
                        f"<span style='color:{color};font-weight:bold;font-size:1.1em'>{name}</span>",
                        unsafe_allow_html=True,
                    )
                    if matched:
                        cat = ingredient.get("category", "")
                        ins = ingredient.get("ins_code", "")
                        extra = []
                        if cat:
                            extra.append(cat)
                        if ins:
                            extra.append(f"INS {ins}")
                        if extra:
                            st.caption(" · ".join(extra))

                with col2:
                    for t in tags:
                        tag = t.get("tag", "unknown")
                        reason = t.get("reason", "")
                        rule = t.get("rule", "")
                        icon = {"avoid": "🚫", "caution": "⚠️", "suitable": "✅", "unknown": "❓"}.get(tag, "")
                        st.markdown(f"{icon} {reason} &nbsp;<small style='color:grey'>({rule})</small>",
                                    unsafe_allow_html=True)


# ================================================================
# Tab 4: 智能问答
# ================================================================
with tab4:
    from ui.pages.chat import render_chat_page

    st.caption("💡 也可以点击右下角的 Boss Baby 悬浮球打开问答窗口~")

    # 如果有宝宝画像，注入背景信息
    if baby_profile.get("age_months", 0) > 0:
        st.caption(
            f"当前宝宝：{baby_profile.get('age_months', '?')}月龄"
            + (f"，过敏：{'、'.join(baby_profile.get('allergies', []))}" if baby_profile.get("allergies") else "")
            + (f"，已尝试：{len(baby_profile.get('tried_foods', []))}种" if baby_profile.get("tried_foods") else "")
        )

    render_chat_page(st.session_state.chat_agent, kb=st.session_state.kb)


# ===== Boss Baby 悬浮球 + 智能问答浮窗 =====
from ui.components.chat_float import render_chat_float
render_chat_float(st.session_state.chat_agent, kb=st.session_state.kb)


# ===== 底部 =====
st.divider()
st.caption("© 2026 宝宝巴适 · 清华大学《人工智能导论》课程大作业")
