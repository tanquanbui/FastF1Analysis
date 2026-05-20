import { config } from "./config.js";
import { api } from "./api.js";
import { renderLapTimesChart, renderRaceProgression } from "./charts/lapTimes.js";
import { renderTrackMap } from "./charts/trackMap.js";
import { render3DTrack } from "./charts/trackMap3D.js";
import { renderQualifyingViewer } from "./charts/qualifying.js";
import { CIRCUIT_BY_ROUND, TRACKS } from "./charts/tracks_data.js";
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

const NAV_ORDER = ["season", "race", "standings", "team", "circuit", "predictor", "championship"];

function updateNavActive(routeName) {
  document.querySelectorAll(".primary-nav a").forEach((a) => {
    a.classList.toggle("is-active", a.dataset.route === routeName);
  });
  const activeIdx = NAV_ORDER.indexOf(routeName);
  document.querySelectorAll(".f1-light").forEach((light, i) => {
    light.classList.toggle("active", i === activeIdx);
  });
}

function teamTag(code) {
  return `<span class="tag team-${code}">${code}</span>`;
}

function fmtLapTime(seconds) {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(3);
  return m > 0 ? `${m}:${s.padStart(6, "0")}` : `${s}s`;
}

// ---------- pages ----------
async function pageSeason(year = config.currentSeason) {
  updateNavActive("season");

  // Render the page skeleton immediately with a clear loading state so the
  // user knows something is happening — server-side parallel fetch usually
  // returns in <500ms but we want to be polite about long tails.
  app.innerHTML = `
    <p class="eyebrow">FORMULA 1 · ${year} · CALENDAR</p>
    <h1 class="page-title">${year} <span class="accent-soft">Season</span></h1>
    <p class="page-subtitle" id="season-status">
      <span class="spinner" style="width:12px;height:12px;display:inline-block;vertical-align:-1px;margin-right:8px"></span>
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
      const raceName = CALENDAR_2024[race.round] || `Round ${race.round}`;
      const winner = (race.podium || [])[0];
      const winnerRow = winner
        ? `<div class="win-row">
            <span>WIN</span>
            <span class="driver-code">${winner.driver_code || "—"}</span>
            ${winner.team_code ? teamTag(winner.team_code) : ""}
          </div>`
        : '<div class="win-row" style="color:var(--text-dim)">— no data —</div>';

      const card = document.createElement("article");
      card.className = "card race-card";
      card.dataset.round = race.round;
      card.style.opacity = "0";
      card.style.transition = "opacity 0.25s ease";
      card.innerHTML = `
        <span class="status-dot ${winner ? "" : "empty"}"></span>
        <p class="round">R${String(race.round).padStart(2, "0")}</p>
        <p class="name">${raceName}</p>
        ${winnerRow}`;
      card.addEventListener("click", () => navigate(`/race/${year}/${card.dataset.round}`));
      grid.appendChild(card);

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

/**
 * Add Marvel-style corner brackets to every .card and .stat-tile that's
 * been rendered. The top-right corner is handled by ::after in CSS; we
 * append a bottom-left .corner-bl span here so we don't have to repeat
 * the HUD chrome in every render call.
 */
function applyHudChrome() {
  document.querySelectorAll(".card, .stat-tile").forEach((el) => {
    if (!el.querySelector(":scope > .corner-bl")) {
      const c = document.createElement("span");
      c.className = "corner-bl";
      el.appendChild(c);
    }
  });
}

/**
 * Count a numeric value up from 0 to its final value over `duration` ms.
 * Mutates a single dedicated text node instead of destroying/recreating
 * children every frame — much smoother in DevTools timeline.
 */
function startCountUps(duration = 900) {
  const elements = document.querySelectorAll(".stat-tile .value[data-target]");
  elements.forEach((el) => {
    const target = Number(el.dataset.target);
    if (!Number.isFinite(target)) return;
    const unit = el.dataset.unit || "";
    const suffixHtml = el.dataset.suffix || "";
    const prefix = el.dataset.prefix || "";
    const decimals = Number(el.dataset.decimals || 0);
    // Wipe the cell and create exactly one text node we mutate per frame
    // (plus optional suffix element appended once).
    el.textContent = "";
    const textNode = document.createTextNode("");
    el.appendChild(textNode);
    let suffixEl = null;
    if (suffixHtml) {
      const tpl = document.createElement("template");
      tpl.innerHTML = suffixHtml;
      suffixEl = tpl.content.firstElementChild;
      el.appendChild(suffixEl);
    }
    el.classList.add("counting");
    const startTime = performance.now();
    function frame(now) {
      const t = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const current = target * eased;
      textNode.nodeValue = `${prefix}${current.toFixed(decimals)}${unit}`;
      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        textNode.nodeValue = `${prefix}${target.toFixed(decimals)}${unit}`;
        el.classList.remove("counting");
      }
    }
    requestAnimationFrame(frame);
  });
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

    const raceName = CALENDAR_2024[Number(round)] || `Round ${round}`;
    const pole = (data.results || []).find((r) => r.Grid === 1) || (data.results || [])[0];
    const winner = (data.results || [])[0];
    const fastestLap = (data.team_metrics || []).reduce((best, t) => {
      const v = t.BestLapSeconds;
      if (v != null && (best == null || v < best)) return v;
      return best;
    }, null);
    const second = (data.results || [])[1];
    const marginMs = winner && second && winner.TimeMillis && second.TimeMillis
      ? second.TimeMillis - winner.TimeMillis
      : null;
    const pitCount = (data.team_metrics || []).reduce((sum, t) => sum + (t.PitStopCount || 0), 0);

    app.innerHTML = `
      <p class="eyebrow">ROUND ${String(round).padStart(2, "0")} · ${year} · COMPLETED</p>
      <h1 class="page-title">${raceName}</h1>
      <p class="page-subtitle">${data.results?.length || 0} CLASSIFIED · ${data.laps?.length || 0} LAP RECORDS · ${data.team_metrics?.length || 0} TEAMS</p>

      <div class="stat-tiles">
        <div class="stat-tile">
          <span class="label">Pole</span>
          <span class="value">${pole?.DriverCode || "—"}</span>
        </div>
        <div class="stat-tile">
          <span class="label">Fastest Lap</span>
          <span class="value">${fastestLap ? fmtLapTime(fastestLap) : "—"}</span>
        </div>
        <div class="stat-tile">
          <span class="label">Margin</span>
          <span class="value" data-target="${marginMs != null ? (marginMs/1000).toFixed(3) : 0}" data-prefix="+" data-unit="" data-decimals="3" data-suffix='<span class="unit">s</span>'>+0.000<span class="unit">s</span></span>
        </div>
        <div class="stat-tile">
          <span class="label">Pit Stops</span>
          <span class="value" data-target="${pitCount || 0}" data-decimals="0">0</span>
        </div>
      </div>

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

      <section class="card section-row">
        <h2>Circuit</h2>
        <div id="track-map" class="track-map-container"></div>
      </section>

      <section class="card section-row">
        <h2>Qualifying</h2>
        <div id="qualifying-viewer" class="qual-container"></div>
      </section>
    `;
    renderRaceProgression("lap-chart", data.laps || [], "position");
    renderTyreStrategyChart("tyre-chart", data.laps || []);
    renderSectorTimesChart("sector-chart", data.laps || []);

    const circuitKey = CIRCUIT_BY_ROUND[Number(round)] || "monza";
    renderTrackMap("track-map", circuitKey);

    api.getQualifying(year, round)
      .then((qd) => renderQualifyingViewer("qualifying-viewer", qd.qualifying || []))
      .catch(() => {
        document.getElementById("qualifying-viewer").innerHTML =
          '<p style="color:var(--text-muted);padding:24px">Qualifying data hasn\'t been processed for this race yet.</p>';
      });

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
      <p class="eyebrow">CHAMPIONSHIP · ${year} · AFTER ROUND ${String(round).padStart(2, "0")}</p>
      <h1 class="page-title">Season <span class="accent-soft">Standings</span></h1>
      <p class="page-subtitle">CONSTRUCTORS & DRIVERS · POINTS-WEIGHTED</p>
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
      <p class="eyebrow">TEAM INTELLIGENCE · ${code}</p>
      <h1 class="page-title">${config.teamNames[code] || code}</h1>
      <p class="page-subtitle">${profile.races_completed || 0} RACES · ${profile.total_points ?? 0} PTS · 8-DIMENSION FINGERPRINT</p>
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
  updateNavActive("circuit");

  const trackData = TRACKS[key] || TRACKS.monza;
  const options = Object.entries(TRACKS)
    .map(([k, t]) => `<option value="${k}" ${k === key ? "selected" : ""}>${t.name}</option>`)
    .join("");

  app.innerHTML = `
    <p class="eyebrow">CIRCUIT · ${key.toUpperCase().replace("_", " ")}</p>
    <h1 class="page-title">${trackData.name.split(" ")[0]} <span class="accent-soft">${trackData.name.split(" ").slice(1).join(" ")}</span></h1>
    <p class="page-subtitle">${trackData.length_km} KM · ${trackData.corners} CORNERS · ${trackData.drs_zones} DRS ZONE(S) · ${trackData.direction.toUpperCase()}</p>
    <div class="toolbar">
      <label>Circuit
        <select id="circuit-select">${options}</select>
      </label>
    </div>
    <section class="card section-row">
      <div id="track-map" class="track-map-container"></div>
    </section>
    <section class="card section-row">
      <h2>Team compatibility at this circuit</h2>
      <div class="chart-container" style="height:480px"><canvas id="track-matrix"></canvas></div>
    </section>
  `;

  document.getElementById("circuit-select").addEventListener("change", (e) => {
    navigate(`/circuit/${e.target.value}`);
  });

  renderTrackMap("track-map", key);
  try {
    const data = await api.getCircuitTeams(key);
    renderTrackMatrix("track-matrix", data.teams || []);
  } catch {
    // Compatibility data optional.
  }
}

async function pagePredictions(year = config.currentSeason, round) {
  setLoading("Loading race predictions…");
  updateNavActive("predictions");
  try {
    // Default to the upcoming-race round we generated reports for.
    const r = round || 25;
    const data = await api.getPredictions(year, r);
    const reports = data.team_reports || [];

    if (reports.length === 0) {
      app.innerHTML = `
        <h1 class="page-title">Race Predictions</h1>
        <p class="page-subtitle">No predictions yet for ${year} round ${r}.</p>
        <div class="card section-row">
          <p style="color:var(--text-muted)">
            Run the predictor Lambda for a future round to generate per-team
            reports here.
          </p>
        </div>`;
      return;
    }

    // Sort by predicted finishing position so the favourites come first.
    reports.sort(
      (a, b) =>
        (a.prediction?.race?.predicted_position ?? 99) -
        (b.prediction?.race?.predicted_position ?? 99),
    );

    app.innerHTML = `
      <h1 class="page-title">Race Predictions · ${data.race_name || `Round ${r}`}</h1>
      <p class="page-subtitle">${reports.length} teams analysed · sorted by predicted finish</p>
      <div class="grid cols-2">
        ${reports.map(renderPredictionCard).join("")}
      </div>
    `;
  } catch (e) {
    setError(e);
  }
}

// --- 2024 calendar mapping (round -> human label) ---
const CALENDAR_2024 = {
  1: "Bahrain", 2: "Saudi Arabia", 3: "Australia", 4: "Japan", 5: "China",
  6: "Miami", 7: "Emilia-Romagna", 8: "Monaco", 9: "Canada", 10: "Spain",
  11: "Austria", 12: "Great Britain", 13: "Hungary", 14: "Belgium", 15: "Netherlands",
  16: "Italy", 17: "Azerbaijan", 18: "Singapore", 19: "United States", 20: "Mexico",
  21: "São Paulo", 22: "Las Vegas", 23: "Qatar", 24: "Abu Dhabi",
};

async function pagePredictor(year = config.currentSeason, round) {
  updateNavActive("predictor");

  // Skeleton + selector first so the UX feels instant.
  const selectedRound = Number(round) || 6;
  const rounds = Array.from({ length: 23 }, (_, i) => i + 2); // can backtest from round 2 onwards
  const options = rounds
    .map((r) => `<option value="${r}" ${r === selectedRound ? "selected" : ""}>R${r} · ${CALENDAR_2024[r] || `Round ${r}`}</option>`)
    .join("");

  app.innerHTML = `
    <p class="eyebrow">PRE-RACE REPORT · BACKTEST MODE · ${year}</p>
    <h1 class="page-title">Race <span class="accent-soft">Predictor</span></h1>
    <p class="page-subtitle">DRIVER-LEVEL 6-SIGNAL MODEL · CLICK ROW FOR FULL ANALYSIS</p>
    <div class="toolbar">
      <label>Target race
        <select id="predictor-round">${options}</select>
      </label>
    </div>
    <div id="predictor-result"></div>
  `;

  document.getElementById("predictor-round").addEventListener("change", (e) => {
    navigate(`/predictor/${year}/${e.target.value}`);
  });

  await renderPredictorComparison(year, selectedRound);
}

async function renderPredictorComparison(year, round) {
  const out = document.getElementById("predictor-result");
  out.innerHTML = `
    <div class="loader" style="min-height:200px">
      <div class="spinner"></div>
      <p>Running prediction with data from rounds 1-${round - 1}…</p>
    </div>`;

  try {
    const [drivers, actual] = await Promise.all([
      api.getDriverPredictions(year, round).catch(() => ({ drivers: [] })),
      api.getRaceDetail(year, round).catch(() => ({ results: [] })),
    ]);

    const predicted = drivers.drivers || [];
    if (predicted.length === 0) {
      out.innerHTML = `
        <div class="card section-row">
          <p style="color:var(--text-muted)">
            No driver predictions for ${year} R${round} yet. Re-run the predictor Lambda
            once fingerprints + qualifying data are populated.
          </p>
        </div>`;
      return;
    }

    const actualRanking = (actual.results || [])
      .filter((r) => r.Position != null)
      .sort((a, b) => (a.Position ?? 99) - (b.Position ?? 99));

    // Accuracy at driver level.
    const actualByCode = new Map(actualRanking.map((r, i) => [r.DriverCode, { row: r, pos: i + 1 }]));
    const winnerHit = predicted[0]?.DriverCode === actualRanking[0]?.DriverCode;
    const top3PredCodes = predicted.slice(0, 3).map((p) => p.DriverCode);
    const top3ActualCodes = actualRanking.slice(0, 3).map((r) => r.DriverCode);
    const top3Hits = top3PredCodes.filter((c) => top3ActualCodes.includes(c)).length;
    const errors = predicted
      .map((p, i) => {
        const a = actualByCode.get(p.DriverCode);
        return a ? Math.abs(i - (a.pos - 1)) : null;
      })
      .filter((v) => v != null);
    const meanAbsErr = mean(errors);

    out.innerHTML = `
      <div class="grid cols-2 predictor-cols">
        <section class="card section-row">
          <h2>Predicted</h2>
          <p class="muted-h3">Driver leaderboard · rounds 1-${round - 1} as training data</p>
          <table class="results-table predictor-table">
            <thead><tr><th>Pos</th><th>Driver</th><th>Team</th><th>Score</th></tr></thead>
            <tbody>
              ${predicted
                .slice(0, 10)
                .map((d, i) => driverPredictionRow(i + 1, d, year, round))
                .join("")}
            </tbody>
          </table>
        </section>
        <section class="card section-row">
          <h2>Actual</h2>
          <p class="muted-h3">${CALENDAR_2024[round] || `Round ${round}`} ${year} — top 10 finishers</p>
          <table class="results-table predictor-table">
            <thead><tr><th>Pos</th><th>Driver</th><th>Team</th></tr></thead>
            <tbody>
              ${actualRanking
                .slice(0, 10)
                .map((r) => actualRow(r))
                .join("")}
            </tbody>
          </table>
        </section>
      </div>
      <section class="card section-row">
        <h2>Accuracy</h2>
        <div class="grid cols-stats">
          <div>
            <p class="muted-h3">Winner</p>
            <p class="metric-big">${winnerHit ? "✓ Correct" : "✗ Miss"}</p>
          </div>
          <div>
            <p class="muted-h3">Podium hits</p>
            <p class="metric-big">${top3Hits}/3</p>
          </div>
          <div>
            <p class="muted-h3">Mean position error</p>
            <p class="metric-big">${meanAbsErr.toFixed(1)}</p>
          </div>
          <div>
            <p class="muted-h3">Drivers scored</p>
            <p class="metric-big">${predicted.length}</p>
          </div>
        </div>
        <p class="muted-h3" style="margin-top:14px">Click any predicted row to see the full signal breakdown for that driver.</p>
      </section>
    `;

    // Wire up row clicks for the analysis modal.
    document.querySelectorAll(".driver-prediction-row").forEach((row) => {
      row.addEventListener("click", () => {
        const code = row.dataset.driver;
        const d = predicted.find((p) => p.DriverCode === code);
        if (d) showDriverAnalysis(d, year, round);
      });
    });
  } catch (e) {
    out.innerHTML = `<section class="error">Prediction failed: ${e.message}</section>`;
  }
}

function driverPredictionRow(rank, d, year, round) {
  const code = d.DriverCode;
  const team = config.teamNames[d.TeamCode] || d.TeamCode;
  const color = config.teamColors[d.TeamCode] || "#8e8e9c";
  const score = Math.round(d.Combined ?? 0);
  const flag = flagFor(config.driverCountry[code]);
  return `
    <tr class="driver-prediction-row" data-driver="${code}">
      <td class="pos-cell">${rank}</td>
      <td class="driver-cell">
        <span class="flag">${flag}</span>
        <span class="driver-name">${d.DriverName || code}</span>
      </td>
      <td>
        <span class="team-swatch" style="background:${color}"></span>
        <span class="team-name">${team}</span>
      </td>
      <td class="conf-cell">
        <div class="conf-bar"><span style="width:${score}%"></span></div>
        <span class="conf-score">${score}<span class="conf-score-suffix">/100</span></span>
      </td>
    </tr>`;
}

function showDriverAnalysis(d, year, round) {
  const code = d.DriverCode;
  const team = config.teamNames[d.TeamCode] || d.TeamCode;
  const color = config.teamColors[d.TeamCode] || "#8e8e9c";
  const flag = flagFor(config.driverCountry[code]);
  const signals = d.Signals || {};
  const weights = d.Weights || {};
  // The predictor stores qualifying_position at the top level of the driver
  // record, not inside InputData — merge it so the narrative can read it.
  const inputs = {
    ...(d.InputData || {}),
    qualifying_position: d.QualifyingPosition ?? null,
  };
  const circuitKey = CIRCUIT_BY_ROUND[Number(round)] || "monza";
  const track = TRACKS[circuitKey] || TRACKS.monza;

  const signalRows = [
    ["qualifying", "Qualifying", `P${d.QualifyingPosition ?? "—"}`],
    ["historical", "Historical at circuit", `last ${(inputs.historical_positions || []).length} same-round finishes`],
    ["recent_form", "Recent form (5 races)", `avg P${avgList(inputs.recent_positions).toFixed(1)}`],
    ["overtaking", "Overtaking skill", `avg ${avgList(inputs.grid_to_finish_history) > 0 ? "+" : ""}${avgList(inputs.grid_to_finish_history).toFixed(1)} pos/race`],
    ["reliability", "Reliability", `DNF rate ${((inputs.dnf_rate ?? 0) * 100).toFixed(0)}%`],
    ["track_fit", "Track fit", `${(inputs.track_fit ?? 0).toFixed(1)}/100`],
  ]
    .map(([key, label, sub]) => {
      const score = signals[key];
      const weight = weights[key];
      if (score == null) {
        return `
          <div class="signal-row missing">
            <span class="signal-label">${label}<span class="signal-sub">no data</span></span>
            <span class="signal-bar"><span class="fill" style="width:0%; background:${color}"></span></span>
            <span class="signal-score">—</span>
          </div>`;
      }
      return `
        <div class="signal-row">
          <span class="signal-label">
            ${label}
            <span class="signal-sub">${sub} · weight ${(weight * 100).toFixed(0)}%</span>
          </span>
          <span class="signal-bar"><span class="fill" style="width:${score}%; background:${color}"></span></span>
          <span class="signal-score">${Math.round(score)}</span>
        </div>`;
    })
    .join("");

  const narrative = buildNarrative(d, signals, weights, inputs, track, circuitKey, round);

  const html = `
    <div class="modal-backdrop">
      <div class="modal modal-xl">
        <button class="modal-close" aria-label="Close">×</button>
        <div class="modal-header">
          <div>
            <h2>${flag} ${d.DriverName || code}</h2>
            <p class="muted-h3" style="margin-top:6px">
              <span class="team-swatch" style="background:${color}"></span>
              ${team} · ${CALENDAR_2024[round] || `Round ${round}`} ${year}
            </p>
          </div>
          <div class="prediction-headline">
            <div class="metric">
              <span class="metric-value">P${d.PredictedPosition}</span>
              <span class="metric-label">predicted</span>
            </div>
            <div class="metric">
              <span class="metric-value">${Math.round(d.Combined ?? 0)}</span>
              <span class="metric-label">/100 combined</span>
            </div>
          </div>
        </div>

        <h3 class="muted-h3">3D circuit visualisation</h3>
        <p class="reasoning-prose" style="margin-bottom:14px">
          Sector elevation = how well this driver's signal profile suits each sector's demands.
          Dot speed = predicted pace per sector. DRS cones in green, overtake rings in red.
          Drag to rotate; auto-rotates by default.
        </p>
        <div id="driver-3d" class="track-3d-container"></div>

        <h3 class="muted-h3" style="margin-top:24px">How the model decided</h3>
        <div class="analysis-prose">
          ${narrative}
        </div>

        <h3 class="muted-h3" style="margin-top:22px">Signal breakdown</h3>
        <div class="signal-list">${signalRows}</div>
      </div>
    </div>`;
  const wrap = document.createElement("div");
  wrap.innerHTML = html;
  document.body.appendChild(wrap);

  // Inject a brief HUD scanning intro before the 3D scene boots.
  const driver3dEl = document.getElementById("driver-3d");
  driver3dEl.style.position = "relative";
  driver3dEl.innerHTML = `
    <div class="scan-intro">
      <div class="scan-line"></div>
      <span class="scan-text">ANALYSING DRIVER · ${code}</span>
      <span class="scan-progress" id="scan-pct">0%</span>
    </div>`;
  const scanPct = document.getElementById("scan-pct");
  const scanStart = performance.now();
  const SCAN_MS = 1300;
  (function scanFrame() {
    const t = Math.min(1, (performance.now() - scanStart) / SCAN_MS);
    if (scanPct) scanPct.textContent = `${Math.round(t * 100)}%`;
    if (t < 1) requestAnimationFrame(scanFrame);
  })();

  let teardown = null;
  setTimeout(() => {
    teardown = render3DTrack({
      containerId: "driver-3d",
      circuitKey,
      driverColor: color,
      driverCode: code,
      signals: { ...signals, combined: d.Combined },
    });
  }, SCAN_MS);

  const close = () => {
    teardown?.();
    wrap.remove();
  };
  wrap.querySelector(".modal-close").addEventListener("click", close);
  wrap.querySelector(".modal-backdrop").addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-backdrop")) close();
  });
  document.addEventListener("keydown", function escHandler(e) {
    if (e.key === "Escape") {
      close();
      document.removeEventListener("keydown", escHandler);
    }
  });
}

/**
 * Build the rich narrative explanation. Each paragraph ties one of the
 * driver's signals to a specific circuit characteristic so the user can
 * see WHY each input matters here.
 */
function buildNarrative(d, signals, weights, inputs, track, circuitKey, round) {
  const name = (d.DriverName || d.DriverCode || "this driver").split(" ").pop();
  const sections = [];

  // Track context — what does this circuit reward?
  const features = trackHighlights(circuitKey, round);
  if (features) {
    sections.push(`<p><strong>${track.name}</strong> is a ${features.character} circuit. ${features.story}</p>`);
  }

  // Order signals by contribution.
  const contribs = Object.entries(signals)
    .filter(([, v]) => v != null)
    .map(([k, v]) => ({ key: k, score: v, weight: weights[k] || 0, contrib: v * (weights[k] || 0) }))
    .sort((a, b) => b.contrib - a.contrib);

  // Top 3 contributors get a paragraph each.
  for (const c of contribs.slice(0, 3)) {
    const para = signalParagraph(c.key, c.score, c.weight, c.contrib, inputs, name, features);
    if (para) sections.push(`<p>${para}</p>`);
  }

  // Missing signals — note that we redistributed weight.
  const missing = Object.entries(signals).filter(([, v]) => v == null).map(([k]) => prettyKey(k));
  if (missing.length) {
    sections.push(
      `<p class="muted">Missing inputs: ${missing.join(", ")}. Their weight has been redistributed across the present signals, so the combined score still reads on a 0-100 scale.</p>`,
    );
  }

  // Closing verdict line.
  const final = Math.round(d.Combined ?? 0);
  const verdict = final >= 75
    ? `Strong overall profile — most signals lean favourable for this circuit.`
    : final >= 55
      ? `Mixed picture: real strengths exist, but at least one major signal is dragging the score down.`
      : `${name} faces an uphill weekend here on multiple fronts. A recovery drive rather than a podium charge.`;
  sections.push(`<p class="verdict-line">${verdict} <strong>Combined ${final}/100</strong> → predicted <strong>P${d.PredictedPosition}</strong>.</p>`);

  return sections.join("");
}

function signalParagraph(key, score, weight, contrib, inputs, name, features) {
  const wPct = (weight * 100).toFixed(0);
  const cPct = contrib.toFixed(1);
  const characterMatters = features?.dominantSignal === key;
  const emphasis = characterMatters ? ` — exactly the signal this circuit rewards most` : "";

  switch (key) {
    case "qualifying": {
      const pos = inputs.qualifying_position ?? "?";
      return `${name} qualified <strong>P${pos}</strong>. With a ${wPct}% weight on qualifying (the strongest single signal in the model), this alone feeds <strong>${cPct} points</strong> into the combined score${emphasis}. The closer to pole, the more this dominates.`;
    }
    case "historical": {
      const past = (inputs.historical_positions || []);
      if (past.length === 0) {
        return `Historical record at this circuit scored ${score.toFixed(1)}/100 (${wPct}% weight → ${cPct} pts).`;
      }
      const avgPos = (past.reduce((a, b) => a + b, 0) / past.length).toFixed(1);
      return `Looking back at the last ${past.length} same-round race${past.length > 1 ? "s" : ""}, ${name} averaged P${avgPos} at this venue. Track-specific history is a strong signal because circuits reward consistent car/driver characteristics year-over-year, so this contributes <strong>${cPct} pts</strong> (${wPct}% weight × ${Math.round(score)}/100)${emphasis}.`;
    }
    case "recent_form": {
      const recent = inputs.recent_positions || [];
      if (recent.length === 0) {
        return `Recent form contributed ${cPct} pts (${wPct}% weight × ${Math.round(score)}/100).`;
      }
      const avg = recent.reduce((a, b) => a + b, 0) / recent.length;
      const trend = recent.length >= 2 && recent[recent.length - 1] < recent[0] ? "improving" : recent.length >= 2 && recent[recent.length - 1] > recent[0] ? "drifting" : "steady";
      return `Last ${recent.length} finishes: ${recent.map((p) => `P${p}`).join(" → ")} (avg P${avg.toFixed(1)}, ${trend}). Recent form picks up upgrades, reliability streaks, and momentum the historical signal can't see — contributes <strong>${cPct} pts</strong>${emphasis}.`;
    }
    case "overtaking": {
      const gains = inputs.grid_to_finish_history || [];
      if (gains.length === 0) {
        return `Overtaking skill: ${cPct} pts (${wPct}% weight × ${Math.round(score)}/100).`;
      }
      const avg = gains.reduce((a, b) => a + b, 0) / gains.length;
      const flavour = avg > 1.5 ? "consistent climber" : avg < -1.5 ? "tends to lose positions" : "broadly holds station";
      return `Grid → finish delta over the last ${gains.length} races: average ${avg > 0 ? "+" : ""}${avg.toFixed(1)} positions per race (${flavour}). This signal matters more on circuits where overtaking is possible. Contributes <strong>${cPct} pts</strong>${emphasis}.`;
    }
    case "reliability": {
      const rate = (inputs.dnf_rate ?? 0) * 100;
      return `Reliability score: ${Math.round(score)}/100 (DNF rate ${rate.toFixed(0)}% over the last 10 races). A high-DNF tail risk doesn't only show in final position — it depresses the combined score even when raw pace is strong. <strong>${cPct} pts</strong> contributed${emphasis}.`;
    }
    case "track_fit": {
      const fit = inputs.track_fit ?? 0;
      return `Team fingerprint × this circuit's 8-dimension profile gives a track fit of <strong>${fit.toFixed(1)}/100</strong>. The model weights this at ${wPct}% because raw team capability across speed/cornering/strategy compounds with the rest of the signals. <strong>${cPct} pts</strong>${emphasis}.`;
    }
    default:
      return `${prettyKey(key)} contributed ${cPct} pts (${wPct}% × ${Math.round(score)}/100).`;
  }
}

