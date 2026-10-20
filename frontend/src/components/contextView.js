import { config } from "../config.js";
import { driverCell, esc, pct } from "../util.js";

const SECTIONS = [
  ["entry", "Grid"],
  ["weekend", "This weekend"],
  ["season", "Season"],
  ["history", "History here"],
  ["prompt", "What Claude sees"],
];

// Race-data explorer: circuit facts + every table the simulator feeds Claude.
export function renderContextView(el, ctx, { prompt } = {}) {
  const c = ctx.circuit;
  const facts = [
    ["Laps", `${c.laps} × ${c.length_km} km`],
    ["Pit loss", `~${Math.round(c.pit_loss_s)}s`],
    ["Overtaking", c.overtaking],
    ["SC likelihood", pct(c.sc_probability)],
    ["Tyre stress", c.tyre_stress],
    ["Compounds", c.compounds],
  ];
  const present = SECTIONS.filter(([key]) =>
    key === "entry" || (key === "prompt" ? !!prompt : ctx.tables.some((t) => t.section === key))
  );
  el.innerHTML = `
    <div class="ctx-head">
      <div>
        <h3>${esc(c.name)} · ${esc(ctx.year)} ${esc(ctx.event_name)}</h3>
        <p class="muted small">${esc(c.notes)}${ctx.weather ? ` · ${esc(ctx.weather)}` : ""}</p>
      </div>
      <span class="muted small">${ctx.tables.length} data tables · ${esc(ctx.data_sources.join(", "))}</span>
    </div>
    <div class="fact-row">${facts.map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join("")}</div>
    ${ctx.extra_notes.map((n) => `<p class="muted small">⚠ ${esc(n)}</p>`).join("")}
    <div class="ctx-tabs">${present
      .map(([key, label], i) => `<button data-tab="${key}" class="${i === 0 ? "is-active" : ""}">${label}</button>`)
      .join("")}</div>
    <div class="ctx-body"></div>`;

  const body = el.querySelector(".ctx-body");
  const show = (key) => {
    el.querySelectorAll(".ctx-tabs button").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === key));
    if (key === "entry") body.innerHTML = entryTable(ctx);
    else if (key === "prompt") body.innerHTML = `<pre class="prompt">${esc(prompt)}</pre>`;
    else body.innerHTML = ctx.tables.filter((t) => t.section === key).map(dataTable).join("");
  };
  el.querySelectorAll(".ctx-tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  show("entry");
}

function entryTable(ctx) {
  if (!ctx.drivers.length) {
    return `<p class="muted">No entry list in the data — Claude will use its knowledge of the ${ctx.year} field.</p>`;
  }
  const rows = ctx.drivers
    .slice()
    .sort((a, b) => (a.grid ?? 99) - (b.grid ?? 99))
    .map(
      (d) => `<tr><td>${d.grid ?? "PL"}</td><td>${driverCell(d.code, d.team)}</td><td>${esc(d.name || "")}</td>
        <td class="mono">${d.quali_gap_s != null ? `+${d.quali_gap_s.toFixed(3)}` : "–"}</td>
        <td class="mono">${d.long_run_pace_s != null ? `${d.long_run_pace_s.toFixed(3)}` : "–"}
          ${d.long_run_compound ? `<i class="tyre" style="--compound:${config.compoundColors[d.long_run_compound] || "#888"}">${esc(d.long_run_compound[0])}</i>` : ""}</td>
        <td class="muted small">${esc(d.notes || "")}</td></tr>`
    )
    .join("");
  return `<div class="table-scroll"><table class="results-table compact">
    <thead><tr><th>Grid</th><th>Driver</th><th></th><th>Quali gap</th><th>Long run</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function dataTable(t) {
  const head = t.columns.map((c) => `<th>${esc(c)}</th>`).join("");
  const rows = t.rows.map((r) => `<tr>${r.map((v) => `<td>${esc(v ?? "–")}</td>`).join("")}</tr>`).join("");
  return `<div class="data-table">
    <h4>${esc(t.title)}</h4>
    <div class="table-scroll"><table class="results-table compact"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>
    ${t.note ? `<p class="muted small">${esc(t.note)}</p>` : ""}
  </div>`;
}
