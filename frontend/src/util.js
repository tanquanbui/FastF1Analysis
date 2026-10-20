import { config } from "./config.js";

// Model output is untrusted text: always escape before putting it in HTML.
export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function pct(p) {
  return `${Math.round((p || 0) * 100)}%`;
}

export function paragraphs(text) {
  return String(text || "")
    .split(/\n{2,}/)
    .map((p) => `<p>${esc(p.trim())}</p>`)
    .join("");
}

export function driverCell(code, team) {
  const color = config.teamColors[team] || "#8a8a9a";
  return `<span class="drv"><i style="background:${color}"></i>${esc(code)}<small>${esc(team || "")}</small></span>`;
}

export function timeAgo(epochSeconds) {
  const s = Math.max(0, Date.now() / 1000 - epochSeconds);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(epochSeconds * 1000).toLocaleDateString();
}

// Per-viewer convenience only; the app works without it.
export const prefs = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(`pitstop.${key}`);
      return v == null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(`pitstop.${key}`, JSON.stringify(value));
    } catch {
      /* storage unavailable */
    }
  },
};
