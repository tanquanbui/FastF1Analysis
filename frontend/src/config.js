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
  teamNames: {
    RBR: "Red Bull Racing",
    MCL: "McLaren",
    FER: "Scuderia Ferrari",
    MER: "Mercedes-AMG Petronas",
    AST: "Aston Martin Aramco",
    ALP: "BWT Alpine",
    WIL: "Williams Racing",
    RB: "Visa Cash App RB",
    SAU: "Kick Sauber",
    HAA: "MoneyGram Haas",
  },
  // Driver code → ISO 3166-1 alpha-2 country code; used to render flag
  // emojis next to the driver name in the top 10.
  driverCountry: {
    VER: "NL", PER: "MX",
    LEC: "MC", SAI: "ES",
    HAM: "GB", RUS: "GB",
    NOR: "GB", PIA: "AU",
    ALO: "ES", STR: "CA",
    GAS: "FR", OCO: "FR",
    ALB: "TH", COL: "AR", SAR: "US",
    TSU: "JP", RIC: "AU", LAW: "NZ",
    HUL: "DE", MAG: "DK", BEA: "GB",
    BOT: "FI", ZHO: "CN",
    ANT: "IT", DOO: "AU",
  },
  compoundColors: {
    SOFT: "#ff3737",
    MEDIUM: "#ffd633",
    HARD: "#f4f4f8",
    INTERMEDIATE: "#43b04a",
    WET: "#3782e5",
  },
};
