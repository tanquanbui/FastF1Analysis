import { config } from "./config.js";
import { api } from "./api.js";
import { renderLapTimesChart, renderRaceProgression } from "./charts/lapTimes.js";
import { renderTyreStrategyChart } from "./charts/tyreStrategy.js";
import { renderSectorTimesChart } from "./charts/sectorTimes.js";
import { renderConstructorStandingsChart, renderDriverStandingsChart } from "./charts/standings.js";
import { renderTeamFingerprintRadar } from "./charts/radarChart.js";
import { renderUpgradeTimeline } from "./charts/upgradeTimeline.js";
import { renderTrackMatrix } from "./charts/trackMatrix.js";
import { renderPredictionCard } from "./charts/predictionCard.js";
import { renderChampionshipChart } from "./charts/championship.js";

const app = document.getElementById("app");

// ---------- helpers ----------
function setLoading(msg = "Loading…") {
  app.innerHTML = `<section class="loader"><div class="spinner"></div><p>${msg}</p></section>`;
}

function setError(error) {
  app.innerHTML = `<section class="error">Could not load: ${error.message}</section>`;
}

function updateNavActive(routeName) {
  document.querySelectorAll(".primary-nav a").forEach((a) => {
    a.classList.toggle("is-active", a.dataset.route === routeName);
  });
}

function teamTag(code) {
  return `<span class="tag team-${code}">${code}</span>`;
}

// ---------- pages ----------
async function pageSeason(year = config.currentSeason) {
  updateNavActive("season");

  // Render the page skeleton immediately with a clear loading state so the
  // user knows something is happening — server-side parallel fetch usually
  // returns in <500ms but we want to be polite about long tails.
  app.innerHTML = `
    <h1 class="page-title">${year} Season</h1>
    <p class="page-subtitle" id="season-status">
      <span class="spinner" style="width:14px;height:14px;display:inline-block;vertical-align:-2px;margin-right:6px"></span>
      Fetching season data…
    </p>
    <div class="toolbar">
      <label>Year <select id="year-select">${seasonOptions(year)}</select></label>
    </div>
    <div class="grid cols-3" id="race-grid"></div>
  `;

  document.getElementById("year-select").addEventListener("change", (e) => {
    navigate(`/season/${e.target.value}`);
  });

  const status = document.getElementById("season-status");
  const grid = document.getElementById("race-grid");

  try {
    const data = await api.listSeasonRaces(year);
    const races = data.races || [];

    if (races.length === 0) {
      status.innerHTML = `<span style="color:var(--text-muted)">No data ingested for ${year} yet.</span>`;
      return;
    }

    status.innerHTML = `<span style="color:var(--text-muted)">${races.length} rounds with data</span>`;

    // Append cards one at a time with a tiny stagger so big seasons feel
    // smooth instead of slamming into the DOM.
    for (const [i, race] of races.entries()) {
      const podium = (race.podium || [])
        .map(
          (p) => `
            <div class="podium-row">
              <span class="pos p${p.position}">${p.position}</span>
              <span>${p.driver_code || "—"}</span>
              ${p.team_code ? teamTag(p.team_code) : ""}
              <span style="margin-left:auto;color:var(--text-muted)">${p.points ?? ""} pts</span>
            </div>`,
        )
        .join("");

      const card = document.createElement("article");
      card.className = "card race-card";
      card.dataset.round = race.round;
      card.style.opacity = "0";
      card.style.transition = "opacity 0.25s ease";
      card.innerHTML = `
        <div class="race-card-header">
          <div>
            <p class="round">Round ${race.round}</p>
            <p class="name">Round ${race.round}</p>
          </div>
        </div>
        <div class="podium">${podium || '<p style="color:var(--text-muted);font-size:13px">No podium data</p>'}</div>`;
      card.addEventListener("click", () => navigate(`/race/${year}/${card.dataset.round}`));
      grid.appendChild(card);

      // Stagger fade-in.
      setTimeout(() => (card.style.opacity = "1"), Math.min(i * 20, 600));
    }
  } catch (e) {
    setError(e);
  }
}

function flagFor(code) {
  if (!code) return "";
  return code
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(127397 + c.charCodeAt(0)))
    .join("");
}

function fullTeamName(code, fallback) {
  return config.teamNames[code] || fallback || code || "Unknown";
}

