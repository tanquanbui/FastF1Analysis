// The simulator server (python -m simulator.server) serves both the API and
// this dashboard, so API calls are same-origin.
export const config = {
  apiBase: "",
  seasons: [2026, 2025, 2024],
  defaultSeason: 2024,
  teamColors: {
    RBR: "#3671c6",
    MCL: "#ff8000",
    FER: "#e8002d",
    MER: "#27f4d2",
    AST: "#229971",
    ALP: "#0093cc",
    WIL: "#64c4ff",
    RB: "#6692ff",
    SAU: "#52e252",
    AUD: "#a6a6a6",
    HAA: "#b6babd",
    CAD: "#c9a227",
  },
  compoundColors: {
    SOFT: "#ff3737",
    MEDIUM: "#ffd633",
    HARD: "#f4f4f8",
    INTERMEDIATE: "#43b04a",
    WET: "#3782e5",
  },
  presets: [
    "Rain arrives on lap 30 and lasts 10 laps",
    "Safety car on lap 12 after a first-sector crash",
    "The pole sitter starts from the pit lane",
    "Front-runners gamble on an aggressive two-stop",
    "Track temperature is 15°C hotter than expected",
    "Red flag at half distance",
  ],
  whatIfPresets: [
    "What if the leader had pitted 3 laps earlier?",
    "What if there had been no safety car?",
    "What if P2 had started on hard tyres?",
  ],
};
