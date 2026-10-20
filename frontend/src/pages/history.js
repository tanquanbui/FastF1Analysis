import { api } from "../api.js";
import { esc, timeAgo } from "../util.js";

export async function pageHistory(app, { navigate }) {
  const rows = await api.history();
  app.innerHTML = `
    <p class="eyebrow">SAVED SIMULATIONS</p>
    <h1 class="page-title">History</h1>
    <p class="page-subtitle">Every simulation and what-if you've run, stored locally in data/simulator.db.</p>
    <section class="card">
      <input id="filter" class="filter" type="search" placeholder="Filter by race, driver, scenario…" />
      <div class="table-scroll"><table class="results-table history-table">
        <thead><tr><th>When</th><th>Race</th><th>Type</th><th>Scenario / question</th><th>Result</th><th>Mode</th><th></th></tr></thead>
        <tbody id="rows"></tbody>
      </table></div>
      <p id="empty" class="muted" hidden>No simulations yet. <a href="#/">Run your first one →</a></p>
    </section>`;

  const tbody = app.querySelector("#rows");
  const render = (filter = "") => {
    const f = filter.toLowerCase();
    const shown = rows.filter((r) =>
      [r.event_name, r.prompt, r.headline, r.year].join(" ").toLowerCase().includes(f)
    );
    app.querySelector("#empty").hidden = rows.length > 0;
    tbody.innerHTML = shown
      .map(
        (r) => `<tr data-id="${esc(r.id)}">
          <td class="muted small">${timeAgo(r.created_at)}</td>
          <td>${esc(r.year)} ${esc(r.event_name)}</td>
          <td><span class="pill ${r.kind === "what_if" ? "" : "pill-dim"}">${r.kind === "what_if" ? "what-if" : r.batch_id ? "batch" : "race"}</span></td>
          <td class="small">${esc(r.prompt || "—")}</td>
          <td>${esc(r.headline)}</td>
          <td class="muted small">${esc(r.mode)}</td>
          <td class="actions"><button class="btn-link" data-open>Open</button><button class="btn-link neg" data-del>Delete</button></td>
        </tr>`
      )
      .join("");
  };
  render();
  app.querySelector("#filter").addEventListener("input", (e) => render(e.target.value));
  tbody.addEventListener("click", async (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    const id = tr.dataset.id;
    if (e.target.matches("[data-del]")) {
      if (!confirm("Delete this simulation?")) return;
      await api.deleteResult(id);
      rows.splice(rows.findIndex((r) => r.id === id), 1);
      render(app.querySelector("#filter").value);
    } else {
      navigate(`#/r/${id}`);
    }
  });
}
