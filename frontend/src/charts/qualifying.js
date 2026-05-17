import { config } from "../config.js";

/**
 * Interactive Q1/Q2/Q3 viewer. Tabs across the top; each tab shows the
 * 20-driver field for that session with their best time, gap to pole,
 * and a bar visualising the delta. Drivers eliminated in Q1 / Q2 are
 * visually muted in subsequent tabs.
 */
export function renderQualifyingViewer(containerId, qualifyingItems) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!qualifyingItems || qualifyingItems.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);padding:24px">No qualifying data for this race yet.</p>';
    return;
  }

  // Normalise — convert "m:ss.ms" / "ss.ms" strings to seconds.
  const drivers = qualifyingItems
    .map((q) => ({
      code: q.DriverCode,
      name: q.DriverName,
      team: q.TeamCode,
      position: Number(q.Position) || 99,
      q1: parseQ(q.Q1),
      q2: parseQ(q.Q2),
      q3: parseQ(q.Q3),
    }))
    .sort((a, b) => a.position - b.position);

  // Render skeleton
  container.innerHTML = `
    <div class="qual-tabs" role="tablist">
      <button class="qual-tab active" data-session="q3">Q3 (Top 10)</button>
      <button class="qual-tab" data-session="q2">Q2 (Top 15)</button>
      <button class="qual-tab" data-session="q1">Q1 (Full Field)</button>
    </div>
    <div class="qual-body"></div>`;

  const renderSession = (session) => {
    const body = container.querySelector(".qual-body");
    const valid = drivers.filter((d) => d[session] != null);
    if (valid.length === 0) {
      body.innerHTML = `<p style="color:var(--text-muted);padding:24px">No times recorded for ${session.toUpperCase()}.</p>`;
      return;
    }

    const pole = Math.min(...valid.map((d) => d[session]));
    const maxGap = Math.max(...valid.map((d) => d[session] - pole));
    const eliminationSet = new Set(
      drivers
        .filter((d) => !d.q2 && d.q1)
        .map((d) => d.code), // q1 eliminated
    );
    const q2Eliminated = new Set(
      drivers
        .filter((d) => !d.q3 && d.q2 && d.q1)
        .map((d) => d.code),
    );

    const rows = drivers
      .filter((d) => d[session] != null)
      .sort((a, b) => a[session] - b[session])
      .map((d, idx) => {
        const time = d[session];
        const gap = time - pole;
        const widthPct = maxGap > 0 ? Math.max(2, (gap / maxGap) * 100) : 2;
        const teamColor = config.teamColors[d.team] || "#8e8e9c";
        const teamName = config.teamNames[d.team] || d.team;
        const flag = flagFor(config.driverCountry[d.code]);
        const isEliminatedHere =
          (session === "q1" && eliminationSet.has(d.code)) ||
          (session === "q2" && q2Eliminated.has(d.code));
        const cls = isEliminatedHere ? "qual-row eliminated" : "qual-row";

        return `
          <div class="${cls}">
            <span class="qual-pos">${idx + 1}</span>
            <span class="qual-driver">
              <span class="flag">${flag}</span>
              <span class="driver-name">${d.name || d.code}</span>
              <span class="qual-team-pill" style="background:${teamColor}"></span>
              <span class="qual-team-name">${teamName}</span>
            </span>
            <span class="qual-time">${formatTime(time)}</span>
            <span class="qual-gap-cell">
              <span class="qual-gap-bar"><span style="width:${widthPct}%; background:${teamColor}"></span></span>
              <span class="qual-gap-text">${idx === 0 ? "—" : `+${gap.toFixed(3)}s`}</span>
            </span>
          </div>`;
      })
      .join("");

    const eliminatedNote =
      session !== "q1"
        ? `<p class="muted-h3" style="margin-top:14px">${
            session === "q3" ? "10 fastest from Q2 advance." : "15 fastest from Q1 advance."
          } Eliminated drivers shown muted.</p>`
        : `<p class="muted-h3" style="margin-top:14px">Full field. Slowest 5 are eliminated.</p>`;

    body.innerHTML = `
      <p class="muted-h3">Pole: <strong>${formatTime(pole)}</strong> · ${valid.length} drivers set a time</p>
      <div class="qual-grid">${rows}</div>
      ${eliminatedNote}`;
  };

  renderSession("q3");

  container.querySelectorAll(".qual-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll(".qual-tab").forEach((b) => b.classList.toggle("active", b === btn));
      renderSession(btn.dataset.session);
    });
  });
}

function parseQ(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number") return value;
  const s = String(value);
  if (s.includes(":")) {
    const [m, ss] = s.split(":", 2);
    const minutes = parseInt(m, 10);
    const seconds = parseFloat(ss);
    if (Number.isNaN(minutes) || Number.isNaN(seconds)) return null;
    return minutes * 60 + seconds;
  }
  const f = parseFloat(s);
  return Number.isNaN(f) ? null : f;
}

function formatTime(seconds) {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(3);
  return m > 0 ? `${m}:${s.padStart(6, "0")}` : `${s}s`;
}

function flagFor(code) {
  if (!code) return "";
  return code
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(127397 + c.charCodeAt(0)))
    .join("");
}