async function pageRace(year, round) {
  setLoading(`Loading ${year} Round ${round}…`);
  updateNavActive("race");
  try {
    const data = await api.getRaceDetail(year, round);
    const top10 = (data.results || []).slice(0, 10);
    const resultsHtml = top10
      .map((r) => {
        const flag = flagFor(config.driverCountry[r.DriverCode]);
        const team = fullTeamName(r.TeamCode, r.ConstructorName);
        return `
          <tr>
            <td class="pos-cell">${r.Position ?? "—"}</td>
            <td class="driver-cell">
              <span class="flag">${flag}</span>
              <span class="driver-name">${r.DriverName || r.DriverCode}</span>
            </td>
            <td>
              <span class="team-swatch" style="background:${config.teamColors[r.TeamCode] || "#8e8e9c"}"></span>
              <span class="team-name">${team}</span>
            </td>
            <td class="pts-cell">${r.Points ?? 0}</td>
            <td style="color:var(--text-muted)">${r.Status || ""}</td>
          </tr>`;
      })
      .join("");

    app.innerHTML = `
      <h1 class="page-title">Round ${round} · ${year}</h1>
      <p class="page-subtitle">${data.results?.length || 0} classified · ${data.laps?.length || 0} lap records · ${data.team_metrics?.length || 0} teams</p>

      <section class="card section-row">
        <h2>Top 10</h2>
        <table class="results-table">
          <thead><tr><th>Pos</th><th>Driver</th><th>Team</th><th>Pts</th><th>Status</th></tr></thead>
          <tbody>${resultsHtml}</tbody>
        </table>
      </section>

      <section class="card section-row">
        <div class="section-head">
          <h2>Race progression</h2>
          <div class="view-toggle" id="progression-toggle">
            <button data-view="position" class="active">Position</button>
            <button data-view="gap">Gap to winner</button>
            <button data-view="pace">Stint pace</button>
          </div>
        </div>
        <div class="chart-container chart-tall"><canvas id="lap-chart"></canvas></div>
      </section>

      <section class="card section-row">
        <h2>Tyre strategy</h2>
        <div class="chart-container chart-tall"><canvas id="tyre-chart"></canvas></div>
      </section>

      <section class="card section-row">
        <h2>Sector breakdown</h2>
        <div class="chart-container chart-tall"><canvas id="sector-chart"></canvas></div>
      </section>
    `;
    renderRaceProgression("lap-chart", data.laps || [], "position");
    renderTyreStrategyChart("tyre-chart", data.laps || []);
    renderSectorTimesChart("sector-chart", data.laps || []);

    // View toggle for the race-progression chart.
    document.querySelectorAll("#progression-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => {
        document
          .querySelectorAll("#progression-toggle button")
          .forEach((b) => b.classList.toggle("active", b === btn));
        renderRaceProgression("lap-chart", data.laps || [], btn.dataset.view);
      });
    });
  } catch (e) {
    setError(e);
  }
}

async function pageStandings(year, round) {
  setLoading(`Loading ${year} standings…`);
  updateNavActive("standings");
  try {
    const data = await api.getStandings(year, round);
    app.innerHTML = `
      <h1 class="page-title">${year} Standings · Round ${round}</h1>
      <p class="page-subtitle">As of round ${round}</p>
      <div class="grid cols-2">
        <div class="card">
          <h2>Constructors</h2>
          <div class="chart-container"><canvas id="constructors-chart"></canvas></div>
        </div>
        <div class="card">
          <h2>Drivers</h2>
          <div class="chart-container"><canvas id="drivers-chart"></canvas></div>
        </div>
      </div>
    `;
    renderConstructorStandingsChart("constructors-chart", data.constructors || []);
    renderDriverStandingsChart("drivers-chart", data.drivers || []);
  } catch (e) {
    setError(e);
  }
}