// Keyed by 2024 round number — every race gets its own character +
// narrative so the analysis doesn't fall back to "Monza" for everyone.
const TRACK_HIGHLIGHTS_BY_ROUND = {
  1:  { character: "tyre-management",                story: "Three DRS zones make overtaking realistic, but rear tyres are the limiting factor.", dominantSignal: "track_fit" },
  2:  { character: "ultra-fast street",              story: "Highest average speed of any street circuit. Walls + flat-out commitment in the high-speed sweeps.", dominantSignal: "qualifying" },
  3:  { character: "park-circuit semi-permanent",    story: "Wide and flowing with several heavy braking zones. Safety-car probability around 35%.", dominantSignal: "historical" },
  4:  { character: "technical figure-8",             story: "S-Curves and 130R reward absolute precision. Engineers' favourite circuit.", dominantSignal: "qualifying" },
  5:  { character: "long-straight + slow corners",   story: "1.2km back straight rewards top speed; the rest of the lap punishes anything with weak slow corner traction.", dominantSignal: "track_fit" },
  6:  { character: "permanent street",               story: "Mixed slow + fast sections. DRS into T17 is the prime overtake.", dominantSignal: "qualifying" },
  7:  { character: "narrow old-school",              story: "Overtaking nearly impossible — qualifying decides the race.", dominantSignal: "qualifying" },
  8:  { character: "tight low-speed street",         story: "Overtaking is essentially impossible — pole wins ~70% of races held here. Qualifying score dominates.", dominantSignal: "qualifying" },
  9:  { character: "stop-go semi-street",            story: "Wall of Champions claims pole-sitters. High kerb-riding tolerance + braking stability rewarded.", dominantSignal: "overtaking" },
  10: { character: "aerodynamic benchmark",          story: "Reveals true car balance. High-speed corners early, slow chicane late — exposes any aero weakness.", dominantSignal: "track_fit" },
  11: { character: "short power-and-flow",           story: "Only 9 corners but extreme elevation. Brake stability in T3 critical.", dominantSignal: "recent_form" },
  12: { character: "high-speed aero",                story: "Maggotts-Becketts demand a confidence-inspiring high-speed platform; Stowe rewards composed braking.", dominantSignal: "historical" },
  13: { character: "low-speed European Monaco",      story: "Twisty, narrow, low-speed cornering rules. Track-position is everything.", dominantSignal: "qualifying" },
  14: { character: "all-rounder, weather wildcard",  story: "Eau Rouge–Raidillon flat-out separates the brave. Rain hits ~30% of years.", dominantSignal: "historical" },
  15: { character: "banked old-school",              story: "Banking at T3 + T14 keeps following cars closer. Qualifying still matters because the track is narrow.", dominantSignal: "qualifying" },
  16: { character: "high-speed power",               story: "Long straights and minimal corners. DRS trains form easily; straight-line speed and slipstream tactics decide it.", dominantSignal: "track_fit" },
  17: { character: "fast street",                    story: "Long castle straight + slow technical second sector. Tyre warm-up after slow corners is the gotcha.", dominantSignal: "overtaking" },
  18: { character: "physical night street",          story: "High humidity, 19 corners, safety-car probability ~60%. The most physically demanding race.", dominantSignal: "qualifying" },
  19: { character: "bumpy COTA",                     story: "Hilly and bumpy. Tests suspension travel + high-speed change of direction in S1.", dominantSignal: "track_fit" },
  20: { character: "high-altitude",                  story: "Thin air robs aero downforce + engine power equally. Cars with good cooling lap consistency win.", dominantSignal: "historical" },
  21: { character: "Brazilian wildcard",             story: "Weather frequently flips the result. Sprint format adds extra strategic complexity.", dominantSignal: "recent_form" },
  22: { character: "Strip night race",               story: "Long straights and a cold low-grip surface. Front-end stability in heavy braking decides it.", dominantSignal: "qualifying" },
  23: { character: "high-speed sweeper",             story: "Lusail's high-speed corners + brutal heat = a tyre-stress contest.", dominantSignal: "track_fit" },
  24: { character: "modern, season-finale",          story: "Reconfigured 2021 layout improved overtaking. Pressure of the finale adds strategic complexity.", dominantSignal: "recent_form" },
};

