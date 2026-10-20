import { config } from "./config.js";
import { api } from "./api.js";
import { renderPositionChart, renderStrategyChart } from "./sim/charts.js";
import { esc, paragraphs, pct } from "./sim/util.js";

const app = document.getElementById("app");

const state = {
  status: null,
  year: config.defaultSeason,
  round: 1,
  source: "auto",
  calendar: [],
  context: null,
  sessionId: null,
  versions: [], // [{ label, result, monteCarlo }]
  active: 0,
  busy: false,
};

const SOURCES = [
  ["auto", "Auto (FastF1 → stored data → AI knowledge)"],
  ["fastf1", "FastF1 live data"],
  ["fixtures", "Stored data (local fixtures)"],
  ["model", "AI knowledge only"],
];

// ---------- shell ----------
function renderShell() {
  app.innerHTML = `
    <p class="eyebrow">AI RACE SIMULATOR</p>
    <h1 class="page-title">Simulate the <span class="accent-soft">race</span></h1>
    <p class="page-subtitle">Pick a Grand Prix, set a scenario, and Claude plays it out lap by lap: pace, tyres, strategy calls, safety cars and the result. Then ask what-ifs.</p>

    <section class="card sim-setup">
      <div class="setup-grid">
        <label>Season
          <select id="year">${config.seasons.map((y) => `<option ${y === state.year ? "selected" : ""}>${y}</option>`).join("")}</select>
        </label>
        <label>Grand Prix
          <select id="round"></select>
        </label>
        <label>Race data
          <select id="source">${SOURCES.map(([v, l]) => `<option value="${v}" ${v === state.source ? "selected" : ""}>${l}</option>`).join("")}</select>
        </label>
        <label>Runs
          <select id="runs">
            <option value="1">1 — single race + what-ifs</option>
            <option value="3">3 — probabilities</option>
            <option value="5">5 — probabilities</option>
          </select>
        </label>
      </div>
      <label class="scenario-label">Scenario — optional
        <textarea id="scenario" rows="2" placeholder="e.g. Rain arrives on lap 30 and lasts 10 laps"></textarea>
      </label>
      <div class="chips" id="presets">
        ${config.presets.map((p) => `<button type="button" class="chip" data-text="${esc(p)}">${esc(p)}</button>`).join("")}
      </div>
      <div class="setup-actions">
        <button id="run" class="btn-primary">Simulate race</button>
        <button id="show-context" class="btn-ghost" type="button">Race context</button>
        <span id="setup-note" class="muted small"></span>
      </div>
      <div id="context-panel" class="context-panel" hidden></div>
    </section>

    <section id="results"></section>
  `;

  app.querySelector("#year").addEventListener("change", async (e) => {
    state.year = Number(e.target.value);
    await loadCalendar();
  });
  app.querySelector("#round").addEventListener("change", (e) => {
    state.round = Number(e.target.value);
    state.context = null;
    hideContext();
  });
  app.querySelector("#source").addEventListener("change", (e) => {
    state.source = e.target.value;
    state.context = null;
    hideContext();
  });
  app.querySelector("#presets").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) app.querySelector("#scenario").value = chip.dataset.text;
  });
  app.querySelector("#run").addEventListener("click", runSimulation);
  app.querySelector("#show-context").addEventListener("click", toggleContext);
}

async function loadCalendar() {
  state.calendar = await api.calendar(state.year);
  state.round = state.calendar[0]?.round || 1;
  state.context = null;
  hideContext();
  app.querySelector("#round").innerHTML = state.calendar
    .map((r) => `<option value="${r.round}">R${r.round} · ${esc(r.event_name)}</option>`)
    .join("");
}

// ---------- context preview ----------
function hideContext() {
  const panel = app.querySelector("#context-panel");
  if (panel) panel.hidden = true;
}

async function toggleContext() {
  const panel = app.querySelector("#context-panel");
  if (!panel.hidden) return hideContext();
  panel.hidden = false;
  panel.innerHTML = `<div class="loader small-loader"><div class="spinner"></div><p>Loading race data…</p></div>`;
  try {
    state.context = await api.context(state.year, state.round, state.source);
    panel.innerHTML = renderContext(state.context);
  } catch (err) {
    panel.innerHTML = `<div class="error">Could not load race data: ${esc(err.message)}</div>`;
  }
}

