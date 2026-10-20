import { config } from "./config.js";

async function request(path, options = {}) {
  const response = await fetch(`${config.apiBase}${path}`, {
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(body.error || `${response.status} ${response.statusText}`);
    err.status = response.status;
    throw err;
  }
  return body;
}

const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  status: () => request("/api/status"),
  seasons: () => request("/api/seasons"),
  calendar: (year) => request(`/api/calendar/${year}`),
  context: (year, round, source) => request(`/api/context/${year}/${round}?source=${source}`),
  prepare: (params) => post("/api/prepare", params),
  simulate: (params) => post("/api/simulate", params),
  whatIf: (sessionId, question) => post("/api/whatif", { session_id: sessionId, question }),
  job: (id) => request(`/api/jobs/${id}`),
  history: () => request("/api/history"),
  result: (id) => request(`/api/results/${id}`),
  deleteResult: (id) => request(`/api/results/${id}`, { method: "DELETE" }),
  exportUrl: (id, format) => `${config.apiBase}/api/results/${id}/export.${format}`,
};

// Poll a background job until it finishes; onUpdate gets every snapshot.
export async function waitForJob(jobId, onUpdate, intervalMs = 1000) {
  for (;;) {
    const job = await api.job(jobId);
    onUpdate?.(job);
    if (job.state === "done") return job;
    if (job.state === "error") throw new Error(job.error || "job failed");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
