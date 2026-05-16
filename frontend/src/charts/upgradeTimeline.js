let chart;

export function renderUpgradeTimeline(canvasId, events) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  // Each event has detected_at_race + affected_dimensions[] + delta{dim: value}.
  // Plot the max delta per event so the timeline shows upgrade magnitude.
  const points = (events || []).map((e) => {
    const deltas = Object.values(e.delta || {});
    const maxDelta = deltas.length ? Math.max(...deltas) : 0;
    return {
      x: e.detected_at_race ?? 0,
      y: maxDelta,
      dims: (e.affected_dimensions || []).join(", "),
      confidence: e.confidence ?? 0,
    };
  });

  chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: points.map((p) => `R${p.x}`),
      datasets: [
        {
          label: "Max dimension delta",
          data: points.map((p) => p.y),
          backgroundColor: points.map((p) => (p.confidence > 0.75 ? "#e8002d" : "#f5a524")),
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterBody: (items) => {
              const i = items[0].dataIndex;
              return `Dimensions: ${points[i].dims}\nConfidence: ${points[i].confidence.toFixed(2)}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: "#8e8e9c" }, grid: { display: false } },
        y: { ticks: { color: "#8e8e9c" }, grid: { color: "#2a2a38" }, title: { display: true, text: "Δ fingerprint", color: "#8e8e9c" } },
      },
    },
  });
}