function renderContext(ctx) {
  const c = ctx.circuit;
  const facts = [
    ["Laps", `${c.laps} × ${c.length_km} km`],
    ["Pit loss", `~${Math.round(c.pit_loss_s)}s`],
    ["Overtaking", c.overtaking],
    ["SC likelihood", pct(c.sc_probability)],
    ["Tyre stress", c.tyre_stress],
    ["Compounds", c.compounds],
  ];
  const rows = ctx.drivers
    .slice()
    .sort((a, b) => (a.grid ?? 99) - (b.grid ?? 99))
    .map(
      (d) => `<tr><td>${d.grid ?? "–"}</td><td>${driverCell(d.code, d.team)}</td><td>${esc(d.name || "")}</td>
        <td class="mono">${d.quali_gap_s != null ? `+${d.quali_gap_s.toFixed(3)}` : "–"}</td>
        <td class="mono">${d.long_run_pace_s != null ? `${d.long_run_pace_s.toFixed(3)} (${esc(d.long_run_compound || "?")})` : "–"}</td></tr>`
    )
    .join("");
  return `
    <h3>${esc(c.name)} · ${esc(ctx.event_name)}</h3>
    <div class="fact-row">${facts.map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join("")}</div>
    <p class="muted small">${esc(c.notes)}${ctx.weather ? ` · Conditions: ${esc(ctx.weather)}` : ""}</p>
    ${
      rows
        ? `<table class="results-table compact"><thead><tr><th>Grid</th><th>Driver</th><th></th><th>Quali gap</th><th>Long run</th></tr></thead><tbody>${rows}</tbody></table>`
        : `<p class="muted">No entry list in the data. Claude will use its knowledge of the ${ctx.year} field.</p>`
    }
    ${ctx.extra_notes.map((n) => `<p class="muted small">⚠ ${esc(n)}</p>`).join("")}
    <p class="muted small">Sources: ${ctx.data_sources.map(esc).join(", ")}</p>`;
}

// ---------- running ----------
function setBusy(busy, message = "") {
  state.busy = busy;
  app.querySelectorAll("#run, #whatif-run").forEach((b) => (b.disabled = busy));
  if (!busy) return;
  const results = app.querySelector("#results");
  const started = Date.now();
  const holder = document.createElement("div");
  holder.className = "card sim-running";
  holder.innerHTML = `
    <div class="race-lights">${"<span></span>".repeat(5)}</div>
    <p>${esc(message)}</p>
    <p class="muted small"><span id="elapsed">0</span>s · a full race simulation usually takes 1–3 minutes</p>`;
  results.prepend(holder);
  const timer = setInterval(() => {
    const el = holder.querySelector("#elapsed");
    if (!el || !state.busy) return clearInterval(timer);
    el.textContent = Math.round((Date.now() - started) / 1000);
  }, 1000);
}

async function runSimulation() {
  if (state.busy) return;
  const scenario = app.querySelector("#scenario").value.trim();
  const runs = Number(app.querySelector("#runs").value);
  const race = state.calendar.find((r) => r.round === state.round);
  setBusy(true, `Simulating the ${state.year} ${race?.event_name || "race"}${runs > 1 ? ` × ${runs} runs` : ""}…`);
  try {
    const res = await api.simulate({ year: state.year, round: state.round, source: state.source, scenario, runs });
    state.context = res.context;
    state.sessionId = runs === 1 && res.mode === "ai" ? res.result.session_id : null;
    state.versions = [{ label: scenario ? "Scenario" : "Base race", result: res.result, monteCarlo: res.monte_carlo, runs: res.runs }];
    state.active = 0;
  } catch (err) {
    setBusy(false);
    app.querySelector("#results").innerHTML = `<div class="error">Simulation failed: ${esc(err.message)}</div>`;
    return;
  }
  setBusy(false);
  renderResults();
}

async function runWhatIf(question) {
  if (state.busy || !question) return;
  setBusy(true, `What if… ${question}`);
  try {
    const res = await api.whatIf(state.sessionId, question);
    state.versions.push({ label: `What-if ${state.versions.length}`, result: res.result });
    state.active = state.versions.length - 1;
  } catch (err) {
    setBusy(false);
    renderResults();
    app.querySelector("#whatif-error").textContent = err.message;
    return;
  }
  setBusy(false);
  renderResults();
}

// ---------- results ----------
function driverCell(code, team) {
  const color = config.teamColors[team] || "#8a8a9a";
  return `<span class="drv"><i style="background:${color}"></i>${esc(code)}<small>${esc(team || "")}</small></span>`;
}

