import { useState, useRef, useEffect } from "react";
import { api } from "./api";
import "./App.css";

/* ================================================================
   宝宝信息侧边栏
   ================================================================ */
function Sidebar({ profile, setProfile, onAssess }) {
  const ALLERGENS = ["鸡蛋", "牛奶", "花生", "鱼类", "大豆", "小麦", "坚果", "芝麻"];
  const FOODS = ["大米粉","小米","燕麦","玉米","猪肝","鸡肝","牛肉","猪肉(瘦)","鸡肉","鸭肉","三文鱼","鳕鱼","带鱼","虾仁","鸡蛋","豆腐","胡萝卜","南瓜","紫薯","山药","土豆","菠菜","西兰花","花椰菜","油菜","番茄","冬瓜","豌豆","苹果","香蕉","梨","牛油果","蓝莓","草莓","橙子","木瓜","酸奶","奶酪","核桃","芝麻粉"];

  const toggle = (list, key, val) => {
    const arr = profile[key] || [];
    const next = arr.includes(val) ? arr.filter((v) => v !== val) : [...arr, val];
    setProfile({ ...profile, [key]: next });
  };

  return (
    <aside className="sidebar">
      <div className="logo"><span>🍼</span>宝宝巴适</div>

      <div className="age-row">
        <div className="field">
          <label>月龄</label>
          <input type="number" value={profile.age_months} min={0} max={36}
            onChange={(e) => setProfile({ ...profile, age_months: Number(e.target.value) })} />
        </div>
        <div className="field">
          <label>矫正月龄</label>
          <input type="number" value={profile.corrected_age_months || ""} min={0} max={36}
            placeholder="早产儿填"
            onChange={(e) => setProfile({ ...profile, corrected_age_months: e.target.value ? Number(e.target.value) : null })} />
        </div>
      </div>

      <div className="field">
        <label>喂养方式</label>
        <select value={profile.feeding_method}
          onChange={(e) => setProfile({ ...profile, feeding_method: e.target.value })}>
          <option value="breast">纯母乳</option>
          <option value="formula">配方奶</option>
          <option value="mixed">混合喂养</option>
        </select>
      </div>

      <div className="field">
        <label>已知过敏原</label>
        <div className="chip-group">
          {ALLERGENS.map((a) => (
            <span key={a} className={`chip ${(profile.allergies || []).includes(a) ? "active" : ""}`}
              onClick={() => toggle("allergies", a)}>
              {a}
            </span>
          ))}
        </div>
      </div>

      <div className="field">
        <label>已尝试食材</label>
        <div className="chip-group">
          {FOODS.map((f) => (
            <span key={f} className={`chip ${(profile.tried_foods || []).includes(f) ? "active" : ""}`}
              onClick={() => toggle("tried_foods", f)}>
              {f}
            </span>
          ))}
        </div>
      </div>

      <div className="field">
        <label>备注（发育信号等）</label>
        <textarea value={profile.notes || ""} placeholder="如：宝宝能坐稳了，看我们吃饭会伸手…"
          onChange={(e) => setProfile({ ...profile, notes: e.target.value })} />
      </div>

      <button className="btn-primary" onClick={onAssess}>🔍 开始评估</button>
    </aside>
  );
}

/* ================================================================
   标签徽章
   ================================================================ */
function Tag({ type }) {
  const map = { suitable: "✅ 安全", caution: "⚠️ 注意", avoid: "🚫 避免", unknown: "❓ 未知" };
  return <span className={`tag ${type}`}>{map[type] || type}</span>;
}

/* ================================================================
   安全评估
   ================================================================ */
