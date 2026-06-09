const BASE = "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  health: () => request("/api/health"),

  assess: (profile) =>
    request("/api/assess", {
      method: "POST",
      body: JSON.stringify({ profile }),
    }),

  plan: (profile) =>
    request("/api/plan", {
      method: "POST",
      body: JSON.stringify({ profile }),
    }),

  parseLabel: (text, age) =>
    request("/api/parse-label", {
      method: "POST",
      body: JSON.stringify({ ingredient_text: text, age_months: age }),
    }),

  chat: (message, history, current_profile) =>
    request("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, history, current_profile }),
    }),

  feedback: {
    submit: (data) =>
      request("/api/feedback", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    get: () => request("/api/feedback"),
    clear: () => request("/api/feedback", { method: "DELETE" }),
  },

  settings: {
    getLLM: () => request("/api/settings/llm"),
    saveLLM: (data) =>
      request("/api/settings/llm", {
        method: "POST",
        body: JSON.stringify(data),
      }),
  },
};
