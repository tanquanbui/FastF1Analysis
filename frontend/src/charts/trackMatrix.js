import { config } from "../config.js";

let chart;

export function renderTrackMatrix(canvasId, teams) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (chart) chart.destroy();

  const sorted = [...teams].sort((a, b) => (b.compatibility_score || 0) - (a.compatibility_score || 0));

  chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: sorted.map((t) => t.team_code),
      datasets: [
        {
          label: "Compatibility (0–100)",
          data: sorted.map((t) => t.compatibility_score || 0),
          backgroundColor: sorted.map((t) => config.teamColors[t.team_code] || "#8e8e9c"),
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
        tooltip: {
          callbacks: {
            afterBody: (items) => {
              const team = sorted[items[0].dataIndex];
              const lines = [];
              if (team.strengths_exploited?.length) lines.push(`Strengths: ${team.strengths_exploited.join(", ")}`);
              if (team.weaknesses_exposed?.length) lines.push(`Weaknesses: ${team.weaknesses_exposed.join(", ")}`);
              return lines.join("\n");
            },
          },
        },
      },
      scales: {
        x: { max: 100, ticks: { color: "#8e8e9c" }, grid: { color: "#2a2a38" } },
        y: { ticks: { color: "#f4f4f8", font: { weight: "600" } }, grid: { display: false } },
      },
    },
  });
}