async function pageTeam(code = "RBR") {
  setLoading(`Loading ${code} intelligence…`);
  updateNavActive("team");
  try {
    const [profile, fingerprint, upgrades] = await Promise.all([
      api.getTeamProfile(code),
      api.getTeamFingerprint(code).catch(() => ({ dimensions: {} })),
      api.getUpgrades(config.currentSeason, code).catch(() => ({ events: [] })),
    ]);

    app.innerHTML = `
      <h1 class="page-title">${code} · Team Intelligence</h1>
      <p class="page-subtitle">${profile.races_completed || 0} races · ${profile.total_points ?? 0} points</p>
      <div class="grid cols-2">
        <div class="card">
          <h2>Performance fingerprint</h2>
          <div class="chart-container"><canvas id="radar"></canvas></div>
        </div>
        <div class="card">
          <h2>Upgrade timeline</h2>
          <div class="chart-container"><canvas id="upgrade-timeline"></canvas></div>
        </div>
      </div>
    `;
    renderTeamFingerprintRadar("radar", fingerprint.dimensions || {});
    renderUpgradeTimeline("upgrade-timeline", upgrades.events || []);
  } catch (e) {
    setError(e);
  }
}

async function pageCircuit(key = "monaco") {
  setLoading(`Loading ${key} analysis…`);
  updateNavActive("circuit");
  try {
    const data = await api.getCircuitTeams(key);
    app.innerHTML = `
      <h1 class="page-title">${data.circuit_name || key.toUpperCase()}</h1>
      <p class="page-subtitle">Team compatibility ranked</p>
      <div class="grid">
        <div class="card">
          <h2>Compatibility heatmap</h2>
          <div class="chart-container" style="height:480px"><canvas id="track-matrix"></canvas></div>
        </div>
      </div>
    `;
    renderTrackMatrix("track-matrix", data.teams || []);
  } catch (e) {
    setError(e);
  }
}

async function pagePredictions(year = config.currentSeason, round) {
  setLoading("Loading race predictions…");
  updateNavActive("predictions");
  try {
    // If no round given, use next-after-current; the API can also be queried with `latest`
    const r = round || 1;
    const data = await api.getPredictions(year, r);
    app.innerHTML = `
      <h1 class="page-title">Race Predictions · ${data.race_name || `Round ${r}`}</h1>
      <p class="page-subtitle">${data.team_reports?.length || 0} teams analysed</p>
      <div class="grid cols-2">
        ${(data.team_reports || []).map(renderPredictionCard).join("")}
      </div>
    `;
  } catch (e) {
    setError(e);
  }
}

async function pageChampionship(year = config.currentSeason) {
  setLoading("Loading title scenarios…");
  updateNavActive("championship");
  try {
    const data = await api.getChampionshipScenarios(year);
    app.innerHTML = `
      <h1 class="page-title">${year} Title Probabilities</h1>
      <p class="page-subtitle">${(data.simulations || 10000).toLocaleString()} Monte Carlo simulations</p>
      <div class="grid cols-2">
        <div class="card">
          <h2>Drivers' championship</h2>
          <div class="chart-container"><canvas id="driver-title"></canvas></div>
        </div>
        <div class="card">
          <h2>Constructors' championship</h2>
          <div class="chart-container"><canvas id="constructor-title"></canvas></div>
        </div>
      </div>
    `;
    renderChampionshipChart("driver-title", data.title_probabilities || {}, "drivers");
    renderChampionshipChart("constructor-title", data.constructor_title_probabilities || {}, "constructors");
  } catch (e) {
    setError(e);
  }
}

// ---------- router ----------
function seasonOptions(active) {
  const years = [];
  for (let y = config.currentSeason; y >= 2018; y--) years.push(y);
  return years.map((y) => `<option value="${y}" ${y === Number(active) ? "selected" : ""}>${y}</option>`).join("");
}

function navigate(path) {
  window.location.hash = path;
}

function dispatch() {
  const hash = window.location.hash.replace(/^#/, "") || "/season";
  const parts = hash.split("/").filter(Boolean);
  const [page, ...args] = parts;
  switch (page) {
    case "season":
      return pageSeason(args[0] || config.currentSeason);
    case "race":
      return pageRace(args[0] || config.currentSeason, args[1] || 1);
    case "standings":
      return pageStandings(args[0] || config.currentSeason, args[1] || 1);
    case "team":
      return pageTeam(args[0]);
    case "circuit":
      return pageCircuit(args[0]);
    case "predictions":
      return pagePredictions(args[0], args[1]);
    case "championship":
      return pageChampionship(args[0]);
    default:
      return pageSeason();
  }
}

window.addEventListener("hashchange", dispatch);
window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("last-updated").textContent = new Date().toLocaleString();
  dispatch();
});
