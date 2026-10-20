import { config } from "../config.js";
import { esc } from "../util.js";

let positionChart = null;

function teamColor(team) {
  return config.teamColors[team] || "#8a8a9a";
}

// Lap-by-lap running order as a "bump chart": one line per driver, P1 at top.
export function renderPositionChart(canvas, sim) {
  if (positionChart) positionChart.destroy();
  if (typeof Chart === "undefined") return;

  const teamOf = Object.fromEntries(sim.classification.map((c) => [c.driver, c.team]));
  const drivers = sim.classification.map((c) => c.driver);
  const teamSeen = {};
  const labels = sim.lap_chart.map((l) => l.lap);

  const datasets = drivers.map((code) => {
    const team = teamOf[code];
    const second = teamSeen[team] === true; // dash the second car of each team
    teamSeen[team] = true;
    return {
      label: code,
      data: sim.lap_chart.map((l) => {
        const idx = l.order.indexOf(code);
        return idx === -1 ? null : idx + 1;
      }),
      borderColor: teamColor(team),
      backgroundColor: teamColor(team),
      borderDash: second ? [5, 4] : [],
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.25,
      spanGaps: false,
    };
  });

  positionChart = new Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "nearest", intersect: false },
      scales: {
        y: {
          reverse: true,
          min: 1,
          max: drivers.length,
          ticks: { stepSize: 1, color: "#7f7f8f", font: { family: "JetBrains Mono", size: 10 } },
          grid: { color: "rgba(255,255,255,0.04)" },
          title: { display: true, text: "Position", color: "#7f7f8f" },
        },
        x: {
          ticks: { color: "#7f7f8f", maxTicksLimit: 20, font: { family: "JetBrains Mono", size: 10 } },
          grid: { color: "rgba(255,255,255,0.04)" },
          title: { display: true, text: "Lap", color: "#7f7f8f" },
        },
      },
      plugins: {
        legend: {
          position: "right",
          labels: { color: "#f4f4f8", boxWidth: 12, font: { family: "JetBrains Mono", size: 11 } },
        },
        tooltip: {
          callbacks: { title: (items) => `Lap ${items[0].label}`, label: (item) => `${item.dataset.label}  P${item.raw}` },
        },
      },
    },
  });
}

// Horizontal tyre-stint bars per driver, scaled to race distance.
export function renderStrategyChart(container, sim, totalLaps) {
  const byDriver = Object.fromEntries(sim.strategies.map((s) => [s.driver, s]));
  const rows = sim.classification
    .map((c) => {
      const s = byDriver[c.driver];
      if (!s) return "";
      const stints = s.stints
        .map((st) => {
          const left = ((st.start_lap - 1) / totalLaps) * 100;
          const width = ((st.end_lap - st.start_lap + 1) / totalLaps) * 100;
          const color = config.compoundColors[st.compound] || "#888";
          const pace = st.avg_lap_s ? ` · ~${st.avg_lap_s.toFixed(2)}s` : "";
          return `<span class="stint" style="left:${left}%;width:${width}%;--compound:${color}"
                    title="${st.compound} L${st.start_lap}–${st.end_lap}${pace}">${st.compound[0]}</span>`;
        })
        .join("");
      const stops = s.pit_stops
        .map(
          (p) =>
            `<li><b>L${p.lap}</b> ${p.from_compound[0]}→${p.to_compound[0]} · ${p.stationary_s.toFixed(1)}s` +
            `${p.under_neutralisation ? ' <span class="pill pill-warn">SC/VSC</span>' : ""} — ${esc(p.reason)}</li>`
        )
        .join("");
      return `
        <details class="strategy-row">
          <summary>
            <span class="strategy-driver"><i style="background:${teamColor(c.team)}"></i>${c.driver}</span>
            <span class="strategy-track">${stints}</span>
            <span class="strategy-plan">${esc(s.planned_strategy)}</span>
          </summary>
          ${stops ? `<ul class="stop-list">${stops}</ul>` : '<p class="muted small">No stops.</p>'}
        </details>`;
    })
    .join("");
  const ticks = [1, Math.round(totalLaps / 4), Math.round(totalLaps / 2), Math.round((3 * totalLaps) / 4), totalLaps]
    .map((l) => `<span style="left:${((l - 1) / totalLaps) * 100}%">L${l}</span>`)
    .join("");
  container.innerHTML = `
    <div class="strategy-axis"><span></span><span class="strategy-ticks">${ticks}</span><span></span></div>
    ${rows}`;
}
