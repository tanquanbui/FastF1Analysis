import { config } from "../config.js";

let constructorChart;
let driverChart;

export function renderConstructorStandingsChart(canvasId, items) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (constructorChart) constructorChart.destroy();

  const sorted = items
    .filter((i) => i.Position != null)
    .sort((a, b) => a.Position - b.Position);

  constructorChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: sorted.map((s) => s.TeamCode || s.ConstructorName || "?"),
      datasets: [
        {
          label: "Points",
          data: sorted.map((s) => s.Points || 0),
          backgroundColor: sorted.map((s) => config.teamColors[s.TeamCode] || "#8e8e9c"),
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8e8e9c" }, grid: { color: "#2a2a38" } },
        y: { ticks: { color: "#8e8e9c" }, grid: { display: false } },
      },
    },
  });
}

export function renderDriverStandingsChart(canvasId, items) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (driverChart) driverChart.destroy();

  const sorted = items
    .filter((i) => i.Position != null)
    .sort((a, b) => a.Position - b.Position)
    .slice(0, 20);

  driverChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: sorted.map((s) => s.DriverCode || s.DriverName?.split(" ").pop()),
      datasets: [
        {
          label: "Points",
          data: sorted.map((s) => s.Points || 0),
          backgroundColor: sorted.map((s) => config.teamColors[s.TeamCode] || "#8e8e9c"),
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8e8e9c" }, grid: { color: "#2a2a38" } },
        y: { ticks: { color: "#8e8e9c" }, grid: { display: false } },
      },
    },
  });
}
