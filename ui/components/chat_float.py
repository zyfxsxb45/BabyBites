"""
Boss Baby 悬浮球 + 智能问答浮窗组件。

在页面右下角渲染一个 CSS 绘制的 Boss Baby 头像球，
点击后展开智能问答浮窗面板。

实现方式：球体用 st.markdown 渲染在页面 DOM 中（position:fixed），
点击通过 <a> 标签 + query_params 触发。
"""

import streamlit as st
from agents.chat import ChatAgent
from ui.pages.chat import _agent_history


# ================================================================
# CSS
# ================================================================

BALL_CSS = """<style>
/* === Boss Baby 悬浮球 === */
#boss-baby-float {
    position: fixed;
    bottom: 28px;
    right: 28px;
    z-index: 99998;
}

/* 提示气泡 */
#bb-tooltip {
    position: fixed;
    bottom: 118px;
    right: 28px;
    background: #fff;
    color: #555;
    font-size: 13px;
    padding: 8px 15px;
    border-radius: 16px;
    white-space: nowrap;
    box-shadow: 0 2px 14px rgba(0,0,0,0.10);
    z-index: 99999;
    opacity: 0;
    transition: opacity 0.5s;
    pointer-events: none;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
}

/* 球体 */
.bb-ball {
    width: 80px; height: 80px;
    border-radius: 50%;
    position: relative;
    background: linear-gradient(180deg,
        #f5d78c 0%, #f5d78c 18%,
        #ffe4c4 18%, #ffe4c4 100%
    );
    box-shadow:
        0 4px 18px rgba(0,0,0,0.15),
        0 0 0 3px #fff;
    cursor: pointer;
    transition: transform 0.2s, box-shadow 0.2s;
    animation: bb-bounce 2.5s ease-in-out infinite;
    display: block;
    text-decoration: none;
}
.bb-ball:hover {
    transform: scale(1.08);
    box-shadow:
        0 6px 24px rgba(0,0,0,0.22),
        0 0 0 3.5px #ffe0b2;
}
.bb-ball:active { transform: scale(0.95); }
@keyframes bb-bounce {
    0%, 100% { transform: translateY(0); }
    15%      { transform: translateY(-8px); }
    30%      { transform: translateY(0); }
    45%      { transform: translateY(-4px); }
    60%      { transform: translateY(0); }
}

/* hair */
.bb-ball .h-front {
    position: absolute; top: -1px; left: 10px;
    width: 55px; height: 20px;
    background: #e8c44a;
    border-radius: 50% 55% 22% 18% / 80% 65% 15% 10%;
    z-index: 3;
}
.bb-ball .h-swoop {
    position: absolute; top: 9px; right: 14px;
    width: 28px; height: 13px;
    background: #e8c44a;
    border-radius: 0 75% 50% 0 / 0 75% 35% 0;
    transform: rotate(-12deg);
    z-index: 3;
}

/* eyes */
.bb-ball .eye {
    position: absolute; top: 26px;
    width: 15px; height: 17px;
    background: #fff; border-radius: 50%;
    z-index: 4;
}
.bb-ball .eye.l { left: 15px; } .bb-ball .eye.r { right: 15px; }

/* brows */
.bb-ball .brow {
    position: absolute; top: 22px;
    width: 18px; height: 3px;
    background: #c4944a; border-radius: 2px;
    z-index: 5;
}
.bb-ball .brow.l { left: 13px; } .bb-ball .brow.r { right: 13px; }

/* mouth */
.bb-ball .mouth {
    position: absolute; top: 48px; left: 50%;
    transform: translateX(-50%);
    width: 13px; height: 6px;
    background: #e88b8b;
    border-radius: 0 0 50% 50%;
    z-index: 4;
}

/* blush */
.bb-ball .blush {
    position: absolute; top: 41px;
    width: 11px; height: 6px;
    background: rgba(255,150,150,0.30);
    border-radius: 50%; z-index: 2;
}
.bb-ball .blush.l { left: 6px; } .bb-ball .blush.r { right: 6px; }

/* suit */
.bb-ball .suit {
    position: absolute; bottom: 0; left: 50%;
    transform: translateX(-50%);
    width: 0; height: 0;
    border-left: 19px solid transparent;
    border-right: 19px solid transparent;
    border-bottom: 20px solid #2c2c2c;
    z-index: 1;
}
.bb-ball .shirt {
    position: absolute; bottom: 0; left: 50%;
    transform: translateX(-50%);
    width: 14px; height: 11px;
    background: #fff; z-index: 1;
}
.bb-ball .tie {
    position: absolute; bottom: 0; left: 50%;
    transform: translateX(-50%);
    width: 6px; height: 14px;
    background: #c0392b;
    border-radius: 1px 1px 3px 3px;
    z-index: 5;
}
.bb-ball .tie-k {
    position: absolute; bottom: 13px; left: 50%;
    transform: translateX(-50%);
    width: 8px; height: 5px;
    background: #a93226;
    border-radius: 1px; z-index: 6;
}

/* online dot */
.bb-ball .dot {
    position: absolute; bottom: 2px; right: 2px;
    width: 15px; height: 15px;
    background: #2ecc71;
    border: 2px solid #fff; border-radius: 50%;
    z-index: 10;
    animation: bb-pulse 2s ease-in-out infinite;
}
@keyframes bb-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(46,204,113,0.5); }
    50%      { box-shadow: 0 0 0 6px rgba(46,204,113,0); }
}

/* ================================================================
   聊天浮窗
   ================================================================ */
.bb-panel {
    position: fixed;
    bottom: 120px;
    right: 28px;
    width: 420px;
    max-height: 520px;
    background: #fff;
    border-radius: 20px;
    box-shadow: 0 8px 44px rgba(0,0,0,0.16);
    z-index: 100000;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}
.bb-panel .bb-panel-hdr {
    background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
    padding: 13px 18px;
    display: flex; align-items: center; justify-content: space-between;
    flex-shrink: 0;
}
.bb-panel .bb-panel-hdr span {
    font-size: 15px; font-weight: 700; color: #5d4037;
}
.bb-panel .bb-panel-body {
    flex: 1; overflow-y: auto;
    padding: 6px 14px;
    background: #fefaf6;
}

@media (max-width: 480px) {
    .bb-panel {
        width: calc(100vw - 16px);
        max-height: 440px;
        right: 8px; bottom: 105px;
        border-radius: 16px;
    }
    .bb-ball { width: 66px; height: 66px; }
    #boss-baby-float { bottom: 20px; right: 16px; }
    #bb-tooltip { bottom: 96px; right: 16px; }
}
</style>"""