function trackHighlights(circuitKey, round) {
  return TRACK_HIGHLIGHTS_BY_ROUND[Number(round)] || null;
}

function prettyKey(k) {
  return {
    qualifying: "qualifying",
    historical: "historical at circuit",
    recent_form: "recent form",
    overtaking: "overtaking skill",
    reliability: "reliability",
    track_fit: "track fit",
  }[k] || k;
}

function reasoningBullets(signals, weights, inputs) {
  const out = [];
  const entries = Object.entries(signals)
    .filter(([, v]) => v != null)
    .sort((a, b) => (b[1] * (weights[b[0]] || 0)) - (a[1] * (weights[a[0]] || 0)));
  for (const [key, score] of entries.slice(0, 3)) {
    const weight = weights[key] || 0;
    const contribution = (score * weight).toFixed(1);
    const labels = {
      qualifying: `Strong qualifying result feeds ${contribution} pts to the score (${(weight * 100).toFixed(0)}% weight × ${score}/100).`,
      historical: `Track record at this circuit contributes ${contribution} pts (${(weight * 100).toFixed(0)}% weight × ${score}/100).`,
      recent_form: `Recent finishing positions contribute ${contribution} pts (${(weight * 100).toFixed(0)}% weight × ${score}/100).`,
      overtaking: `Grid→finish skill contributes ${contribution} pts (${(weight * 100).toFixed(0)}% weight × ${score}/100).`,
      reliability: `Reliability over the last 10 races contributes ${contribution} pts (${(weight * 100).toFixed(0)}% weight × ${score}/100).`,
      track_fit: `Team fingerprint × this circuit's profile contributes ${contribution} pts (${(weight * 100).toFixed(0)}% weight × ${score}/100).`,
    };
    out.push(`<li>${labels[key] || `${key}: ${contribution} pts`}</li>`);
  }
  const missing = Object.entries(signals).filter(([, v]) => v == null).map(([k]) => k);
  if (missing.length) {
    out.push(`<li class="muted">No data for: ${missing.join(", ")}. Their weight was redistributed across the present signals.</li>`);
  }
  return out;
}

