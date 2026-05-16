const DIMENSIONS = [
  "straight_line_speed",
  "high_speed_cornering",
  "low_speed_cornering",
  "tyre_management",
  "qualifying_pace",
  "race_pace_conversion",
  "tyre_strategy_execution",
  "wet_weather_performance",
];

const LABELS = {
  straight_line_speed: "Straight Speed",
  high_speed_cornering: "High-Speed Corners",
  low_speed_cornering: "Low-Speed Corners",
  tyre_management: "Tyre Management",
  qualifying_pace: "Qualifying Pace",
  race_pace_conversion: "Race Conversion",
  tyre_strategy_execution: "Strategy Execution",
  wet_weather_performance: "Wet Weather",
};

let chart;

export function renderTeamFingerprintRadar(canvasId, dimensions) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  const data = DIMENSIONS.map((dim) => dimensions[dim] ?? 0);

  chart = new Chart(ctx, {
    type: "radar",
    data: {
      labels: DIMENSIONS.map((d) => LABELS[d]),
      datasets: [
        {
          label: "Fingerprint",
          data,
          backgroundColor: "rgba(232, 0, 45, 0.18)",
          borderColor: "#e8002d",
          pointBackgroundColor: "#e8002d",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        r: {
          beginAtZero: true,
          max: 100,
          ticks: { color: "#8e8e9c", backdropColor: "transparent", stepSize: 20 },
          grid: { color: "#2a2a38" },
          angleLines: { color: "#2a2a38" },
          pointLabels: { color: "#f4f4f8", font: { size: 11 } },
        },
      },
    },
  });
}
