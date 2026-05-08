import { config } from "../config.js";

let chart;

export function renderLapTimesChart(canvasId, laps) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  // Group laps by driver -> [{x: LapNumber, y: LapTimeSeconds}, ...]
  const grouped = new Map();
  for (const lap of laps) {
    if (lap.LapTimeSeconds == null || lap.LapNumber == null) continue;
    const driver = lap.DriverCode || "UNK";
    if (!grouped.has(driver)) grouped.set(driver, { team: lap.TeamCode || "UNK", points: [] });
    grouped.get(driver).points.push({ x: Number(lap.LapNumber), y: Number(lap.LapTimeSeconds) });
  }

  const datasets = Array.from(grouped.entries()).map(([driver, { team, points }]) => ({
    label: driver,
    data: points.sort((a, b) => a.x - b.x),
    borderColor: config.teamColors[team] || "#8e8e9c",
    backgroundColor: "transparent",
    borderWidth: 1.5,
    pointRadius: 0,
    tension: 0.2,
  }));

  chart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { labels: { color: "#8e8e9c", font: { size: 11 } } },
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Lap", color: "#8e8e9c" },
          ticks: { color: "#8e8e9c" },
          grid: { color: "#2a2a38" },
        },
        y: {
          title: { display: true, text: "Lap time (s)", color: "#8e8e9c" },
          ticks: { color: "#8e8e9c" },
          grid: { color: "#2a2a38" },
        },
      },
    },
  });
}