function avgList(arr) {
  const nums = (arr || []).filter((v) => typeof v === "number" && !Number.isNaN(v));
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : 0;
}

function predictorRow(rank, code, confidence) {
  const team = config.teamNames[code] || code;
  const color = config.teamColors[code] || "#8e8e9c";
  const score = Math.round((confidence ?? 0) * 100);
  return `
    <tr>
      <td class="pos-cell">${rank}</td>
      <td>
        <span class="team-swatch" style="background:${color}"></span>
        <span class="team-name">${team}</span>
      </td>
      <td class="conf-cell">
        <div class="conf-bar"><span style="width:${score}%"></span></div>
        <span class="conf-score">${score}<span class="conf-score-suffix">/100</span></span>
      </td>
    </tr>`;
}

function actualRow(r) {
  const flag = flagFor(config.driverCountry[r.DriverCode]);
  const team = config.teamNames[r.TeamCode] || r.TeamCode;
  const color = config.teamColors[r.TeamCode] || "#8e8e9c";
  return `
    <tr>
      <td class="pos-cell">${r.Position ?? "—"}</td>
      <td class="driver-cell">
        <span class="flag">${flag}</span>
        <span class="driver-name">${r.DriverName || r.DriverCode}</span>
      </td>
      <td>
        <span class="team-swatch" style="background:${color}"></span>
        <span class="team-name">${team}</span>
      </td>
    </tr>`;
}

