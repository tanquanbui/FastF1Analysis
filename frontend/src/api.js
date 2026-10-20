import { config } from "./config.js";

async function request(path, options = {}) {
  const response = await fetch(`${config.apiBase}${path}`, {
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `${response.status} ${response.statusText}`);
  }
  return body;
}

const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  status: () => request("/api/status"),
  calendar: (year) => request(`/api/calendar/${year}`),
  context: (year, round, source) => request(`/api/context/${year}/${round}?source=${source}`),
  simulate: (params) => post("/api/simulate", params),
  whatIf: (sessionId, question) => post("/api/whatif", { session_id: sessionId, question }),
};
