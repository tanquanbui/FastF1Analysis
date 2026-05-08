import { config } from "../config.js";

let chart;

export function renderSectorTimesChart(canvasId, laps) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  // Best sector time per driver
  const byDriver = new Map();
  for (const lap of laps) {
    const driver = lap.DriverCode;
    if (!driver) continue;
    const existing = byDriver.get(driver) || { s1: Infinity, s2: Infinity, s3: Infinity, team: lap.TeamCode };
    if (lap.Sector1Seconds != null) existing.s1 = Math.min(existing.s1, lap.Sector1Seconds);
    if (lap.Sector2Seconds != null) existing.s2 = Math.min(existing.s2, lap.Sector2Seconds);
    if (lap.Sector3Seconds != null) existing.s3 = Math.min(existing.s3, lap.Sector3Seconds);
    existing.team = lap.TeamCode || existing.team;
    byDriver.set(driver, existing);
  }

  const drivers = Array.from(byDriver.entries())
    .filter(([, d]) => Number.isFinite(d.s1 + d.s2 + d.s3))
    .sort(([, a], [, b]) => a.s1 + a.s2 + a.s3 - (b.s1 + b.s2 + b.s3));

  chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: drivers.map(([d]) => d),
      datasets: [
        { label: "Sector 1", data: drivers.map(([, d]) => d.s1), backgroundColor: "#e8002d" },
        { label: "Sector 2", data: drivers.map(([, d]) => d.s2), backgroundColor: "#ff8000" },
        { label: "Sector 3", data: drivers.map(([, d]) => d.s3), backgroundColor: "#3782e5" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: { legend: { labels: { color: "#8e8e9c" } } },
      scales: {
        x: { stacked: true, ticks: { color: "#8e8e9c" }, grid: { color: "#2a2a38" }, title: { display: true, text: "Best sector time (s)", color: "#8e8e9c" } },
        y: { stacked: true, ticks: { color: "#8e8e9c" }, grid: { display: false } },
      },
    },
  });
}
