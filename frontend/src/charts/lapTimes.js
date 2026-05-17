import { config } from "../config.js";

let chart;

// ---------- Public dispatcher ----------

export function renderRaceProgression(canvasId, laps, view = "position") {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  if (!laps || laps.length === 0) {
    ctx.parentElement.innerHTML = '<p style="color:var(--text-muted);padding:20px">No lap data for this race.</p>';
    return;
  }

  switch (view) {
    case "gap":
      renderGapToWinner(ctx, laps);
      break;
    case "pace":
      renderStintPace(ctx, laps);
      break;
    case "position":
    default:
      renderPositionByLap(ctx, laps);
      break;
  }
}

// Kept for backwards compat with the old main.js call site.
export const renderLapTimesChart = renderRaceProgression;

// ---------- View 1: Position by lap ----------

function renderPositionByLap(ctx, laps) {
  const byDriver = groupByDriver(laps, (lap) => ({
    x: Number(lap.LapNumber),
    y: Number(lap.Position),
  }));
  const maxLap = Math.max(...laps.map((l) => Number(l.LapNumber)).filter(Number.isFinite));

  const datasets = sortByFinalY(byDriver).map(({ driver, info, finalY }) => ({
    label: `P${finalY} ${driver}`,
    data: info.points,
    borderColor: config.teamColors[info.team] || "#8e8e9c",
    backgroundColor: "transparent",
    borderWidth: finalY <= 3 ? 2.5 : 1.5,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0,
  }));

  chart = baseChart(ctx, datasets, {
    title: "Position by lap — crossings are overtakes, lines that end short are DNFs",
    xMax: maxLap,
    y: {
      reverse: true,
      min: 1,
      max: 20,
      title: { display: true, text: "Position", color: "#8e8e9c" },
      ticks: { color: "#8e8e9c", stepSize: 1, callback: (v) => (Number.isInteger(v) ? `P${v}` : "") },
      grid: { color: "#2a2a38" },
    },
    tooltipLabel: (item) => `${item.dataset.label.replace(/^P\d+\s/, "")}: P${item.parsed.y}`,
  });
}

// ---------- View 2: Gap to race winner ----------

function renderGapToWinner(ctx, laps) {
  // Build cumulative race time per driver per lap.
  const cumByDriver = new Map();
  const sorted = [...laps].sort((a, b) => (a.LapNumber || 0) - (b.LapNumber || 0));
  for (const lap of sorted) {
    if (lap.LapTimeSeconds == null || lap.DriverCode == null || lap.LapNumber == null) continue;
    if (!cumByDriver.has(lap.DriverCode)) {
      cumByDriver.set(lap.DriverCode, { team: lap.TeamCode, totals: [] });
    }
    const driver = cumByDriver.get(lap.DriverCode);
    const prev = driver.totals.length ? driver.totals[driver.totals.length - 1].cum : 0;
    driver.totals.push({
      lap: Number(lap.LapNumber),
      cum: prev + Number(lap.LapTimeSeconds),
    });
  }

  // Pick the winner = driver with smallest cumulative time at the highest shared lap.
  const maxLap = Math.max(...Array.from(cumByDriver.values()).map((d) => d.totals.length));
  let winnerCode = null;
  let winnerCum = Infinity;
  for (const [code, d] of cumByDriver.entries()) {
    const final = d.totals[d.totals.length - 1];
    if (final && final.lap >= maxLap - 2 && final.cum < winnerCum) {
      winnerCum = final.cum;
      winnerCode = code;
    }
  }
  if (!winnerCode) {
    ctx.parentElement.innerHTML =
      '<p style="color:var(--text-muted);padding:20px">No reliable lap-time data for gap calculation.</p>';
    return;
  }
  const winner = cumByDriver.get(winnerCode);
  const winnerCumByLap = new Map(winner.totals.map((t) => [t.lap, t.cum]));

  // For each driver, gap-to-winner at each shared lap.
  const datasets = [];
  for (const [code, d] of cumByDriver.entries()) {
    if (code === winnerCode) continue;
    const points = d.totals
      .filter((t) => winnerCumByLap.has(t.lap))
      .map((t) => ({ x: t.lap, y: round2(t.cum - winnerCumByLap.get(t.lap)) }));
    if (points.length === 0) continue;
    const finalGap = points[points.length - 1].y;
    datasets.push({
      label: `${code} +${finalGap.toFixed(1)}s`,
      data: points,
      borderColor: config.teamColors[d.team] || "#8e8e9c",
      backgroundColor: "transparent",
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0,
      _finalY: finalGap,
    });
  }

  // Include the winner as a 0-line reference.
  datasets.unshift({
    label: `${winnerCode} 0.0s (winner)`,
    data: winner.totals.map((t) => ({ x: t.lap, y: 0 })),
    borderColor: "#e8002d",
    borderDash: [6, 4],
    borderWidth: 2,
    pointRadius: 0,
    _finalY: -1,
  });

  datasets.sort((a, b) => (a._finalY ?? 0) - (b._finalY ?? 0));

  chart = baseChart(ctx, datasets, {
    title: `Cumulative gap to race winner (${winnerCode}) — pit stops show as ~20s drops`,
    xMax: maxLap,
    y: {
      title: { display: true, text: "Gap (s)", color: "#8e8e9c" },
      ticks: {
        color: "#8e8e9c",
        callback: (v) => (v === 0 ? "0" : `+${v}s`),
      },
      grid: { color: "#2a2a38" },
    },
    tooltipLabel: (item) =>
      item.parsed.y === 0
        ? `${item.dataset.label}: leader`
        : `${item.dataset.label}: +${item.parsed.y.toFixed(1)}s`,
  });
}