function Assessment({ data }) {
  if (!data) return <p style={{ color: "#999" }}>👈 请先在左侧填写宝宝信息，点击「开始评估」</p>;

  const signals = data.readiness_signals || [];
  const foods = data.food_tags || {};
  const avoidList = Object.entries(foods).filter(([, v]) => v.tag === "avoid");
  const cautionList = Object.entries(foods).filter(([, v]) => v.tag === "caution");
  const suitableList = Object.entries(foods).filter(([, v]) => v.tag === "suitable");
  const stage = data.stage || {};

  return (
    <div>
      <h2 className="section-title">📊 阶段判断</h2>
      <div className="metrics-row">
        <div className={`metric-card ${data.can_start ? "g" : "r"}`}>
          <div className="val">{data.can_start ? "✅" : "🚫"}</div>
          <div className="lbl">可开始辅食</div>
        </div>
        <div className="metric-card">
          <div className="val">{stage.label || "—"}</div>
          <div className="lbl">当前阶段</div>
        </div>
        <div className="metric-card">
          <div className="val">{data.effective_age_months}月</div>
          <div className="lbl">矫正月龄</div>
        </div>
        <div className="metric-card">
          <div className="val">{signals.length}个</div>
          <div className="lbl">就绪信号</div>
        </div>
      </div>

      {data.recommendation && (
        <div className="card" style={{ background: data.can_start ? "#e8f5e9" : "#fff3e0" }}>
          {data.recommendation}
        </div>
      )}

      {(data.blocking_reasons || []).length > 0 && (
        <div className="card" style={{ background: "#ffebee" }}>
          <b>⚠️ 阻止原因：</b>
          {data.blocking_reasons.map((r, i) => <p key={i}>· {r}</p>)}
        </div>
      )}

      {signals.length > 0 && (
        <div className="card">
          <b>📝 检测到 {signals.length} 个发育就绪信号</b>
          {signals.map((s, i) => <p key={i}>· {s.label}</p>)}
        </div>
      )}

      {Object.keys(foods).length > 0 && (
        <>
          <h2 className="section-title">🍽️ 食材安全标签</h2>
          {avoidList.length > 0 && (
            <div className="card" style={{ background: "#ffebee" }}>
              <b>🚫 必须避免 ({avoidList.length}种)：</b>
              {avoidList.map(([name, f]) => (
                <p key={name}>· <b>{name}</b>：{(f.reasons || []).join("；")}</p>
              ))}
            </div>
          )}
          {cautionList.length > 0 && (
            <div className="card" style={{ background: "#fff8e1" }}>
              <b>⚠️ 需要注意 ({cautionList.length}种)：</b>
              {cautionList.slice(0, 5).map(([name, f]) => (
                <p key={name}>· <b>{name}</b>：{(f.reasons || []).join("；")}</p>
              ))}
            </div>
          )}
          <div className="food-grid">
            {suitableList.map(([name]) => (
              <div key={name} className="food-card">✅ {name}</div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ================================================================
   周度计划
   ================================================================ */
function WeeklyPlan({ data, onRefresh }) {
  if (!data || !data.plan) {
    return <p style={{ color: "#999" }}>请先完成安全评估，然后生成计划</p>;
  }

  const plan = data.plan || [];
  const newFoods = data.new_foods_this_week || [];
  const notes = data.nutrition_notes || [];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 className="section-title" style={{ marginBottom: 0 }}>📅 周度辅食计划</h2>
        <button className="btn-primary" onClick={onRefresh} style={{ padding: "8px 20px", fontSize: 14 }}>🔄 刷新计划</button>
      </div>

      {newFoods.length > 0 && (
        <div className="card" style={{ background: "#fff8e1", borderLeft: "4px solid #ff9800" }}>
          🆕 本周新食材：<b>{newFoods.join("、")}</b>。每次一种，观察3-5天。
        </div>
      )}

      <div className="week-calendar">
        {plan.map((d) => (
          <div key={d.day} className={`day-card ${d.is_new_food ? "new" : ""}`}>
            <div className="dn">{d.day}{d.is_new_food ? " 🆕" : ""}</div>
            {(d.foods || []).map((f) => <div key={f} className="fi">{f}</div>)}
          </div>
        ))}
      </div>

      {notes.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          {notes.map((n, i) => (
            <p key={i} style={{ color: n.startsWith("✅") ? "#2e7d32" : n.startsWith("⚠") ? "#e65100" : "#1565c0" }}>
              {n}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

/* ================================================================
   配料解析
   ================================================================ */
function LabelParser() {
  const [text, setText] = useState("");
  const [age, setAge] = useState(6);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const parse = async () => {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const r = await api.parseLabel(text, age);
      setResult(r);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  return (
    <div>
      <h2 className="section-title">🔍 配料表解析</h2>
      <div className="card">
        <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
          <input value={text} onChange={(e) => setText(e.target.value)}
            placeholder="粘贴配料表，如：大米(85%)、乳清蛋白、白砂糖、柠檬酸(330)"
            style={{ flex: 1, border: "1.5px solid #e8d5c8", borderRadius: 10, padding: "8px 12px", fontSize: 14 }} />
          <input type="number" value={age} onChange={(e) => setAge(Number(e.target.value))}
            min={0} max={36} style={{ width: 70, border: "1.5px solid #e8d5c8", borderRadius: 10, padding: "8px", fontSize: 14, textAlign: "center" }} />
          <button className="btn-primary" onClick={parse} disabled={loading}
            style={{ padding: "8px 20px", fontSize: 14 }}>
            {loading ? "解析中…" : "🔬 解析"}
          </button>
        </div>
        <small style={{ color: "#999" }}>月龄</small>
      </div>

      {result && (
        <div className="card">
          <p>共识别 <b>{result.total_count}</b> 种成分，匹配 <b>{result.matched_count}</b> 种</p>
          {result.risk_summary?.has_avoid && <p style={{ color: "#c62828" }}>🚫 含有需避免的成分</p>}
          {result.risk_summary?.allergens?.length > 0 && <p style={{ color: "#e65100" }}>⚠️ 过敏原：{result.risk_summary.allergens.join("、")}</p>}
          {result.risk_summary?.added_sugars?.length > 0 && <p style={{ color: "#e65100" }}>⚠️ 添加糖：{result.risk_summary.added_sugars.join("、")}</p>}

          <div style={{ marginTop: 12 }}>
            {(result.parsed || []).map((entry, i) => {
              const worst = entry.tags?.find((t) => t.tag === "avoid") ? "avoid"
                : entry.tags?.find((t) => t.tag === "caution") ? "caution"
                : entry.matched ? "suitable" : "unknown";
              return (
                <div key={i} className={`ing-row ${worst}`}>
                  <div>
                    <b>{entry.raw_name}</b>
                    {entry.ingredient?.category && <span style={{ color: "#999", fontSize: 12, marginLeft: 8 }}>{entry.ingredient.category}</span>}
                  </div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end" }}>
                    {(entry.tags || []).map((t, j) => <Tag key={j} type={t.tag} />)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ================================================================
   Boss Baby 悬浮球 + 聊天浮窗
   ================================================================ */
function BossBabyChat() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [tooltip, setTooltip] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    const t1 = setTimeout(() => setTooltip(true), 2000);
    const t2 = setTimeout(() => setTooltip(false), 8000);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [msgs, loading]);

  const send = async (text) => {
    if (!text.trim()) return;
    const msg = text;
    setInput("");
    setMsgs((prev) => [...prev, { role: "user", content: msg }]);
    setLoading(true);
    try {
      const history = msgs
        .filter((m) => m.role === "assistant")
        .map((m) => ({ question: msgs[msgs.indexOf(m) - 1]?.content || "", answer: m.content }));
      const r = await api.chat(msg, history);
      setMsgs((prev) => [...prev, { role: "assistant", content: r.answer || "抱歉，暂时无法回答。" }]);
    } catch (e) { setMsgs((prev) => [...prev, { role: "assistant", content: "网络出错了，请稍后再试。" }]); }
    setLoading(false);
  };

  return (
    <>
      {/* 悬浮球 */}
      {!open && (
        <div className="bb-float">
          {tooltip && <div className="bb-tooltip" style={{ opacity: 1 }}>有问题？点我聊聊~</div>}
          <div className="bb-ball" onClick={() => setOpen(true)} title="智能问答">
            <div className="h-front" /><div className="h-swoop" />
            <div className="brow l" /><div className="brow r" />
            <div className="eye l" /><div className="eye r" />
            <div className="blush l" /><div className="blush r" />
            <div className="mouth" />
            <div className="shirt" /><div className="suit" />
            <div className="tie" /><div className="tie-k" /><div className="dot" />
          </div>
        </div>
      )}

      {/* 聊天浮窗 */}
      {open && (
        <div className="chat-overlay">
          <div className="ch">
            <b>👶 宝宝巴适 · 智能问答</b>
            <button onClick={() => setOpen(false)}>✕</button>
          </div>
          <div className="q-row">
            {["6月龄宝宝可以吃哪些食物？","猪肝含铁量多少？","鸡蛋过敏要注意什么？","辅食应该怎么循序渐进？"].map((q) => (
              <button key={q} className="q-btn" onClick={() => send(q)} disabled={loading}>{q}</button>
            ))}
          </div>
          <div className="cb" ref={bodyRef}>
            {msgs.length === 0 && (
              <p style={{ textAlign: "center", color: "#bbb", fontSize: 13, marginTop: 40 }}>
                🍼 我是宝宝巴适，有什么辅食问题可以问我~
              </p>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`msg-b ${m.role === "user" ? "u" : "a"}`}>{m.content}</div>
            ))}
            {loading && (
              <div className="msg-b a" style={{ display: "flex", gap: 4, padding: "8px 14px" }}>
                <span style={{ width: 7, height: 7, background: "#ccc", borderRadius: "50%", animation: "bbPulse 1.2s ease-in-out infinite" }} />
                <span style={{ width: 7, height: 7, background: "#ccc", borderRadius: "50%", animation: "bbPulse 1.2s ease-in-out .2s infinite" }} />
                <span style={{ width: 7, height: 7, background: "#ccc", borderRadius: "50%", animation: "bbPulse 1.2s ease-in-out .4s infinite" }} />
              </div>
            )}
          </div>
          <div className="cf">
            <input value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send(input)}
              placeholder="关于宝宝辅食，随时问我..." />
            <button onClick={() => send(input)} disabled={loading}>➤</button>
          </div>
        </div>
      )}
    </>
  );
}

/* ================================================================
   主 App
   ================================================================ */
export default function App() {
  const [profile, setProfile] = useState({
    age_months: 6,
    corrected_age_months: null,
    allergies: [],
    feeding_method: "breast",
    tried_foods: [],
    notes: "",
  });
  const [assessment, setAssessment] = useState(null);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);

  const doAssess = async () => {
    setLoading(true);
    try {
      const r = await api.assess(profile);
      setAssessment(r);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const doPlan = async () => {
    setLoading(true);
    try {
      const r = await api.plan(profile);
      setPlan(r);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  return (
    <div className="app-container">
      <Sidebar profile={profile} setProfile={setProfile} onAssess={doAssess} />
      <main className="main-content">
        <h1 style={{ fontSize: 24, marginBottom: 24 }}>👶 宝宝辅食助手</h1>

        {loading && <p style={{ color: "#999", marginBottom: 16 }}>⏳ 宝宝在思考中...</p>}

        <Assessment data={assessment} />

        {assessment?.can_start && (
          <>
            <hr style={{ border: "none", borderTop: "1px solid #f0e8df", margin: "24px 0" }} />
            <WeeklyPlan data={plan} onRefresh={doPlan} />
          </>
        )}

        {assessment && (
          <>
            <hr style={{ border: "none", borderTop: "1px solid #f0e8df", margin: "24px 0" }} />
            <LabelParser />
          </>
        )}

        {!assessment && (
          <>
            <hr style={{ border: "none", borderTop: "1px solid #f0e8df", margin: "24px 0" }} />
            <p style={{ color: "#999", marginBottom: 20 }}>👈 填入宝宝信息后点击「开始评估」查看完整报告</p>
            <LabelParser />
          </>
        )}
      </main>

      <BossBabyChat />
    </div>
  );
}
