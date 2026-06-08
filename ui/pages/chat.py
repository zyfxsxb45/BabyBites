"""
Chat 智能问答页面。

嵌入到 app.py 的 Tab 中，提供自由对话界面。
"""

import streamlit as st


def _agent_history(messages):
    history = []
    pending_question = None
    for message in messages:
        if message.get("role") == "user":
            pending_question = message.get("content", "")
        elif message.get("role") == "assistant" and pending_question:
            history.append({
                "question": pending_question,
                "answer": message.get("content", ""),
            })
            pending_question = None
    return history[-5:]


def render_chat_page(chat_agent, kb=None):
    """
    渲染 Chat 问答页面。

    Args:
        chat_agent: ChatAgent 实例
        kb: 知识库实例（用于查询）
    """
    st.subheader("💬 智能问答")
    st.caption("结合当前宝宝画像、知识库和安全规则回答辅食问题。")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    quick_questions = [
        "6月龄宝宝可以吃哪些食物？",
        "猪肝含铁量多少？什么时候可以吃？",
        "鸡蛋过敏有什么要注意的？",
        "辅食应该怎么循序渐进？",
    ]
    clicked = None
    with st.container(border=True):
        st.caption("快捷提问")
        cols = st.columns(2)
        for i, question in enumerate(quick_questions):
            with cols[i % 2]:
                if st.button(question, key=f"quick_{i}", use_container_width=True):
                    clicked = question

        st.divider()
        if not st.session_state.chat_history:
            st.info("输入问题后，回答会显示在这里。")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("sources"):
                    with st.expander("📚 信息来源"):
                        for source in msg["sources"]:
                            st.caption(f"· {source}")

        with st.form("chat_page_form", clear_on_submit=True):
            typed_input = st.text_input(
                "输入问题",
                placeholder="例如：8月龄宝宝第一次吃鸡蛋应该注意什么？",
                key="chat_page_input",
            )
            send_clicked = st.form_submit_button(
                "发送",
                type="primary",
                use_container_width=True,
            )
        user_input = clicked or (typed_input.strip() if send_clicked else None)

    if user_input:
        with st.spinner("思考中..."):
            result = chat_agent.process({
                "message": user_input,
                "history": _agent_history(st.session_state.chat_history),
                "current_profile": st.session_state.get("baby_profile", {}),
            })

        answer = result.get("answer") or "抱歉，我暂时无法回答这个问题。"
        sources = result.get("sources", [])

        # 合并 Chat 提取的 profile 增量
        insights = result.get("profile_insights", {})
        if insights:
            bp = st.session_state.get("baby_profile", {})
            changed = []
            if "allergies" in insights:
                bp["allergies"] = insights["allergies"]
                changed.append(f"过敏原→{insights['allergies']}")
            if "tried_foods" in insights:
                bp["tried_foods"] = insights["tried_foods"]
                changed.append(f"已尝试→新增{len(insights['tried_foods'])}种")
            if "age_months" in insights:
                bp["age_months"] = insights["age_months"]
                changed.append(f"月龄→{insights['age_months']}月")
            st.session_state.baby_profile = bp
            if changed:
                st.caption(f"💡 已自动更新宝宝信息：{' · '.join(changed)}")

        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
        })
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "answer": answer,
        })
        st.rerun()

    if st.session_state.chat_history:
        if st.button("🗑️ 清除对话历史", use_container_width=True, key="chat_page_clear"):
            st.session_state.chat_history = []
            st.rerun()