// ---------- View 3: Stint pace ----------

function renderStintPace(ctx, laps) {
  // Compute median lap time per driver per stint, ignoring pit/SC laps.
  const byStint = new Map(); // key: driver|stint -> {driver, stint, team, compound, laps[]}
  for (const lap of laps) {
    if (lap.LapTimeSeconds == null || lap.Stint == null || lap.DriverCode == null) continue;
    if (lap.TrackStatus && String(lap.TrackStatus) !== "1") continue;
    const key = `${lap.DriverCode}|${lap.Stint}`;
    if (!byStint.has(key)) {
      byStint.set(key, {
        driver: lap.DriverCode,
        stint: Number(lap.Stint),
        team: lap.TeamCode,
        compound: lap.Compound,
        times: [],
      });
    }
    byStint.get(key).times.push(Number(lap.LapTimeSeconds));
  }

  const drivers = new Set();
  const stintRows = [];
  for (const v of byStint.values()) {
    if (v.times.length < 3) continue;
    drivers.add(v.driver);
    stintRows.push({
      ...v,
      median: median(v.times),
    });
  }

  if (stintRows.length === 0) {
    ctx.parentElement.innerHTML =
      '<p style="color:var(--text-muted);padding:20px">Not enough clean stint data for pace breakdown.</p>';
    return;
  }

  const driverOrder = Array.from(drivers).sort((a, b) => {
    const aBest = Math.min(...stintRows.filter((s) => s.driver === a).map((s) => s.median));
    const bBest = Math.min(...stintRows.filter((s) => s.driver === b).map((s) => s.median));
    return aBest - bBest;
  });

  const maxStint = Math.max(...stintRows.map((s) => s.stint));
  const compoundColor = (c) => config.compoundColors[c] || "#8e8e9c";

  const datasets = [];
  for (let s = 1; s <= maxStint; s++) {
    datasets.push({
      label: `Stint ${s}`,
      data: driverOrder.map((d) => {
        const row = stintRows.find((r) => r.driver === d && r.stint === s);
        return row ? round2(row.median) : null;
      }),
      backgroundColor: driverOrder.map((d) => {
        const row = stintRows.find((r) => r.driver === d && r.stint === s);
        return row ? compoundColor(row.compound) : "transparent";
      }),
      borderRadius: 3,
      barPercentage: 0.85,
      categoryPercentage: 0.85,
    });
  }

  chart = new Chart(ctx, {
    type: "bar",
    data: { labels: driverOrder, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: { labels: { color: "#8e8e9c" } },
        title: {
          display: true,
          text: "Median clean lap time per stint — bar colour = tyre compound",
          color: "#8e8e9c",
          font: { size: 11, weight: "normal" },
          padding: { bottom: 12 },
        },
        tooltip: {
          callbacks: {
            afterLabel: (item) => {
              const row = stintRows.find(
                (r) => r.driver === driverOrder[item.dataIndex] && r.stint === Number(item.dataset.label.replace("Stint ", "")),
              );
              return row ? `Tyre: ${row.compound} · ${row.times.length} laps` : "";
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#8e8e9c", callback: (v) => `${v.toFixed(1)}s` },
          grid: { color: "#2a2a38" },
          title: { display: true, text: "Median lap time (s)", color: "#8e8e9c" },
        },
        y: {
          ticks: { color: "#f4f4f8" },
          grid: { display: false },
        },
      },
    },
  });
}

// ---------- helpers ----------

function groupByDriver(laps, mapper) {
  const byDriver = new Map();
  for (const lap of laps) {
    const point = mapper(lap);
    if (point.y == null || point.x == null || Number.isNaN(point.x) || Number.isNaN(point.y)) continue;
    if (!byDriver.has(lap.DriverCode)) {
      byDriver.set(lap.DriverCode, { team: lap.TeamCode, points: [] });
    }
    byDriver.get(lap.DriverCode).points.push(point);
  }
  for (const d of byDriver.values()) d.points.sort((a, b) => a.x - b.x);
  return byDriver;
}

function sortByFinalY(byDriver) {
  return Array.from(byDriver.entries())
    .map(([driver, info]) => ({
      driver,
      info,
      finalY: info.points[info.points.length - 1]?.y ?? 99,
    }))
    .sort((a, b) => a.finalY - b.finalY);
}

function baseChart(ctx, datasets, { title, xMax, y, tooltipLabel }) {
  return new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: {
          position: "right",
          labels: { color: "#8e8e9c", font: { size: 10 }, boxWidth: 14, boxHeight: 2, padding: 4 },
        },
        tooltip: {
          callbacks: {
            title: (items) => `Lap ${items[0].parsed.x}`,
            label: tooltipLabel,
          },
        },
        title: {
          display: true,
          text: title,
          color: "#8e8e9c",
          font: { size: 11, weight: "normal" },
          padding: { bottom: 12 },
        },
      },
      scales: {
        x: {
          type: "linear",
          min: 1,
          max: xMax,
          title: { display: true, text: "Lap", color: "#8e8e9c" },
          ticks: { color: "#8e8e9c", stepSize: 5 },
          grid: { color: "#2a2a38" },
        },
        y,
      },
    },
  });
}

function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function round2(n) {
  return Math.round(n * 100) / 100;
}
