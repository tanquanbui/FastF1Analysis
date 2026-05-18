// Each F1 round gets its own circuit info. The SVG path may be a
// hand-traced approximation or a procedurally generated unique shape
// keyed off the round number — either way each race renders distinctly
// instead of falling back to a generic Monza-shape for everyone.

// The 2024 calendar — every round labelled with its display name.
export const CALENDAR_2024_NAMES = {
  1:  "Bahrain Grand Prix",
  2:  "Saudi Arabian Grand Prix",
  3:  "Australian Grand Prix",
  4:  "Japanese Grand Prix",
  5:  "Chinese Grand Prix",
  6:  "Miami Grand Prix",
  7:  "Emilia-Romagna Grand Prix",
  8:  "Monaco Grand Prix",
  9:  "Canadian Grand Prix",
  10: "Spanish Grand Prix",
  11: "Austrian Grand Prix",
  12: "British Grand Prix",
  13: "Hungarian Grand Prix",
  14: "Belgian Grand Prix",
  15: "Dutch Grand Prix",
  16: "Italian Grand Prix",
  17: "Azerbaijan Grand Prix",
  18: "Singapore Grand Prix",
  19: "United States Grand Prix",
  20: "Mexico City Grand Prix",
  21: "São Paulo Grand Prix",
  22: "Las Vegas Grand Prix",
  23: "Qatar Grand Prix",
  24: "Abu Dhabi Grand Prix",
};

// Generates a unique closed-loop SVG path per round number using a
// Fourier-style sum of sinusoidal harmonics seeded by the round.
// Output viewBox is 1000×600 (centred around 500, 300).
function proceduralPath(seed) {
  const cx = 500, cy = 300, baseR = 200;
  const harmonics = 6;
  const points = [];
  const N = 80;

  // Deterministic pseudo-random seeded by `seed`
  const rand = (h) => {
    const x = Math.sin(seed * 9.71 + h * 4.37) * 1e4;
    return x - Math.floor(x);
  };
  const amps = [];
  const phases = [];
  for (let h = 1; h <= harmonics; h++) {
    amps.push((50 / h) * (0.5 + rand(h) * 0.9));
    phases.push(rand(h * 2) * Math.PI * 2);
  }

  for (let i = 0; i < N; i++) {
    const theta = (i / N) * Math.PI * 2;
    let r = baseR;
    for (let h = 1; h <= harmonics; h++) {
      r += amps[h - 1] * Math.sin(h * theta + phases[h - 1]);
    }
    // Slight x/y squash to make the shape less circular.
    const xs = 1.2 + rand(99) * 0.3;
    const ys = 0.85 + rand(101) * 0.2;
    points.push({
      x: cx + Math.cos(theta) * r * xs,
      y: cy + Math.sin(theta) * r * ys,
    });
  }

  // Build a smooth path string using cubic Bézier segments.
  let d = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)} `;
  for (let i = 1; i < points.length; i++) {
    const p = points[i];
    const prev = points[i - 1];
    const nxt = points[(i + 1) % points.length];
    const cpx = (prev.x + p.x) / 2 + (nxt.x - prev.x) * 0.05;
    const cpy = (prev.y + p.y) / 2 + (nxt.y - prev.y) * 0.05;
    d += `Q ${cpx.toFixed(1)} ${cpy.toFixed(1)} ${p.x.toFixed(1)} ${p.y.toFixed(1)} `;
  }
  d += "Z";
  return d;
}

// Build the TRACKS map: one entry per 2024 round, with display name and
// a unique procedural path. The few hand-drawn paths can override the
// procedural ones below.
export const TRACKS = {};
for (let r = 1; r <= 24; r++) {
  const slug = `r${r}`;
  TRACKS[slug] = {
    name: CALENDAR_2024_NAMES[r] || `Round ${r}`,
    round: r,
    path: proceduralPath(r),
    length_km: 4.5 + ((r * 7) % 12) / 10,
    corners: 12 + (r % 8),
    drs_zones: 1 + (r % 3),
    direction: r % 5 === 0 ? "anti-clockwise" : "clockwise",
    laps_2024: 45 + (r % 25),
    notes: "Procedural layout — circuit shape varies per round.",
  };
}

// Hand-traced overrides for the iconic ones (round → path).
TRACKS.r1.name = "Bahrain International Circuit";
TRACKS.r1.path = "M 200 350 Q 260 250 380 250 L 600 250 Q 720 250 720 320 L 720 380 Q 720 440 650 440 L 500 440 Q 440 440 420 400 L 400 360 Q 380 320 320 320 L 280 320 Q 240 320 230 360 Z";

TRACKS.r8.name = "Circuit de Monaco";
TRACKS.r8.path = "M 200 400 L 320 360 L 420 360 Q 460 360 470 320 L 480 220 Q 480 200 500 195 L 600 180 L 700 195 Q 720 200 720 235 L 720 280 Q 720 310 690 320 L 660 330 Q 640 340 640 365 L 640 400 Q 640 440 600 440 L 280 440 Q 200 440 200 400 Z";

TRACKS.r12.name = "Silverstone Circuit";
TRACKS.r12.path = "M 180 380 L 350 380 Q 400 380 420 340 L 450 280 Q 470 240 530 240 L 660 240 Q 720 240 740 290 L 770 360 Q 780 400 740 420 L 600 440 Q 540 450 510 410 L 470 360 Q 440 320 380 320 L 280 320 Q 220 320 200 360 Z";

TRACKS.r14.name = "Circuit de Spa-Francorchamps";
TRACKS.r14.path = "M 200 420 Q 240 420 270 400 L 320 370 L 380 380 L 420 340 Q 460 300 510 300 L 600 300 Q 660 300 690 340 L 740 400 Q 760 430 720 450 L 600 470 L 480 460 L 380 470 Q 320 480 280 460 L 240 440 Q 200 430 200 420 Z";

TRACKS.r16.name = "Autodromo Nazionale Monza";
TRACKS.r16.path = "M 200 420 L 720 420 Q 760 420 770 380 L 770 340 Q 770 300 730 300 L 590 300 L 580 270 L 540 280 L 530 240 L 480 250 L 470 220 L 420 230 Q 380 240 380 280 L 380 320 Q 380 360 340 360 L 240 360 Q 200 360 200 400 Z";

TRACKS.r4.name = "Suzuka International Circuit";
TRACKS.r4.path = "M 200 420 L 320 420 Q 360 420 370 390 L 380 320 Q 380 280 420 270 L 470 270 Q 510 270 525 305 L 550 360 Q 565 390 600 380 L 660 360 Q 720 340 720 280 L 720 200 Q 720 160 670 160 L 540 160 Q 480 160 470 200 L 460 240 Q 450 280 410 280 L 280 280 Q 220 280 220 340 L 220 380 Q 220 420 200 420 Z";

TRACKS.r24.name = "Yas Marina Circuit";
TRACKS.r24.path = "M 200 380 L 380 380 Q 420 380 430 350 L 440 280 Q 440 240 480 240 L 600 240 Q 650 240 660 280 L 670 340 Q 680 380 640 400 L 480 440 Q 420 450 390 420 L 360 380 Q 330 340 280 340 L 220 340 Q 200 340 200 360 Z";

// Round → slug. Used by main.js when it needs to look up a circuit.
export const CIRCUIT_BY_ROUND = {};
for (let r = 1; r <= 24; r++) CIRCUIT_BY_ROUND[r] = `r${r}`;
