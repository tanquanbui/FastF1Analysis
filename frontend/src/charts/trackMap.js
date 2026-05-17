import { TRACKS } from "./tracks_data.js";

/**
 * Render a F1-broadcast-style schematic of a circuit into ``container``.
 * Sectors are coloured arcs along the track, DRS zones get a thick green
 * stroke overlay, the pit-lane marker is dashed, and overtake spots are
 * dots with labels.
 */
export function renderTrackMap(containerId, circuitKey) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const track = TRACKS[circuitKey];
  if (!track) {
    container.innerHTML = `
      <p style="color:var(--text-muted);padding:24px;text-align:center">
        No schematic yet for circuit <code>${circuitKey}</code>.<br/>
        Available: ${Object.keys(TRACKS).join(", ")}.
      </p>`;
    return;
  }

  const sectorColors = ["#e8002d", "#f5a524", "#3782e5"];

  // Build per-sector path layers via stroke-dasharray.
  // We measure the path length once and slice using dash offsets.
  const sectorLayers = track.sectors
    .map((s, i) => {
      const color = sectorColors[i] || "#8e8e9c";
      const len = "{TRACK_LEN}"; // replaced after measurement below
      const visible = `${(s.to - s.from) * len} ${len}`;
      const offset = `${-s.from * len}`;
      return `<path class="track-sector" data-from="${s.from}" data-to="${s.to}"
        d="${track.path}" fill="none" stroke="${color}"
        stroke-width="14" stroke-linecap="round" stroke-linejoin="round"
        stroke-dasharray="${visible}" stroke-dashoffset="${offset}" opacity="0.95" />`;
    })
    .join("");

  const drsLines = (track.drs || [])
    .map(
      (z, i) => `
        <line class="drs-zone" x1="${z.from[0]}" y1="${z.from[1]}" x2="${z.to[0]}" y2="${z.to[1]}"
          stroke="#22c55e" stroke-width="6" stroke-linecap="round" opacity="0.85" />
        <text x="${(z.from[0] + z.to[0]) / 2}" y="${(z.from[1] + z.to[1]) / 2 - 14}"
          fill="#22c55e" font-size="12" font-weight="700" text-anchor="middle"
          style="text-shadow:0 0 4px rgba(0,0,0,0.8)">${z.label}</text>`,
    )
    .join("");

  const overtakeDots = (track.overtake_spots || [])
    .map(
      (s, i) => `
        <g class="overtake-spot">
          <circle cx="${s.x}" cy="${s.y}" r="8" fill="#e8002d" stroke="#fff" stroke-width="2"/>
          <text x="${s.x + 12}" y="${s.y + 5}" fill="#fff" font-size="11" font-weight="600">${s.label}</text>
        </g>`,
    )
    .join("");

  const pitMarker = track.pit_lane
    ? `<g>
        <circle cx="${track.pit_lane.at[0]}" cy="${track.pit_lane.at[1]}" r="6" fill="#fff" stroke="#0a0a0f" stroke-width="2"/>
        <text x="${track.pit_lane.at[0] + 12}" y="${track.pit_lane.at[1] + 4}" fill="#aaa" font-size="11">${track.pit_lane.label}</text>
       </g>`
    : "";

  container.innerHTML = `
    <div class="track-header">
      <div>
        <h2 class="track-name">${track.name}</h2>
        <p class="muted-h3">${track.length_km} km · ${track.corners} corners · ${track.drs_zones} DRS zone(s) · ${track.laps_2024} laps</p>
      </div>
      <div class="track-legend">
        <span><span class="dot" style="background:#e8002d"></span>Sector 1</span>
        <span><span class="dot" style="background:#f5a524"></span>Sector 2</span>
        <span><span class="dot" style="background:#3782e5"></span>Sector 3</span>
        <span><span class="dot" style="background:#22c55e"></span>DRS zone</span>
        <span><span class="dot" style="background:#fff"></span>Overtake spot</span>
      </div>
    </div>
    <svg viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid meet" class="track-svg">
      <defs>
        <filter id="trackShadow" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur in="SourceAlpha" stdDeviation="3"/>
          <feOffset dx="0" dy="2"/>
          <feComponentTransfer><feFuncA type="linear" slope="0.4"/></feComponentTransfer>
          <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      <!-- base outline (dark grey under-track) -->
      <path d="${track.path}" fill="none" stroke="#2a2a38" stroke-width="22" stroke-linecap="round" stroke-linejoin="round"/>
      <!-- sectors -->
      <g id="sectors">${sectorLayers}</g>
      <!-- DRS overlays -->
      <g id="drs">${drsLines}</g>
      <!-- pit + overtakes on top -->
      ${pitMarker}
      ${overtakeDots}
    </svg>
    <p class="track-notes">${track.notes || ""}</p>
  `;

  // Measure the actual path length, then patch the sector dash arrays.
  const svg = container.querySelector("svg");
  const measure = svg.querySelector("path");
  const totalLen = measure.getTotalLength();
  container.querySelectorAll(".track-sector").forEach((p) => {
    const from = Number(p.dataset.from);
    const to = Number(p.dataset.to);
    const seg = (to - from) * totalLen;
    p.setAttribute("stroke-dasharray", `${seg} ${totalLen}`);
    p.setAttribute("stroke-dashoffset", `${-from * totalLen}`);
  });
}