function mean(arr) {
  if (!arr.length) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

async function pageChampionship(year = config.currentSeason) {
  setLoading("Loading title scenarios…");
  updateNavActive("championship");
  try {
    const data = await api.getChampionshipScenarios(year);
    app.innerHTML = `
      <p class="eyebrow">CHAMPIONSHIP SIMULATOR · ${year}</p>
      <h1 class="page-title">Title <span class="accent-soft">Probabilities</span></h1>
      <p class="page-subtitle">${(data.simulations || 10000).toLocaleString()} MONTE CARLO RUNS · DRIVERS + CONSTRUCTORS</p>
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

function afterRender() {
  // Called after every page renders. Adds HUD chrome to new cards/tiles
  // and triggers the count-up animation on any [data-target] values.
  requestAnimationFrame(() => {
    applyHudChrome();
    startCountUps();
    // Strip will-change once the entrance animations finish so we don't
    // keep promoting every card to its own GPU layer forever — that
    // drains battery and slows down later interactions (scroll, hover).
    setTimeout(() => {
      document
        .querySelectorAll(".eyebrow, .page-title, .page-subtitle, .stat-tile, .card.race-card, .card.section-row")
        .forEach((el) => {
          el.style.willChange = "auto";
        });
    }, 1500);
  });
}

function dispatch() {
  const hash = window.location.hash.replace(/^#/, "") || "/season";
  const parts = hash.split("/").filter(Boolean);
  const [page, ...args] = parts;
  let p;
  switch (page) {
    case "season":
      p = pageSeason(args[0] || config.currentSeason); break;
    case "race":
      p = pageRace(args[0] || config.currentSeason, args[1] || 1); break;
    case "standings":
      p = pageStandings(args[0] || config.currentSeason, args[1] || 1); break;
    case "team":
      p = pageTeam(args[0]); break;
    case "circuit":
      p = pageCircuit(args[0]); break;
    case "predictions":
      p = pagePredictions(args[0], args[1]); break;
    case "predictor":
      p = pagePredictor(args[0], args[1]); break;
    case "championship":
      p = pageChampionship(args[0]); break;
    default:
      p = pageSeason();
  }
  // After the page promise resolves, slap on the HUD chrome.
  if (p && typeof p.then === "function") {
    p.then(afterRender);
  } else {
    afterRender();
  }
}

window.addEventListener("hashchange", dispatch);
window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("last-updated").textContent = new Date().toLocaleString();
  dispatch();
});
