import { config } from "./config.js";

async function request(path) {
  const url = `${config.apiBase}${path}`;
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`${response.status} ${response.statusText} — ${detail.slice(0, 120)}`);
  }
  return response.json();
}

export const api = {
  // Phase 1
  listSeasonRaces: (year) => request(`/races/${year}`),
  getRaceDetail: (year, round) => request(`/races/${year}/${round}`),
  getQualifying: (year, round) => request(`/qualifying/${year}/${round}`),
  getDriverProfile: (code) => request(`/drivers/${code}`),
  getTeamProfile: (code) => request(`/teams/${code}`),
  getStandings: (year, round) => request(`/standings/${year}/${round}`),

  // Phase 2
  getPredictions: (year, round) => request(`/predictions/${year}/${round}`),
  getDriverPredictions: (year, round) => request(`/predictions/${year}/${round}/drivers`),
  getTeamFingerprint: (code) => request(`/team/${code}/fingerprint`),
  getTeamCircuit: (code, circuitKey) => request(`/team/${code}/circuit/${circuitKey}`),
  getCircuitTeams: (circuitKey) => request(`/circuit/${circuitKey}/teams`),
  getChampionshipScenarios: (year) => request(`/championship/${year}/scenarios`),
  getUpgrades: (year, teamCode) => request(`/upgrades/${year}/${teamCode}`),
};
