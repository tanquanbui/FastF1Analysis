import { config } from "../config.js";
import { api, waitForJob } from "../api.js";
import { renderContextView } from "../components/contextView.js";
import { renderProgress } from "../components/progress.js";
import { esc, prefs } from "../util.js";

const SOURCES = [
  ["auto", "Auto — FastF1, then stored data, then AI knowledge"],
  ["fastf1", "FastF1 full weekend"],
  ["fixtures", "Stored data (local fixtures)"],
  ["model", "AI knowledge only"],
];

export async function pageNewSim(app, { status, navigate }) {
  const seasons = await api.seasons();
  const state = {
    year: prefs.get("year", config.defaultSeason),
    round: prefs.get("round", 1),
    source: prefs.get("source", "auto"),
    calendar: [],
    busy: false,
  };
  if (!seasons.includes(state.year)) state.year = seasons[0];

  app.innerHTML = `
    <p class="eyebrow">AI RACE SIMULATOR</p>
    <h1 class="page-title">Simulate the <span class="accent-soft">race</span></h1>
    <p class="page-subtitle">Load a Grand Prix weekend from FastF1 — every session, long runs, tyre deg, penalties, standings and past races here — then let Claude play the race out lap by lap and ask what-ifs.</p>

    <section class="card sim-setup">
      <div class="setup-grid">
        <label>Season<select id="year">${seasons.map((y) => `<option ${y === state.year ? "selected" : ""}>${y}</option>`).join("")}</select></label>
        <label>Grand Prix<select id="round"></select></label>
        <label>Race data<select id="source">${SOURCES.map(([v, l]) => `<option value="${v}" ${v === state.source ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label>Runs<select id="runs">
          <option value="1">1 — one race + what-ifs</option>
          <option value="3">3 — outcome probabilities</option>
          <option value="5">5 — outcome probabilities</option>
        </select></label>
      </div>
      <label>Scenario — optional<textarea id="scenario" rows="2" placeholder="e.g. Rain arrives on lap 30 and lasts 10 laps"></textarea></label>
      <div class="chips" id="presets">${config.presets.map((p) => `<button type="button" class="chip" data-text="${esc(p)}">${esc(p)}</button>`).join("")}</div>
      <div class="setup-actions">
        <button id="run" class="btn-primary">Simulate race</button>
        <button id="load" class="btn-ghost" type="button">Load race data</button>
        <span id="data-state" class="muted small"></span>
      </div>
      ${status.ai_available ? "" : `<p class="pill pill-warn">Demo mode — no ANTHROPIC_API_KEY on the server, so results come from a simple offline model.</p>`}
    </section>

    <section id="progress"></section>
    <section id="context" class="card" hidden></section>`;

  const $ = (sel) => app.querySelector(sel);

  async function loadCalendar() {
    state.calendar = await api.calendar(state.year);
    if (!state.calendar.some((r) => r.round === state.round)) state.round = state.calendar[0]?.round || 1;
    $("#round").innerHTML = state.calendar
      .map((r) => {
        const cached = r.cached_sources.length ? " ✓" : "";
        return `<option value="${r.round}" ${r.round === state.round ? "selected" : ""}>R${r.round} · ${esc(r.event_name)}${cached}</option>`;
      })
      .join("");
    await showContext();
  }

  async function showContext() {
    prefs.set("year", state.year);
    prefs.set("round", state.round);
    prefs.set("source", state.source);
    const panel = $("#context");
    try {
      const ctx = await api.context(state.year, state.round, state.source);
      panel.hidden = false;
      renderContextView(panel, ctx, { prompt: ctx.prompt });
      $("#data-state").textContent = `Race data loaded · ${ctx.tables.length} tables`;
      $("#load").textContent = "Reload race data";
    } catch (err) {
      panel.hidden = true;
      $("#load").textContent = "Load race data";
      $("#data-state").textContent =
        err.status === 404 ? "Race data not loaded yet — it loads automatically when you simulate." : err.message;
    }
  }

  async function runJob(jobPromise, title) {
    if (state.busy) return null;
    state.busy = true;
    app.querySelectorAll("#run, #load").forEach((b) => (b.disabled = true));
    const progress = $("#progress");
    try {
      const job = await jobPromise;
      prefs.set("activeJob", { id: job.id, title });
      return await waitForJob(job.id, (j) => renderProgress(progress, j, title));
    } catch (err) {
      progress.innerHTML = `<div class="error">${esc(title)} failed: ${esc(err.message)}</div>`;
      return null;
    } finally {
      prefs.set("activeJob", null);
      state.busy = false;
      app.querySelectorAll("#run, #load").forEach((b) => (b.disabled = false));
    }
  }

  $("#year").addEventListener("change", (e) => {
    state.year = Number(e.target.value);
    loadCalendar();
  });
  $("#round").addEventListener("change", (e) => {
    state.round = Number(e.target.value);
    showContext();
  });
  $("#source").addEventListener("change", (e) => {
    state.source = e.target.value;
    showContext();
  });
  $("#presets").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) $("#scenario").value = chip.dataset.text;
  });
  $("#load").addEventListener("click", async () => {
    const refresh = $("#load").textContent.startsWith("Reload");
    const job = await runJob(
      api.prepare({ year: state.year, round: state.round, source: state.source, refresh }),
      "Loading race data"
    );
    if (job) {
      $("#progress").innerHTML = "";
      await loadCalendar();
    }
  });
  $("#run").addEventListener("click", async () => {
    const race = state.calendar.find((r) => r.round === state.round);
    const runs = Number($("#runs").value);
    const scenario = $("#scenario").value.trim();
    const title = `Simulating the ${state.year} ${race?.event_name || "race"}${runs > 1 ? ` × ${runs}` : ""}`;
    const job = await runJob(api.simulate({ year: state.year, round: state.round, source: state.source, scenario, runs }), title);
    if (job) navigate(`#/r/${job.output.result_id}`);
  });

  await loadCalendar();
  await resumeActiveJob(app, navigate);
}

// After a page reload, keep showing a job that's still running.
async function resumeActiveJob(app, navigate) {
  const active = prefs.get("activeJob", null);
  if (!active) return;
  try {
    const job = await waitForJob(active.id, (j) => renderProgress(app.querySelector("#progress"), j, active.title));
    prefs.set("activeJob", null);
    if (job.output?.result_id) navigate(`#/r/${job.output.result_id}`);
    else app.querySelector("#progress").innerHTML = "";
  } catch {
    prefs.set("activeJob", null);
    const el = app.querySelector("#progress");
    if (el) el.innerHTML = "";
  }
}
