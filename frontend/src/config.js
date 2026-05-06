// Runtime config. In production, replace API_BASE at build time (or via a
// loader script that fetches /config.json from the same origin).
const PRODUCTION_API = "https://nc264emm2i.execute-api.ap-southeast-2.amazonaws.com/dev";
const LOCAL_API = "http://localhost:3030";

const isLocal = typeof window !== "undefined" && /localhost|127\.0\.0\.1/.test(window.location.host);

export const config = {
  apiBase: isLocal ? LOCAL_API : PRODUCTION_API,
  currentSeason: 2024,
  teamColors: {
    RBR: "#1e3a8a",
    MCL: "#ff8000",
    FER: "#dc0000",
    MER: "#00d2be",
    AST: "#006f62",
    ALP: "#0090ff",
    WIL: "#005aff",
    RB: "#6692ff",
    SAU: "#52e252",
    HAA: "#b6babd",
  },
  compoundColors: {
    SOFT: "#ff3737",
    MEDIUM: "#ffd633",
    HARD: "#f4f4f8",
    INTERMEDIATE: "#43b04a",
    WET: "#3782e5",
  },
};