# ================================================================
# Boss Baby 球 HTML（用 <a> 标签包裹，点击触发 query_params）
# ================================================================

BALL_HTML = """
<div id="boss-baby-float">
    <div id="bb-tooltip">有问题？点我聊聊~</div>
    <a href="?chat=open" class="bb-ball" title="智能问答">
        <div class="h-front"></div><div class="h-swoop"></div>
        <div class="brow l"></div><div class="brow r"></div>
        <div class="eye l"></div><div class="eye r"></div>
        <div class="blush l"></div><div class="blush r"></div>
        <div class="mouth"></div>
        <div class="shirt"></div><div class="suit"></div>
        <div class="tie"></div><div class="tie-k"></div>
        <div class="dot"></div>
    </a>
</div>
<script>
(function(){
    var t=document.getElementById('bb-tooltip');
    if(t){
        setTimeout(function(){t.style.opacity='1';},2500);
        setTimeout(function(){t.style.opacity='0';},9000);
    }
})();
</script>
"""


# ================================================================
# 渲染函数
# ================================================================

def render_chat_float(chat_agent: ChatAgent, kb=None):
    """
    渲染 Boss Baby 悬浮球 + 智能问答浮窗。
    在 app.py 页面末尾调用。
    """
    # ---- CSS ----
    st.markdown(BALL_CSS, unsafe_allow_html=True)

    # ---- session state ----
    if "show_chat_float" not in st.session_state:
        st.session_state.show_chat_float = False
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # ---- 检测 <a> 标签点击（通过 query_params）----
    if st.query_params.get("chat") == "open":
        st.session_state.show_chat_float = True
        st.query_params.clear()
        st.rerun()

    # ---- Boss Baby 球 ----
    if not st.session_state.show_chat_float:
        st.markdown(BALL_HTML, unsafe_allow_html=True)

    # ---- 聊天浮窗 ----
    if st.session_state.show_chat_float:
        _render_chat_panel(chat_agent, kb)


@st.dialog("👶 宝宝巴适 · 智能问答", width="large")
def _render_chat_panel(chat_agent: ChatAgent, kb=None):
    close_col, clear_col = st.columns(2)
    if close_col.button("关闭", key="cf_close", use_container_width=True):
        st.session_state.show_chat_float = False
        st.rerun()
    if clear_col.button("清除对话", key="cf_clear", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

    st.caption("结合当前宝宝画像、知识库和安全规则回答辅食问题。")

    questions = [
        "6月龄宝宝可以吃哪些食物？",
        "猪肝含铁量多少？",
        "鸡蛋过敏要注意什么？",
        "辅食应该怎么循序渐进？",
    ]
    clicked = None
    with st.expander("💡 快捷提问"):
        cols = st.columns(2)
        for i, question in enumerate(questions):
            with cols[i % 2]:
                if st.button(question, key=f"cf_q_{i}", use_container_width=True):
                    clicked = question

    if not st.session_state.chat_history:
        st.info("输入问题后，回答会显示在这里。")
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📚 信息来源"):
                    for source in msg["sources"]:
                        st.caption(f"· {source}")

    with st.form("chat_float_form", clear_on_submit=True):
        typed_input = st.text_input(
            "输入问题",
            placeholder="例如：宝宝对鸡蛋过敏，可以吃什么替代？",
            key="cf_input",
        )
        send_clicked = st.form_submit_button("发送", type="primary", use_container_width=True)
    user_input = clicked or (typed_input.strip() if send_clicked else None)

    if user_input:
        with st.spinner("宝宝在思考中..."):
            result = chat_agent.process({
                "message": user_input,
                "history": _agent_history(st.session_state.chat_history),
                "current_profile": st.session_state.get("baby_profile", {}),
            })
        answer = result.get("answer") or "抱歉，我暂时无法回答这个问题。"
        st.session_state.chat_history.extend([
            {"role": "user", "content": user_input},
            {
                "role": "assistant",
                "content": answer,
                "answer": answer,
                "sources": result.get("sources", []),
            },
        ])
        st.rerun()
