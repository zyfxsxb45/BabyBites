import { useState, useRef, useEffect } from "react";
import { api } from "./api";
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer,
} from "recharts";
import "./App.css";

/* ================================================================
   宝宝信息侧边栏
   ================================================================ */
function Sidebar({ profile, setProfile, onAssess }) {
  const ALLERGENS = ["鸡蛋", "牛奶", "花生", "鱼类", "虾", "大豆", "小麦", "坚果", "芝麻"];
  const FOODS = ["大米粉","小米","燕麦","玉米","猪肝","鸡肝","牛肉","猪肉(瘦)","鸡肉","鸭肉","三文鱼","鳕鱼","带鱼","虾仁","鸡蛋","豆腐","胡萝卜","南瓜","紫薯","山药","土豆","菠菜","西兰花","花椰菜","油菜","番茄","冬瓜","豌豆","苹果","香蕉","梨","牛油果","蓝莓","草莓","橙子","木瓜","酸奶","奶酪","核桃","芝麻粉"];

  const toggle = (key, val) => {
    const arr = profile[key] || [];
    const next = arr.includes(val) ? arr.filter((v) => v !== val) : [...arr, val];
    setProfile({ ...profile, [key]: next });
  };

  return (
    <aside className="sidebar">
      <div className="logo"><img src="/logo.png" alt="logo" className="logo-img" />宝宝巴适</div>

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
            onChange={(e) => setProfile({ ...profile, corrected_age_months: e.target.value ? Number(e.target.value) : null, preterm: e.target.value ? true : profile.preterm })} />
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
          {/* 自定义过敏原：可移除 */}
          {(profile.allergies || [])
            .filter((a) => !ALLERGENS.includes(a))
            .map((a) => (
              <span key={a} className="chip custom active" onClick={() => toggle("allergies", a)}>
                {a} <span style={{ marginLeft: 2, opacity: 0.7 }}>✕</span>
              </span>
            ))}
        </div>
        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
          <input
            placeholder="输入其他过敏原…"
            style={{ flex: 1, border: "1.5px solid #e8d5c8", borderRadius: 8, padding: "5px 10px", fontSize: 12 }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.target.value.trim()) {
                const val = e.target.value.trim();
                if (!(profile.allergies || []).includes(val)) {
                  setProfile({ ...profile, allergies: [...(profile.allergies || []), val] });
                }
                e.target.value = "";
              }
            }}
          />
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
   Tab 1：阶段判断
   ================================================================ */
