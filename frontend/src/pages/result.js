import { config } from "../config.js";
import { api, waitForJob } from "../api.js";
import { renderPositionChart, renderStrategyChart } from "../components/charts.js";
import { renderContextView } from "../components/contextView.js";
import { renderProgress } from "../components/progress.js";
import { driverCell, esc, paragraphs, pct, prefs } from "../util.js";

export async function pageResult(app, id, { navigate }) {
  const data = await api.result(id);
  const { result, context } = data;
  const sim = result.simulation;
  const laps = context?.circuit?.laps || sim.lap_chart.length;
  const isDemo = data.mode === "demo";

  const versions = data.versions.length > 1
    ? `<div class="version-tabs">${data.versions
        .map((v, i) => `<a href="#/r/${v.id}" class="${v.id === id ? "is-active" : ""}" title="${esc(v.prompt || "")}">${
          v.kind === "what_if" ? `What-if ${i}` : "Base race"}</a>`)
        .join("")}</div>`
    : "";
  const batchRuns = data.batch_runs?.length > 1
    ? `<div class="version-tabs">${data.batch_runs
        .map((rid, i) => `<a href="#/r/${rid}" class="${rid === id ? "is-active" : ""}">Run ${i + 1}</a>`)
        .join("")}</div>`
    : "";

  const strategies = Object.fromEntries(sim.strategies.map((s) => [s.driver, s]));
  const rows = sim.classification
    .map((c) => {
      const dnf = /^(DNF|DSQ)/i.test(c.status);
      const delta = c.grid - c.position;
      const move = dnf ? "" : delta > 0 ? `<span class="up">▲${delta}</span>` : delta < 0 ? `<span class="down">▼${-delta}</span>` : `<span class="muted">–</span>`;
      const stints = (strategies[c.driver]?.stints || [])
        .map((s) => `<i class="tyre" style="--compound:${config.compoundColors[s.compound]}" title="${s.compound}">${s.compound[0]}</i>`)
        .join("");
      return `<tr class="${dnf ? "dnf" : ""}">
        <td class="pos-cell">${c.position}</td><td>${driverCell(c.driver, c.team)}</td>
        <td class="mono">${c.grid || "PL"}</td><td>${move}</td><td class="mono">${esc(c.gap)}</td>
        <td class="nowrap">${stints}</td><td class="mono">${result.points[c.driver] || ""}</td>
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

  app.innerHTML = `
    ${versions}${batchRuns}
    <section class="card result-head">
      <div class="result-actions">
        <a class="btn-ghost small-btn" href="${api.exportUrl(id, "md")}">Export report (.md)</a>
        <a class="btn-ghost small-btn" href="${api.exportUrl(id, "json")}">Export data (.json)</a>
        <button class="btn-ghost small-btn" id="copy-link">Copy link</button>
        <button class="btn-ghost small-btn neg" id="delete">Delete</button>
      </div>
      <p class="eyebrow">${esc(data.year)} · ${esc(data.event_name)}${result.prompt ? ` · ${result.kind === "what_if" ? "what if: " : ""}${esc(result.prompt)}` : ""}</p>
      <h2 class="headline">${esc(sim.headline)}</h2>
      <p class="muted">${esc(sim.weather_summary)}</p>
      <div class="podium">${podium}</div>
      ${meta}
      ${result.issues.length ? `<details class="issues"><summary>${result.issues.length} consistency warning(s)</summary><ul>${result.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></details>` : ""}
    </section>

    ${data.batch ? renderMonteCarlo(data.batch) : ""}
    ${result.comparison ? renderComparison(result.comparison) : ""}
    ${renderWhatIfBox(data, isDemo)}
    <section id="progress"></section>

    <div class="grid cols-2 sim-grid">
      <section class="card"><h3>Classification</h3>
        <div class="table-scroll"><table class="results-table compact"><thead><tr><th>Pos</th><th>Driver</th><th>Grid</th><th>+/-</th><th>Gap</th><th>Tyres</th><th>Pts</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
      </section>
      <section class="card"><h3>Strategy brief</h3>${insights}</section>
    </div>

    <section class="card"><h3>Lap chart</h3><div class="chart-container chart-tall"><canvas id="position-chart"></canvas></div></section>
    <section class="card"><h3>Tyre strategies <span class="muted small">— click a driver for pit calls</span></h3><div id="strategy-chart" class="strategy-chart"></div></section>

    <div class="grid cols-2 sim-grid">
      <section class="card"><h3>Key moments</h3><ol class="events">${events}</ol></section>
      <section class="card"><h3>Race report</h3><div class="narrative">${paragraphs(sim.narrative)}</div>
        <h3 class="spaced">Race pace</h3>
        <div class="table-scroll"><table class="results-table compact"><thead><tr><th>Driver</th><th>Δ pace</th><th>Deg</th><th></th></tr></thead><tbody>${pace}</tbody></table></div>
        ${sim.assumptions.length ? `<h3 class="spaced">Assumptions</h3><ul class="assumptions">${sim.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}
      </section>
    </div>

    ${context ? `<details class="card ctx-details"><summary><h3>Race data used</h3></summary><div id="ctx"></div></details>` : ""}`;

  renderPositionChart(app.querySelector("#position-chart"), sim);
  renderStrategyChart(app.querySelector("#strategy-chart"), sim, laps);
  if (context) renderContextView(app.querySelector("#ctx"), context);

  app.querySelector("#copy-link").addEventListener("click", async (e) => {
    try {
      await navigator.clipboard.writeText(location.href);
      e.target.textContent = "Copied";
    } catch {
      e.target.textContent = location.href;
    }
  });
  app.querySelector("#delete").addEventListener("click", async () => {
    if (!confirm("Delete this simulation?")) return;
    await api.deleteResult(id);
    navigate("#/history");
  });

  const form = app.querySelector("#whatif-form");
  if (!form) return;
  form.querySelectorAll(".chip").forEach((chip) =>
    chip.addEventListener("click", () => (form.querySelector("input").value = chip.dataset.text))
  );
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = form.querySelector("input").value.trim();
    if (!question) return;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    const progress = app.querySelector("#progress");
    try {
      const job = await api.whatIf(data.session_id, question);
      prefs.set("activeJob", { id: job.id, title: `What if… ${question}` });
      const done = await waitForJob(job.id, (j) => renderProgress(progress, j, `What if… ${question}`));
      navigate(`#/r/${done.output.result_id}`);
    } catch (err) {
      progress.innerHTML = `<div class="error">What-if failed: ${esc(err.message)}</div>`;
      button.disabled = false;
    } finally {
      prefs.set("activeJob", null);
    }
  });
}

function renderWhatIfBox(data, isDemo) {
  if (!data.can_what_if) {
    const why = isDemo ? "What-ifs need AI mode (set ANTHROPIC_API_KEY and restart the server)." : "What-ifs need AI mode.";
    return `<section class="card whatif muted small">${why}</section>`;
  }
  return `
    <section class="card whatif">
      <h3>Ask a what-if</h3>
      <form id="whatif-form">
        <input type="text" placeholder="What if NOR had pitted under the safety car?" />
        <button class="btn-primary" type="submit">Re-simulate</button>
      </form>
      <div class="chips">${config.whatIfPresets.map((p) => `<button type="button" class="chip" data-text="${esc(p)}">${esc(p)}</button>`).join("")}</div>
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
  return `<section class="card"><h3>Outcome probabilities · ${mc.runs} independent runs</h3>
    <div class="table-scroll"><table class="results-table compact mc"><thead><tr><th>Driver</th><th>Win</th><th>Podium</th><th>Points</th><th>DNF</th><th>Avg pos</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
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
