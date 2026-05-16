import { config } from "../config.js";

const charts = {};

export function renderChampionshipChart(canvasId, probabilities, kind = "drivers") {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (charts[canvasId]) charts[canvasId].destroy();

  const entries = Object.entries(probabilities)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10);

  const colorMap = kind === "drivers"
    ? entries.map(() => "#e8002d")
    : entries.map(([code]) => config.teamColors[code] || "#8e8e9c");

  charts[canvasId] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: entries.map(([code]) => code),
      datasets: [
        {
          label: "Title probability",
          data: entries.map(([, p]) => (p * 100).toFixed(1)),
          backgroundColor: colorMap,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.x}% title chance` } },
      },
      scales: {
        x: { max: 100, ticks: { color: "#8e8e9c", callback: (v) => `${v}%` }, grid: { color: "#2a2a38" } },
        y: { ticks: { color: "#f4f4f8" }, grid: { display: false } },
      },
    },
  });
}