function StageAssessment({ data }) {
  if (!data) return <p style={{ color: "#999", textAlign: "center", padding: 40 }}>👈 请先在左侧填写宝宝信息，点击「开始评估」</p>;

  const signals = data.readiness_signals || [];
  const stage = data.stage || {};

  return (
    <div className="fade-in">
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

      {(data.notes_avoid_foods || []).length > 0 && (
        <div className="card" style={{ background: "#fff3e0", borderLeft: "4px solid #ff9800" }}>
          <b>📝 从备注中检测到以下食材过敏/不耐受：</b>
          {data.notes_avoid_foods.map((f, i) => (
            <span key={i} style={{ display: "inline-block", margin: "4px 6px 0 0", padding: "2px 10px", background: "#ffcc80", color: "#e65100", borderRadius: 6, fontSize: 13, fontWeight: 600 }}>{f}</span>
          ))}
          <p style={{ marginTop: 8, fontSize: 12, color: "#8d6e63" }}>已在食材安全标签中自动标记为「🚫 避免」</p>
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

      {signals.length === 0 && !data.can_start && (
        <div className="card" style={{ background: "#f5f5f5", color: "#999", textAlign: "center" }}>
          暂未检测到明确的发育就绪信号，请结合儿科医生建议判断
        </div>
      )}
    </div>
  );
}

/* ================================================================
   Tab 2：食材安全标签
   ================================================================ */
function FoodSafetyTags({ data }) {
  if (!data) return <p style={{ color: "#999", textAlign: "center", padding: 40 }}>👈 请先完成评估以查看食材安全标签</p>;

  const foods = data.food_tags || {};
  const avoidList = Object.entries(foods).filter(([, v]) => v.tag === "avoid");
  const cautionList = Object.entries(foods).filter(([, v]) => v.tag === "caution");
  const recommended = Object.entries(foods).filter(([, v]) => v.tag !== "avoid" && v.tag !== "caution" && v.iron_rich);
  const laterList = Object.entries(foods).filter(([, v]) => v.tag !== "avoid" && v.tag !== "caution" && !v.iron_rich);

  if (Object.keys(foods).length === 0) {
    return <p style={{ color: "#999", textAlign: "center", padding: 40 }}>暂无食材数据</p>;
  }

  return (
    <div className="fade-in">
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
          <b>⚠️ 需谨慎引入 ({cautionList.length}种)：</b>
          {cautionList.slice(0, 5).map(([name, f]) => (
            <p key={name}>· <b>{name}</b>：{(f.reasons || []).join("；")}</p>
          ))}
          {cautionList.length > 5 && (
            <details className="caution-details">
              <summary>…还有 {cautionList.length - 5} 种，点击展开</summary>
              {cautionList.slice(5).map(([name, f]) => (
                <p key={name}>· <b>{name}</b>：{(f.reasons || []).join("；")}</p>
              ))}
            </details>
          )}
        </div>
      )}

      {recommended.length > 0 && (
        <div className="card" style={{ background: "#e8f5e9" }}>
          <b>⭐ 优先推荐 ({recommended.length}种) — 高铁、高营养、适合首尝</b>
          <div className="food-grid" style={{ marginTop: 8 }}>
            {recommended.map(([name]) => (
              <div key={name} className="food-card">⭐ {name}</div>
            ))}
          </div>
        </div>
      )}

      {laterList.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", color: "#8d6e63", fontSize: 14, fontWeight: 600 }}>
            🔜 可后续添加 ({laterList.length}种) — 首轮辅食之后逐步引入
          </summary>
          <div className="food-grid" style={{ marginTop: 8 }}>
            {laterList.map(([name]) => (
              <div key={name} className="food-card">{name}</div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

/* ================================================================
   营养雷达图
   ================================================================ */
const RADAR_DATA = [
  { nutrient: "铁", value: 85, full: 100 },
  { nutrient: "锌", value: 60, full: 100 },
  { nutrient: "蛋白质", value: 72, full: 100 },
  { nutrient: "维生素C", value: 45, full: 100 },
  { nutrient: "膳食纤维", value: 55, full: 100 },
];

function NutrientRadar() {
  return (
    <div className="radar-card">
      <div className="radar-title">📊 本周营养素覆盖</div>
      <ResponsiveContainer width="100%" height={220}>
        <RadarChart data={RADAR_DATA} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#e8d5c8" />
          <PolarAngleAxis dataKey="nutrient" tick={{ fill: "#8d6e63", fontSize: 12 }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
          <Radar
            name="覆盖率"
            dataKey="value"
            stroke="#ff9800"
            fill="#ff9800"
            fillOpacity={0.25}
            strokeWidth={2}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ================================================================
   Tab 3：周度计划
   ================================================================ */
function WeeklyPlan({ data, onRefresh }) {
  const [planStartedAt, setPlanStartedAt] = useState(() => {
    return localStorage.getItem("bb_plan_start") || null;
  });

  // 记录计划开始日期 & 计算已执行天数
  useEffect(() => {
    if (data?.plan?.length > 0) {
      const stored = localStorage.getItem("bb_plan_start");
      if (!stored) {
        const today = new Date().toISOString().slice(0, 10);
        localStorage.setItem("bb_plan_start", today);
        setPlanStartedAt(today);
      }
    }
  }, [data]);

  const today = new Date();
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const todayStr = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日 ${weekdays[today.getDay()]}`;

  const daysElapsed = planStartedAt
    ? Math.max(1, Math.ceil((today - new Date(planStartedAt)) / (1000 * 60 * 60 * 24)))
    : 0;

  if (!data || !data.plan) {
    return (
      <div className="fade-in">
        <NutrientRadar />
        <div className="card" style={{ textAlign: "center", padding: "32px 20px" }}>
          <p style={{ color: "#999", marginBottom: 12 }}>计划尚未生成或生成失败</p>
          <button className="btn-primary" onClick={onRefresh} style={{ padding: "8px 24px", fontSize: 14 }}>🔄 生成计划</button>
        </div>
      </div>
    );
  }

  const plan = data.plan || [];
  const newFoods = data.new_foods_this_week || [];
  const notes = data.nutrition_notes || [];

  return (
    <div className="fade-in">
      <NutrientRadar />

      {/* 今日状态栏 */}
      <div className="plan-status-bar">
        <div className="plan-status-item">
          <span className="plan-status-icon">📅</span>
          <span className="plan-status-label">今天</span>
          <span className="plan-status-value">{todayStr}</span>
        </div>
        <div className="plan-status-divider" />
        <div className="plan-status-item">
          <span className="plan-status-icon">⏱️</span>
          <span className="plan-status-label">已执行</span>
          <span className="plan-status-value">{daysElapsed} 天</span>
        </div>
        <div className="plan-status-divider" />
        <div className="plan-status-item">
          <span className="plan-status-icon">🎯</span>
          <span className="plan-status-label">计划开始</span>
          <span className="plan-status-value">{planStartedAt || todayStr}</span>
        </div>
      </div>

      {/* 今日与计划的关系提示 */}
      {(() => {
        const planDates = plan.map((d) => d.date).filter(Boolean).sort();
        if (planDates.length > 0) {
          const first = planDates[0], last = planDates[planDates.length - 1];
          const todayISO = today.toISOString().slice(0, 10);
          if (todayISO < first) {
            const daysUntil = Math.ceil((new Date(first) - today) / 86400000);
            return (
              <div style={{ textAlign: "center", marginTop: 8, fontSize: 12, color: "#8d6e63" }}>
                📋 计划将于 {daysUntil} 天后（{first}）开始，可以先熟悉食材哦
              </div>
            );
          }
          if (todayISO > last) {
            return (
              <div style={{ textAlign: "center", marginTop: 8, fontSize: 12, color: "#e65100" }}>
                ⚠️ 本周计划已结束，点击「刷新计划」生成新一周安排
              </div>
            );
          }
        }
        return null;
      })()}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "20px 0 16px" }}>
        <h2 className="section-title" style={{ marginBottom: 0 }}>📅 7 日排菜</h2>
        <button className="btn-primary" onClick={onRefresh} style={{ padding: "8px 20px", fontSize: 14 }}>🔄 刷新计划</button>
      </div>

      {newFoods.length > 0 && (
        <div className="card" style={{ background: "#fff8e1", borderLeft: "4px solid #ff9800" }}>
          🆕 本周新食材：<b>{newFoods.join("、")}</b>。每次一种，观察3-5天。
        </div>
      )}

      <div className="week-calendar">
        {plan.map((d) => {
          const isToday = d.date === today.toISOString().slice(0, 10);
          return (
            <div key={d.day} className={`day-card ${d.is_new_food ? "new" : ""} ${isToday ? "today" : ""}`}>
              <div className="dn">
                {d.day}{d.is_new_food ? " 🆕" : ""}
                {isToday && <span className="today-badge">今天</span>}
              </div>
              <div className="dd">{d.date?.slice(5)}</div>
              {(d.foods || []).map((f) => <div key={f} className="fi">{f}</div>)}
              {d.serving_note && <div className="sn">{d.serving_note}</div>}
            </div>
          );
        })}
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
   Tab 4：配料解析
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
    <div className="fade-in">
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
   LLM 设置面板
   ================================================================ */
const LLM_PRESETS = [
  { label: "DeepSeek", url: "https://api.deepseek.com", model: "deepseek-chat" },
  { label: "OpenAI", url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { label: "硅基流动", url: "https://api.siliconflow.cn/v1", model: "deepseek-ai/DeepSeek-V3" },
  { label: "阿里百炼", url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
];

function SettingsPanel({ open, onClose }) {
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (open) {
      api.settings.getLLM().then((r) => {
        setApiKey(r.api_key || "");
        setBaseUrl(r.base_url || "");
        setModel(r.model || "");
      }).catch(() => {});
    }
  }, [open]);

  const save = async () => {
    if (!apiKey.trim() || !baseUrl.trim() || !model.trim()) {
      setMsg({ type: "error", text: "请填写完整的 API Key、Base URL 和 Model" });
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      const r = await api.settings.saveLLM({ api_key: apiKey, base_url: baseUrl, model });
      setMsg({ type: "success", text: r.message || "配置已保存" });
    } catch (e) {
      setMsg({ type: "error", text: "保存失败：" + e.message });
    }
    setLoading(false);
  };

  if (!open) return null;

  return (
    <div className="settings-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="settings-panel">
        <div className="settings-header">
          <b>⚙️ LLM 设置</b>
          <button onClick={onClose}>✕</button>
        </div>

        <div className="settings-body">
          <label className="fb-label">API Key</label>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            style={inputStyle} />

          <label className="fb-label">Base URL</label>
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            style={inputStyle} />

          <label className="fb-label">Model</label>
          <input value={model} onChange={(e) => setModel(e.target.value)}
            placeholder="gpt-4o-mini"
            style={inputStyle} />

          <label className="fb-label" style={{ marginTop: 12 }}>快速切换预设</label>
          <div className="chip-group" style={{ maxHeight: "none" }}>
            {LLM_PRESETS.map((p) => (
              <span key={p.label} className="chip"
                onClick={() => { setBaseUrl(p.url); setModel(p.model); }}
                style={{ cursor: "pointer" }}>
                {p.label}
              </span>
            ))}
          </div>

          {msg && (
            <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: 10, background: msg.type === "success" ? "#e8f5e9" : "#ffebee", color: msg.type === "success" ? "#2e7d32" : "#c62828", fontSize: 13 }}>
              {msg.text}
            </div>
          )}

          <button className="btn-primary" onClick={save} disabled={loading}
            style={{ marginTop: 16, width: "100%" }}>
            {loading ? "保存中…" : "💾 保存并生效"}
          </button>
          <p style={{ fontSize: 11, color: "#bbb", textAlign: "center", marginTop: 8 }}>
            配置保存在服务器端，重启后仍然有效
          </p>
        </div>
      </div>
    </div>
  );
}

const inputStyle = {
  width: "100%", border: "1.5px solid #e8d5c8", borderRadius: 10,
  padding: "8px 12px", fontSize: 14, boxSizing: "border-box",
};

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

      {open && (
        <div className="chat-overlay">
          <div className="ch">
            <b><img src="/logo.png" alt="logo" className="logo-img-xs" />宝宝巴适 · 智能问答</b>
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
   Tab 配置
   ================================================================ */
const TABS = [
  { key: "stage", label: "📊 阶段判断" },
  { key: "foods", label: "🍽️ 食材安全标签" },
  { key: "plan", label: "📅 周度辅食计划" },
  { key: "label", label: "🔍 配料表解析" },
];

/* ================================================================
   每日喂养反馈
   ================================================================ */
function DailyFeedback({ plan, onFeedbackSubmit }) {
  const todayPlan = plan?.plan || [];
  const todayIdx = new Date().getDay(); // 0=Sun ... 6=Sat
  const todayName = ["周日","周一","周二","周三","周四","周五","周六"][todayIdx];
  const todayFoods = todayPlan.find((d) => d.day === todayName)?.foods || [];
  const allPlanFoods = [...new Set(todayPlan.flatMap((d) => d.foods || []))];

  const [foodName, setFoodName] = useState("");
  const [reaction, setReaction] = useState("none");
  const [severity, setSeverity] = useState("mild");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedbackHistory, setFeedbackHistory] = useState(null);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    api.feedback.get().then(setFeedbackHistory).catch(() => {});
  }, [plan]);

  const submit = async () => {
    if (!foodName.trim()) return;
    setSubmitting(true);
    setMessage(null);
    try {
      await api.feedback.submit({
        food_name: foodName,
        reaction,
        severity: reaction === "none" ? "mild" : severity,
        notes,
      });
      setMessage({ type: "success", text: `已记录「${foodName}」的反馈` });
      setFoodName("");
      setReaction("none");
      setSeverity("mild");
      setNotes("");
      const r = await api.feedback.get();
      setFeedbackHistory(r);
      if (onFeedbackSubmit) await onFeedbackSubmit();
    } catch (e) {
      setMessage({ type: "error", text: "提交失败：" + e.message });
    }
    setSubmitting(false);
  };

  return (
    <div style={{ marginTop: 28 }}>
      <h2 className="section-title">📝 每日喂养反馈</h2>

      {/* 反馈表单 */}
      <div className="card">
        <label className="fb-label">反馈食材</label>
        {allPlanFoods.length > 0 ? (
          <>
            <div className="chip-group" style={{ maxHeight: "none", marginBottom: todayFoods.length > 0 ? 8 : 0 }}>
              {(todayFoods.length > 0 ? todayFoods : allPlanFoods).map((f) => (
                <span key={f} className={`chip ${foodName === f ? "active" : ""}`}
                  onClick={() => setFoodName(f)}>{f}</span>
              ))}
            </div>
            {todayFoods.length > 0 && allPlanFoods.length > todayFoods.length && (
              <details style={{ marginBottom: 8 }}>
                <summary style={{ fontSize: 12, color: "#999", cursor: "pointer" }}>本周其他食材</summary>
                <div className="chip-group" style={{ maxHeight: "none", marginTop: 6 }}>
                  {allPlanFoods.filter((f) => !todayFoods.includes(f)).map((f) => (
                    <span key={f} className={`chip ${foodName === f ? "active" : ""}`}
                      onClick={() => setFoodName(f)}>{f}</span>
                  ))}
                </div>
              </details>
            )}
          </>
        ) : (
          <input value={foodName} onChange={(e) => setFoodName(e.target.value)}
            placeholder="输入食材名称"
            style={{ width: "100%", border: "1.5px solid #e8d5c8", borderRadius: 10, padding: "8px 12px", fontSize: 14 }} />
        )}

        <label className="fb-label">宝宝反应</label>
        <div className="chip-group" style={{ maxHeight: "none" }}>
          {[
            { key: "none", label: "✅ 无不良反应" },
            { key: "rash", label: "🔴 皮疹" },
            { key: "diarrhea", label: "💧 腹泻" },
            { key: "vomiting", label: "🤮 呕吐" },
            { key: "refusal", label: "🙅 拒食" },
            { key: "other", label: "❓ 其他" },
          ].map((r) => (
            <span key={r.key} className={`chip ${reaction === r.key ? "active" : ""}`}
              onClick={() => setReaction(r.key)}>{r.label}</span>
          ))}
        </div>

        {reaction !== "none" && (
          <>
            <label className="fb-label">严重程度</label>
            <div className="chip-group" style={{ maxHeight: "none" }}>
              {[
                { key: "mild", label: "🟡 轻度" },
                { key: "moderate", label: "🟠 中度" },
                { key: "severe", label: "🔴 重度" },
              ].map((s) => (
                <span key={s.key} className={`chip ${severity === s.key ? "active" : ""}`}
                  onClick={() => setSeverity(s.key)}>{s.label}</span>
              ))}
            </div>
          </>
        )}

        <label className="fb-label">备注（可选）</label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
          placeholder="如：吃完2小时后脸上出红点..."
          style={{ width: "100%", border: "1.5px solid #e8d5c8", borderRadius: 10, padding: "8px 12px", fontSize: 14, resize: "vertical", minHeight: 50, fontFamily: "inherit", boxSizing: "border-box" }} />

        {message && (
          <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 10, background: message.type === "success" ? "#e8f5e9" : "#ffebee", color: message.type === "success" ? "#2e7d32" : "#c62828", fontSize: 13 }}>
            {message.text}
          </div>
        )}

        <button className="btn-primary" onClick={submit} disabled={submitting || !foodName}
          style={{ marginTop: 14, width: "100%" }}>
          {submitting ? "提交中…" : "💾 提交反馈并刷新计划"}
        </button>
      </div>

      {/* 反馈历史 */}
      {feedbackHistory && feedbackHistory.total > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <b style={{ fontSize: 14 }}>📋 反馈记录（{feedbackHistory.total}条）</b>
          {feedbackHistory.avoid_foods?.length > 0 && (
            <p style={{ marginTop: 8, fontSize: 13, color: "#c62828" }}>🚫 已避免：{feedbackHistory.avoid_foods.join("、")}</p>
          )}
          {feedbackHistory.caution_foods?.length > 0 && (
            <p style={{ marginTop: 4, fontSize: 13, color: "#e65100" }}>⚠️ 需谨慎：{feedbackHistory.caution_foods.join("、")}</p>
          )}
          {feedbackHistory.by_reaction && (
            <p style={{ marginTop: 4, fontSize: 12, color: "#999" }}>
              {Object.entries(feedbackHistory.by_reaction).map(([k, v]) => `${k}:${v}次`).join(" · ")}
            </p>
          )}
        </div>
      )}
    </div>
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
    preterm: false,
  });
  const [assessment, setAssessment] = useState(null);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("plan");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const doAssess = async () => {
    setLoading(true);
    setError(null);
    setPlan(null);
    try {
      const r = await api.assess(profile);
      setAssessment(r);
      if (r.can_start) {
        setActiveTab("plan"); // 评估通过后自动跳到计划 Tab
        try {
          const planR = await api.plan(profile);
          setPlan(planR);
        } catch (e) {
          setError("计划生成失败：" + e.message);
        }
      } else {
        setActiveTab("stage"); // 未通过则跳到阶段判断 Tab
      }
    } catch (e) {
      setError("安全评估失败：" + e.message);
    }
    setLoading(false);
  };

  const doPlan = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.plan(profile);
      setPlan(r);
      setActiveTab("plan");
    } catch (e) {
      setError("计划生成失败：" + e.message);
    }
    setLoading(false);
  };

  return (
    <div className="app-container">
      <Sidebar profile={profile} setProfile={setProfile} onAssess={doAssess} />
      <main className="main-content">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h1 style={{ fontSize: 24, margin: 0, display: "flex", alignItems: "center", gap: 8 }}><img src="/logo.png" alt="logo" className="logo-img-small" />宝宝辅食助手</h1>
          <button className="settings-gear" onClick={() => setSettingsOpen(true)} title="LLM 设置">⚙️</button>
        </div>

        {loading && <p style={{ color: "#999", marginBottom: 16 }}>⏳ 宝宝在思考中...</p>}

        {error && (
          <div className="card" style={{ background: "#ffebee", color: "#c62828", marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>⚠️ {error}</span>
            <button onClick={() => setError(null)} style={{ cursor: "pointer", background: "none", border: "none", fontSize: 18, color: "#c62828" }}>✕</button>
          </div>
        )}

        {/* Tab 导航栏 */}
        <nav className="tab-bar">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`tab-btn ${activeTab === tab.key ? "active" : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
          <div className="tab-indicator" style={{ transform: `translateX(${TABS.findIndex((t) => t.key === activeTab) * 100}%)`, width: `${100 / TABS.length}%` }} />
        </nav>

        {/* Tab 内容区 */}
        <div className="tab-content" key={activeTab}>
          {activeTab === "stage" && <StageAssessment data={assessment} />}
          {activeTab === "foods" && <FoodSafetyTags data={assessment} />}
          {activeTab === "plan" && (
            assessment?.can_start
              ? (
                <>
                  <WeeklyPlan data={plan} onRefresh={doPlan} />
                  <DailyFeedback plan={plan} onFeedbackSubmit={doPlan} />
                </>
              )
              : (
                <div className="fade-in" style={{ textAlign: "center", padding: 40, color: "#999" }}>
                  <p style={{ marginBottom: 16 }}>👈 请先完成安全评估，再生成周度辅食计划</p>
                  <button className="btn-primary" onClick={doAssess} style={{ padding: "8px 24px", fontSize: 14 }}>🔍 开始评估</button>
                </div>
              )
          )}
          {activeTab === "label" && <LabelParser />}
        </div>
      </main>

      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <BossBabyChat />
    </div>
  );
}
