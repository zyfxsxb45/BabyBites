"""
宝宝巴适 BabyBites — Streamlit 主入口

启动方式：
    streamlit run ui/app.py
"""

import streamlit as st
import sys
from pathlib import Path

# 把项目根目录加入 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.loader import init_kb, init_llm

# ===== 全局初始化（只执行一次）=====

if "kb" not in st.session_state:
    st.session_state.kb = init_kb()

if "llm" not in st.session_state:
    st.session_state.llm = init_llm()

if "chat_agent" not in st.session_state:
    from agents.chat import ChatAgent
    st.session_state.chat_agent = ChatAgent(
        kb=st.session_state.kb,
        llm=st.session_state.llm,
    )

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
    feeding_method = st.selectbox("喂养方式", ["纯母乳", "配方奶", "混合喂养"])
    allergies = st.multiselect(
        "已知过敏原",
        ["鸡蛋", "牛奶", "花生", "鱼类", "大豆", "小麦", "坚果", "芝麻"],
    )
    tried_foods = st.multiselect(
        "已尝试食材",
        ["胡萝卜", "南瓜", "土豆", "菠菜", "苹果", "香蕉", "猪肝", "三文鱼", "鸡蛋", "豆腐"],
    )

    st.divider()
    st.button("🔍 开始评估", type="primary", use_container_width=True)

# ===== 主区域：四 Tab =====

tab1, tab2, tab3, tab4 = st.tabs([
    "📋 安全评估",
    "📅 周度计划",
    "🔍 配料解析",
    "💬 智能问答",
])

with tab1:
    st.info('输入宝宝信息后点击「开始评估」，查看阶段判断和安全标签')
    st.subheader("评估结果")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("月龄", f"{age_months}个月", delta="")
    with col2:
        st.metric("辅食阶段", "待评估", delta="")
    with col3:
        st.metric("安全状态", "待评估", delta="")

with tab2:
    st.info('功能开发中：生成的周计划将以周历形式展示')

with tab3:
    st.info('功能开发中：粘贴商品配料表，自动识别过敏原和风险成分')
    ingredient_input = st.text_area(
        "粘贴配料表",
        placeholder='示例：大米(85%)、乳清蛋白、白砂糖、柠檬酸(330)、碳酸钙',
        disabled=True,
    )

with tab4:
    from ui.pages.chat import render_chat_page
    render_chat_page(st.session_state.chat_agent, kb=st.session_state.kb)

# ===== 底部 =====

st.divider()
st.caption("© 2026 宝宝巴适 · 清华大学《人工智能导论》课程大作业")
