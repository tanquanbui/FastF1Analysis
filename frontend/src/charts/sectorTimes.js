import { config } from "../config.js";

let chart;

/**
 * Sector breakdown — shows each driver's gap (in seconds) to the
 * sector-fastest driver per sector. Absolute sector times all sit
 * around 28-34s so a stacked total looks flat; deltas amplify the
 * 0.05-0.5s differences that actually matter.
 */
export function renderSectorTimesChart(canvasId, laps) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  // Per driver, take their best in each sector.
  const byDriver = new Map();
  for (const lap of laps) {
    const driver = lap.DriverCode;
    if (!driver) continue;
    const e = byDriver.get(driver) || {
      s1: Infinity,
      s2: Infinity,
      s3: Infinity,
      team: lap.TeamCode,
    };
    if (lap.Sector1Seconds != null) e.s1 = Math.min(e.s1, lap.Sector1Seconds);
    if (lap.Sector2Seconds != null) e.s2 = Math.min(e.s2, lap.Sector2Seconds);
    if (lap.Sector3Seconds != null) e.s3 = Math.min(e.s3, lap.Sector3Seconds);
    e.team = lap.TeamCode || e.team;
    byDriver.set(driver, e);
  }

  const drivers = Array.from(byDriver.entries()).filter(
    ([, d]) => Number.isFinite(d.s1) && Number.isFinite(d.s2) && Number.isFinite(d.s3),
  );

  if (drivers.length === 0) {
    ctx.parentElement.innerHTML = '<p style="color:var(--text-muted);padding:20px">No sector data for this race.</p>';
    return;
  }

  // Sector-fastest baselines.
  const bestS1 = Math.min(...drivers.map(([, d]) => d.s1));
  const bestS2 = Math.min(...drivers.map(([, d]) => d.s2));
  const bestS3 = Math.min(...drivers.map(([, d]) => d.s3));

  // Sort by total delta so the strongest cars float to the top.
  drivers.sort(
    ([, a], [, b]) =>
      a.s1 + a.s2 + a.s3 - (b.s1 + b.s2 + b.s3),
  );

  const labels = drivers.map(([d]) => d);
  const d1 = drivers.map(([, d]) => round3(d.s1 - bestS1));
  const d2 = drivers.map(([, d]) => round3(d.s2 - bestS2));
  const d3 = drivers.map(([, d]) => round3(d.s3 - bestS3));

  chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Sector 1 Δ",
          data: d1,
          backgroundColor: "#e8002d",
          borderRadius: 2,
          barPercentage: 0.85,
        },
        {
          label: "Sector 2 Δ",
          data: d2,
          backgroundColor: "#f5a524",
          borderRadius: 2,
          barPercentage: 0.85,
        },
        {
          label: "Sector 3 Δ",
          data: d3,
          backgroundColor: "#3782e5",
          borderRadius: 2,
          barPercentage: 0.85,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: {
          labels: { color: "#8e8e9c" },
        },
        tooltip: {
          callbacks: {
            label: (item) => {
              const delta = item.parsed.x;
              if (delta === 0) return `${item.dataset.label}: fastest (purple sector)`;
              return `${item.dataset.label}: +${delta.toFixed(3)}s vs fastest`;
            },
          },
        },
        title: {
          display: true,
          text: `Δ to sector best — purple sectors S1 ${bestS1.toFixed(3)}s · S2 ${bestS2.toFixed(3)}s · S3 ${bestS3.toFixed(3)}s`,
          color: "#8e8e9c",
          font: { size: 11, weight: "normal" },
          padding: { bottom: 12 },
        },
      },
      scales: {
        x: {
          stacked: false,
          ticks: {
            color: "#8e8e9c",
            callback: (v) => `+${v.toFixed(2)}s`,
          },
          grid: { color: "#2a2a38" },
          title: {
            display: true,
            text: "Gap to sector best",
            color: "#8e8e9c",
          },
        },
        y: {
          ticks: { color: "#f4f4f8", font: { size: 11 } },
          grid: { display: false },
        },
      },
    },
  });
}

function round3(n) {
  return Math.round(n * 1000) / 1000;
}
