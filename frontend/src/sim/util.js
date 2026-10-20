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
