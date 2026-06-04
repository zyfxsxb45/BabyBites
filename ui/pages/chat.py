"""
Chat 智能问答页面。

嵌入到 app.py 的 Tab 中，提供自由对话界面。
"""

import streamlit as st


def render_chat_page(chat_agent, kb=None):
    """
    渲染 Chat 问答页面。

    Args:
        chat_agent: ChatAgent 实例
        kb: 知识库实例（用于查询）
    """
    st.subheader("💬 智能问答")

    # 快捷提问按钮
    st.caption("快捷提问：")
    quick_questions = [
        "6月龄宝宝可以吃哪些食物？",
        "猪肝含铁量多少？什么时候可以吃？",
        "鸡蛋过敏有什么要注意的？",
        "辅食应该怎么循序渐进？",
    ]
    cols = st.columns(4)
    clicked = None
    for i, q in enumerate(quick_questions):
        with cols[i]:
            if st.button(q, key=f"quick_{i}", use_container_width=True):
                clicked = q

    st.divider()

    # 初始化会话历史
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 显示对话历史
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📚 信息来源"):
                    for s in msg["sources"]:
                        st.caption(f"· {s}")

    # 输入框
    user_input = st.chat_input("关于宝宝辅食的问题，随时问我...")

    # 处理快捷提问
    if clicked:
        user_input = clicked

    if user_input:
        # 显示用户消息
        with st.chat_message("user"):
            st.markdown(user_input)

        # 调用 Chat Agent
        with st.spinner("思考中..."):
            result = chat_agent.process({
                "message": user_input,
                "history": [
                    {"question": h["content"], "answer": h.get("answer", "")}
                    for h in st.session_state.chat_history
                    if h["role"] == "assistant"
                ],
            })

        answer = result.get("answer") or "抱歉，我暂时无法回答这个问题。"
        sources = result.get("sources", [])

        # 显示助手回答
        with st.chat_message("assistant"):
            st.markdown(answer)
            if sources:
                with st.expander("📚 信息来源"):
                    for s in sources:
                        st.caption(f"· {s}")

        # 保存历史
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

    # 清除历史按钮
    if st.session_state.chat_history:
        st.divider()
        if st.button("🗑️ 清除对话历史", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
