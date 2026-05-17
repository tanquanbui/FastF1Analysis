import { config } from "../config.js";

export function renderPredictionCard(report) {
  const tc = report.track_compatibility || {};
  const pred = report.prediction?.race || {};
  const upgrade = report.upgrade_analysis || {};
  const champ = report.championship_scenarios || {};
  const code = report.team_code || "UNK";
  const teamName = config.teamNames[code] || report.team || code;
  const teamColor = config.teamColors[code] || "#8e8e9c";

  const confClass = (c) => (c >= 0.7 ? "" : c >= 0.5 ? "med" : "low");

  const dimensionBars = tc.dimension_breakdown
    ? Object.entries(tc.dimension_breakdown)
        .sort(([, a], [, b]) => b - a)
        .map(([dim, score]) => `
          <div class="dimension-bar">
            <span class="label">${dim.replace(/_/g, " ")}</span>
            <span class="track">
              <span class="fill" style="width:${Math.max(2, Math.min(100, score))}%; background:${teamColor}"></span>
            </span>
            <span class="value">${Math.round(score)}</span>
          </div>`)
        .join("")
    : "";

  const scenarioRows = (champ.scenarios || [])
    .map((s) => `
      <tr>
        <td>${s.outcome}</td>
        <td class="pts-cell">+${s.points_gained ?? 0}</td>
        <td class="pts-cell">${((s.title_probability_after ?? 0) * 100).toFixed(0)}%</td>
      </tr>`)
    .join("");

  return `
    <article class="card prediction-card">
      <div class="prediction-head">
        <div>
          <h2 class="prediction-team">${teamName}</h2>
          <p class="prediction-sub">
            <span class="team-swatch" style="background:${teamColor}"></span>
            ${code}
          </p>
        </div>
        <div class="prediction-headline">
          <div class="metric">
            <span class="metric-value">P${pred.predicted_position ?? "—"}</span>
            <span class="metric-label">predicted</span>
          </div>
          <div class="metric">
            <span class="metric-value">${tc.overall_score?.toFixed(1) ?? "—"}</span>
            <span class="metric-label">track fit</span>
          </div>
        </div>
      </div>

      ${tc.verdict ? `<div class="verdict">${tc.verdict}</div>` : ""}

      <h3 class="muted-h3">Race prediction</h3>
      <p class="prediction-summary">
        Range <strong>P${pred.position_range?.[0] ?? "?"}–P${pred.position_range?.[1] ?? "?"}</strong>
        <span class="confidence-band ${confClass(pred.confidence ?? 0)}">
          <span class="dot"></span> confidence ${(pred.confidence ?? 0).toFixed(2)}
        </span>
      </p>
      ${pred.model_reasoning ? `<p class="reasoning">${pred.model_reasoning}</p>` : ""}

      ${dimensionBars ? `<h3 class="muted-h3">Dimension breakdown</h3>${dimensionBars}` : ""}

      ${scenarioRows
        ? `<h3 class="muted-h3">Championship outcomes</h3>
           <table class="scenario-table">
             <thead><tr><th>Outcome</th><th>Pts</th><th>Title chance</th></tr></thead>
             <tbody>${scenarioRows}</tbody>
           </table>`
        : ""}

      ${
        champ.must_win_race
          ? `<div class="verdict warn">⚠ Must-win race · ${champ.pressure_level}</div>`
          : ""
      }
    </article>
  `;
}
