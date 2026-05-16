export function renderPredictionCard(report) {
  const tc = report.track_compatibility || {};
  const pred = report.prediction || {};
  const upgrade = report.upgrade_analysis || {};
  const champ = report.championship_scenarios || {};

  const confidenceClass = (c) => (c >= 0.7 ? "" : c >= 0.5 ? "med" : "low");

  const dimensionBars = (tc.dimension_breakdown || {})
    ? Object.entries(tc.dimension_breakdown || {})
        .map(([dim, score]) => `
          <div class="dimension-bar">
            <span class="label">${dim.replace(/_/g, " ")}</span>
            <span class="track"><span class="fill" style="width:${Math.min(100, score)}%"></span></span>
            <span class="value">${Math.round(score)}</span>
          </div>`)
        .join("")
    : "";

  return `
    <article class="card">
      <h2>${report.team} <span class="tag team-${report.team_code}">${report.team_code}</span></h2>
      <p class="page-subtitle">Compatibility ${tc.overall_score ?? "—"} / 100</p>
      <div class="verdict">${tc.verdict || "—"}</div>

      ${dimensionBars ? `<h3 style="margin-top:16px">Dimension breakdown</h3>${dimensionBars}` : ""}

      <h3 style="margin-top:16px">Race prediction</h3>
      <p>Predicted P${pred.race?.predicted_position ?? "—"} (range P${pred.race?.position_range?.[0] ?? "?"}–P${pred.race?.position_range?.[1] ?? "?"})
        <span class="confidence-band ${confidenceClass(pred.race?.confidence ?? 0)}"><span class="dot"></span> confidence ${(pred.race?.confidence ?? 0).toFixed(2)}</span>
      </p>
      <p style="color:var(--text-muted);font-size:13px;margin-top:4px">${pred.race?.model_reasoning || ""}</p>

      <h3 style="margin-top:16px">Upgrade impact</h3>
      <p style="font-size:13px">${upgrade.upgrade_impact_at_this_circuit?.net_upgrade_benefit || "No recent upgrade detected."}</p>

      ${champ.must_win_race ? `<div class="verdict" style="margin-top:16px">Must-win race · ${champ.pressure_level}</div>` : ""}
    </article>
  `;
}