function renderResults() {
  const v = state.versions[state.active];
  if (!v) return;
  const { result } = v;
  const sim = result.simulation;
  const laps = state.context?.circuit?.laps || sim.lap_chart.length;
  const isDemo = result.model.startsWith("demo");

  const tabs =
    state.versions.length > 1
      ? `<div class="version-tabs">${state.versions
          .map((ver, i) => `<button class="${i === state.active ? "is-active" : ""}" data-idx="${i}" title="${esc(ver.result.prompt || "")}">${esc(ver.label)}</button>`)
          .join("")}</div>`
      : "";

  const strategies = Object.fromEntries(sim.strategies.map((s) => [s.driver, s]));
  const rows = sim.classification
    .map((c) => {
      const delta = c.grid - c.position;
      const move = c.status.toUpperCase().startsWith("DNF") ? "" : delta > 0 ? `<span class="up">▲${delta}</span>` : delta < 0 ? `<span class="down">▼${-delta}</span>` : `<span class="muted">–</span>`;
      const stints = (strategies[c.driver]?.stints || [])
        .map((s) => `<i class="tyre" style="--compound:${config.compoundColors[s.compound]}" title="${s.compound}">${s.compound[0]}</i>`)
        .join("");
      return `<tr class="${c.status.toUpperCase().startsWith("DNF") ? "dnf" : ""}">
        <td class="pos-cell">${c.position}</td><td>${driverCell(c.driver, c.team)}</td>
        <td class="mono">${c.grid}</td><td>${move}</td><td class="mono">${esc(c.gap)}</td>
        <td>${stints}</td><td class="mono">${result.points[c.driver] || ""}</td>
        <td>${c.fastest_lap ? '<span class="pill">FL</span>' : ""}${c.status.startsWith("Finished") ? "" : `<span class="muted small">${esc(c.status)}</span>`}</td></tr>`;
    })
    .join("");

  const podium = sim.classification
    .slice(0, 3)
    .map((c) => `<div class="podium-step p${c.position}"><span>P${c.position}</span>${driverCell(c.driver, c.team)}<small class="mono">${esc(c.gap)}</small></div>`)
    .join("");

  const events = sim.events
    .map((e) => `<li class="ev ev-${e.type.toLowerCase()}"><span class="ev-lap">L${e.lap}</span><span class="ev-type">${e.type.replace(/_/g, " ")}</span><span>${esc(e.description)}</span></li>`)
    .join("");

  const insights = sim.insights.map((i) => `<div class="insight"><h4>${esc(i.title)}</h4><p>${esc(i.detail)}</p></div>`).join("");

  const pace = sim.pace
    .slice()
    .sort((a, b) => a.race_pace_delta_s - b.race_pace_delta_s)
    .map((p) => `<tr><td>${esc(p.driver)}</td><td class="mono">+${p.race_pace_delta_s.toFixed(3)}s</td><td>${p.tyre_deg}</td><td class="muted small">${esc(p.comment)}</td></tr>`)
    .join("");

  const u = result.usage;
  const meta = isDemo
    ? `<span class="pill pill-warn">DEMO — offline pace model, not AI. Set ANTHROPIC_API_KEY for Claude simulations.</span>`
    : `<span class="muted small mono">${esc(result.model)} · ${u.input_tokens + u.cache_read_input_tokens} in / ${u.output_tokens} out tokens</span>`;

  app.querySelector("#results").innerHTML = `
    ${tabs}
    <section class="card result-head">
      <p class="eyebrow">${esc(state.context?.year)} · ${esc(state.context?.event_name)}${result.prompt ? ` · ${esc(result.prompt)}` : ""}</p>
      <h2 class="headline">${esc(sim.headline)}</h2>
      <p class="muted">${esc(sim.weather_summary)}</p>
      <div class="podium">${podium}</div>
      ${meta}
      ${result.issues.length ? `<details class="issues"><summary>${result.issues.length} consistency warning(s)</summary><ul>${result.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></details>` : ""}
    </section>

    ${v.monteCarlo ? renderMonteCarlo(v.monteCarlo) : ""}
    ${result.comparison ? renderComparison(result.comparison) : ""}

    ${renderWhatIfBox(isDemo)}

    <div class="grid cols-2 sim-grid">
      <section class="card"><h3>Classification</h3>
        <table class="results-table compact"><thead><tr><th>Pos</th><th>Driver</th><th>Grid</th><th>+/-</th><th>Gap</th><th>Tyres</th><th>Pts</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      </section>
      <section class="card"><h3>Strategy brief</h3>${insights}</section>
    </div>

    <section class="card"><h3>Lap chart</h3><div class="chart-container chart-tall"><canvas id="position-chart"></canvas></div></section>

    <section class="card"><h3>Tyre strategies <span class="muted small">— click a driver for pit calls</span></h3><div id="strategy-chart" class="strategy-chart"></div></section>

    <div class="grid cols-2 sim-grid">
      <section class="card"><h3>Key moments</h3><ol class="events">${events}</ol></section>
      <section class="card"><h3>Race report</h3><div class="narrative">${paragraphs(sim.narrative)}</div>
        <h3 class="spaced">Race pace</h3>
        <table class="results-table compact"><thead><tr><th>Driver</th><th>Δ pace</th><th>Deg</th><th></th></tr></thead><tbody>${pace}</tbody></table>
        ${sim.assumptions.length ? `<h3 class="spaced">Assumptions</h3><ul class="assumptions">${sim.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}
      </section>
    </div>`;

  renderPositionChart(app.querySelector("#position-chart"), sim);
  renderStrategyChart(app.querySelector("#strategy-chart"), sim, laps);

  app.querySelectorAll(".version-tabs button").forEach((b) =>
    b.addEventListener("click", () => {
      state.active = Number(b.dataset.idx);
      renderResults();
    })
  );
  const form = app.querySelector("#whatif-form");
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      runWhatIf(form.querySelector("input").value.trim());
    });
    form.querySelectorAll(".chip").forEach((chip) =>
      chip.addEventListener("click", () => (form.querySelector("input").value = chip.dataset.text))
    );
  }
}

function renderWhatIfBox(isDemo) {
  if (!state.sessionId) {
    const why = isDemo ? "What-ifs need AI mode." : "What-ifs are available on single-run simulations.";
    return `<section class="card whatif muted small">${why}</section>`;
  }
  return `
    <section class="card whatif">
      <h3>Ask a what-if</h3>
      <form id="whatif-form">
        <input type="text" placeholder="What if NOR had pitted under the safety car?" />
        <button id="whatif-run" class="btn-primary" type="submit">Re-simulate</button>
      </form>
      <div class="chips">${config.whatIfPresets.map((p) => `<button type="button" class="chip" data-text="${esc(p)}">${esc(p)}</button>`).join("")}</div>
      <p id="whatif-error" class="neg small"></p>
    </section>`;
}

function renderMonteCarlo(mc) {
  const rows = Object.entries(mc.average_finish)
    .map(
      ([d, avg]) => `<tr><td>${esc(d)}</td>
        <td><span class="bar" style="--w:${pct(mc.win_probability[d])}"></span>${pct(mc.win_probability[d])}</td>
        <td><span class="bar" style="--w:${pct(mc.podium_probability[d])}"></span>${pct(mc.podium_probability[d])}</td>
        <td>${pct(mc.points_probability[d])}</td><td>${pct(mc.dnf_probability[d])}</td><td class="mono">${avg.toFixed(1)}</td></tr>`
    )
    .join("");
  return `<section class="card"><h3>Outcome probabilities · ${mc.runs} independent runs <span class="muted small">— details below are from run 1</span></h3>
    <table class="results-table compact mc"><thead><tr><th>Driver</th><th>Win</th><th>Podium</th><th>Points</th><th>DNF</th><th>Avg pos</th></tr></thead><tbody>${rows}</tbody></table></section>`;
}

function renderComparison(c) {
  return `<section class="card comparison">
    <h3>vs the real race</h3>
    <div class="fact-row">
      <div><span>Winner</span><b class="${c.winner_correct ? "up" : "down"}">${c.winner_correct ? "Correct" : `Actual: ${esc(c.actual_order[0])}`}</b></div>
      <div><span>Podium overlap</span><b>${c.podium_overlap}/3</b></div>
      <div><span>Mean position error</span><b>${c.mean_abs_position_error}</b></div>
      <div><span>Actual top 5</span><b class="mono">${c.actual_order.slice(0, 5).map(esc).join(" · ")}</b></div>
    </div></section>`;
}

// ---------- boot ----------
async function boot() {
  renderShell();
  try {
    state.status = await api.status();
    const badge = document.getElementById("mode-badge");
    badge.textContent = state.status.ai_available ? `AI · ${state.status.model}` : "DEMO MODE";
    badge.classList.toggle("demo", !state.status.ai_available);
    if (!state.status.ai_available) {
      app.querySelector("#setup-note").textContent =
        "Demo mode: no ANTHROPIC_API_KEY on the server, so results come from a simple offline model.";
    }
    await loadCalendar();
  } catch (err) {
    app.innerHTML = `<section class="error">Can't reach the simulator server (${esc(err.message)}). Start it with <code>python -m simulator.server</code>.</section>`;
  }
}

boot();
