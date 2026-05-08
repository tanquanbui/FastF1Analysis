import { config } from "../config.js";

let chart;

export function renderTyreStrategyChart(canvasId, laps) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  // Build per-driver stints: array of {compound, start, end}
  const byDriver = new Map();
  for (const lap of laps.sort((a, b) => (a.LapNumber || 0) - (b.LapNumber || 0))) {
    if (!lap.DriverCode || lap.LapNumber == null) continue;
    if (!byDriver.has(lap.DriverCode)) byDriver.set(lap.DriverCode, []);
    const stints = byDriver.get(lap.DriverCode);
    const current = stints[stints.length - 1];
    if (!current || current.compound !== lap.Compound) {
      stints.push({ compound: lap.Compound || "UNKNOWN", start: lap.LapNumber, end: lap.LapNumber });
    } else {
      current.end = lap.LapNumber;
    }
  }

  const drivers = Array.from(byDriver.keys());
  const datasets = [];
  const compounds = new Set();
  for (const [driver, stints] of byDriver.entries()) {
    for (const stint of stints) compounds.add(stint.compound);
  }
  for (const compound of compounds) {
    datasets.push({
      label: compound,
      data: drivers.map((driver) => {
        const stints = byDriver.get(driver).filter((s) => s.compound === compound);
        return stints.reduce((sum, s) => sum + (s.end - s.start + 1), 0);
      }),
      backgroundColor: config.compoundColors[compound] || "#8e8e9c",
      borderWidth: 0,
    });
  }

  chart = new Chart(ctx, {
    type: "bar",
    data: { labels: drivers, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: { labels: { color: "#8e8e9c" } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.x} laps` } },
      },
      scales: {
        x: {
          stacked: true,
          ticks: { color: "#8e8e9c" },
          grid: { color: "#2a2a38" },
          title: { display: true, text: "Laps", color: "#8e8e9c" },
        },
        y: { stacked: true, ticks: { color: "#8e8e9c" }, grid: { display: false } },
      },
    },
  });
}
