import { config } from "../config.js";

let chart;

/**
 * Position-over-laps chart — the canonical "race story" view.
 * Each line is one driver, y-axis inverted so P1 is at the top.
 * Crossings = overtakes. Lines that end short = DNFs.
 *
 * Lap-time absolute values are dominated by pit stops + safety
 * cars so the previous lap-time-over-lap chart looked like noise;
 * position vs lap is what F1 broadcast graphics show.
 */
export function renderLapTimesChart(canvasId, laps) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  // Group: driver -> [{x: lap, y: position}]
  const byDriver = new Map();
  let maxLap = 0;
  for (const lap of laps) {
    if (lap.Position == null || lap.LapNumber == null) continue;
    const driver = lap.DriverCode || "UNK";
    if (!byDriver.has(driver)) {
      byDriver.set(driver, {
        team: lap.TeamCode || "UNK",
        points: [],
      });
    }
    byDriver.get(driver).points.push({
      x: Number(lap.LapNumber),
      y: Number(lap.Position),
    });
    maxLap = Math.max(maxLap, Number(lap.LapNumber));
  }

  if (byDriver.size === 0) {
    ctx.parentElement.innerHTML =
      '<p style="color:var(--text-muted);padding:20px">No lap-by-lap position data for this race.</p>';
    return;
  }

  // Sort each driver's points by lap.
  for (const d of byDriver.values()) {
    d.points.sort((a, b) => a.x - b.x);
  }

  // Order drivers by their final position so the legend reads top→bottom.
  const finalPositions = Array.from(byDriver.entries())
    .map(([driver, info]) => ({
      driver,
      info,
      finalPos: info.points[info.points.length - 1]?.y ?? 99,
    }))
    .sort((a, b) => a.finalPos - b.finalPos);

  const datasets = finalPositions.map(({ driver, info, finalPos }) => ({
    label: `P${finalPos} ${driver}`,
    data: info.points,
    borderColor: config.teamColors[info.team] || "#8e8e9c",
    backgroundColor: "transparent",
    borderWidth: finalPos <= 3 ? 2.5 : 1.5,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0,
    spanGaps: false,
  }));

  chart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: {
          position: "right",
          labels: {
            color: "#8e8e9c",
            font: { size: 11 },
            boxWidth: 14,
            boxHeight: 2,
            padding: 6,
          },
        },
        tooltip: {
          callbacks: {
            title: (items) => `Lap ${items[0].parsed.x}`,
            label: (item) => `${item.dataset.label.replace(/^P\d+\s/, "")}: P${item.parsed.y}`,
          },
        },
        title: {
          display: true,
          text: "Position by lap — overtakes are line crossings, DNFs end short",
          color: "#8e8e9c",
          font: { size: 11, weight: "normal" },
          padding: { bottom: 12 },
        },
      },
      scales: {
        x: {
          type: "linear",
          min: 1,
          max: maxLap,
          title: { display: true, text: "Lap", color: "#8e8e9c" },
          ticks: { color: "#8e8e9c", stepSize: 5 },
          grid: { color: "#2a2a38" },
        },
        y: {
          reverse: true,
          min: 1,
          max: 20,
          title: { display: true, text: "Position", color: "#8e8e9c" },
          ticks: {
            color: "#8e8e9c",
            stepSize: 1,
            callback: (v) => (Number.isInteger(v) ? `P${v}` : ""),
          },
          grid: { color: "#2a2a38" },
        },
      },
    },
  });
}
