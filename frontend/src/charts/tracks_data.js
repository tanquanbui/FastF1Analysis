// Per-circuit schematic data. Path strings are hand-traced approximations
// of the real circuit shape — accurate enough for an at-a-glance visual
// without infringing on official F1 imagery.
//
// Coordinates assume a 1000 × 600 viewBox. Sectors are { from, to }
// percentages along the path's stroke-dasharray. DRS zones, overtake
// spots, and pit-lane markers are pixel coordinates relative to the path.

export const TRACKS = {
  bahrain: {
    name: "Bahrain International Circuit",
    length_km: 5.412,
    corners: 15,
    drs_zones: 3,
    direction: "anti-clockwise",
    laps_2024: 57,
    path: "M 200 350 Q 260 250 380 250 L 600 250 Q 720 250 720 320 L 720 380 Q 720 440 650 440 L 500 440 Q 440 440 420 400 L 400 360 Q 380 320 320 320 L 280 320 Q 240 320 230 360 Z",
    sectors: [
      { id: 1, from: 0, to: 0.36, label: "S1" },
      { id: 2, from: 0.36, to: 0.66, label: "S2" },
      { id: 3, from: 0.66, to: 1, label: "S3" },
    ],
    drs: [
      { from: [200, 350], to: [380, 250], label: "DRS 1" },
      { from: [600, 250], to: [720, 320], label: "DRS 2" },
      { from: [720, 380], to: [500, 440], label: "DRS 3" },
    ],
    pit_lane: { at: [200, 360], label: "Pit entry/exit" },
    overtake_spots: [
      { x: 220, y: 320, label: "T1 — heavy braking" },
      { x: 720, y: 350, label: "T11 — DRS into braking" },
      { x: 500, y: 440, label: "T14 — back straight" },
    ],
    notes: "Tyre management critical. Three long straights make DRS overtakes possible.",
  },
  monaco: {
    name: "Circuit de Monaco",
    length_km: 3.337,
    corners: 19,
    drs_zones: 1,
    direction: "clockwise",
    laps_2024: 78,
    // Tight street circuit — narrow zig-zag through Casino, Mirabeau, Loews, Portier
    path: "M 200 400 L 320 360 L 420 360 Q 460 360 470 320 L 480 220 Q 480 200 500 195 L 600 180 L 700 195 Q 720 200 720 235 L 720 280 Q 720 310 690 320 L 660 330 Q 640 340 640 365 L 640 400 Q 640 440 600 440 L 280 440 Q 200 440 200 400 Z",
    sectors: [
      { id: 1, from: 0, to: 0.32, label: "S1" },
      { id: 2, from: 0.32, to: 0.68, label: "S2" },
      { id: 3, from: 0.68, to: 1, label: "S3" },
    ],
    drs: [{ from: [200, 400], to: [320, 360], label: "DRS 1" }],
    pit_lane: { at: [240, 410], label: "Pit lane" },
    overtake_spots: [
      { x: 200, y: 400, label: "T1 (Sainte Devote) — only real chance" },
      { x: 480, y: 220, label: "Nouvelle Chicane — dive bomb" },
    ],
    notes: "Overtaking nearly impossible. Qualifying decides the race.",
  },
  silverstone: {
    name: "Silverstone Circuit",
    length_km: 5.891,
    corners: 18,
    drs_zones: 2,
    direction: "clockwise",
    laps_2024: 52,
    path: "M 180 380 L 350 380 Q 400 380 420 340 L 450 280 Q 470 240 530 240 L 660 240 Q 720 240 740 290 L 770 360 Q 780 400 740 420 L 600 440 Q 540 450 510 410 L 470 360 Q 440 320 380 320 L 280 320 Q 220 320 200 360 Z",
    sectors: [
      { id: 1, from: 0, to: 0.34, label: "S1 — high-speed flow" },
      { id: 2, from: 0.34, to: 0.66, label: "S2 — Maggotts–Becketts" },
      { id: 3, from: 0.66, to: 1, label: "S3 — Stowe complex" },
    ],
    drs: [
      { from: [180, 380], to: [350, 380], label: "DRS 1 (Wellington)" },
      { from: [770, 360], to: [600, 440], label: "DRS 2 (Hangar)" },
    ],
    pit_lane: { at: [200, 390], label: "Pit lane" },
    overtake_spots: [
      { x: 350, y: 380, label: "Brooklands — late on the brakes" },
      { x: 600, y: 440, label: "Stowe — main overtake" },
      { x: 180, y: 380, label: "T1 (Abbey) — opportunistic" },
    ],
    notes: "Rewards a well-rounded aero package. Maggotts-Becketts is a true high-speed sector.",
  },
  monza: {
    name: "Autodromo Nazionale Monza",
    length_km: 5.793,
    corners: 11,
    drs_zones: 2,
    direction: "clockwise",
    laps_2024: 53,
    // Long straights + low-speed chicanes
    path: "M 200 420 L 720 420 Q 760 420 770 380 L 770 340 Q 770 300 730 300 L 590 300 L 580 270 L 540 280 L 530 240 L 480 250 L 470 220 L 420 230 Q 380 240 380 280 L 380 320 Q 380 360 340 360 L 240 360 Q 200 360 200 400 Z",
    sectors: [
      { id: 1, from: 0, to: 0.33, label: "S1 — Variante del Rettifilo" },
      { id: 2, from: 0.33, to: 0.66, label: "S2 — Lesmo + Ascari" },
      { id: 3, from: 0.66, to: 1, label: "S3 — Parabolica" },
    ],
    drs: [
      { from: [200, 420], to: [720, 420], label: "DRS 1 (start/finish)" },
      { from: [380, 320], to: [240, 360], label: "DRS 2 (back straight)" },
    ],
    pit_lane: { at: [220, 430], label: "Pit lane" },
    overtake_spots: [
      { x: 720, y: 420, label: "T1 Variante — main braking zone" },
      { x: 380, y: 360, label: "Ascari chicane" },
      { x: 240, y: 360, label: "Parabolica exit (DRS-assisted)" },
    ],
    notes: "Power circuit. Top speed and DRS-train tactics dominate.",
  },
  spa: {
    name: "Circuit de Spa-Francorchamps",
    length_km: 7.004,
    corners: 19,
    drs_zones: 2,
    direction: "clockwise",
    laps_2024: 44,
    path: "M 200 420 Q 240 420 270 400 L 320 370 L 380 380 L 420 340 Q 460 300 510 300 L 600 300 Q 660 300 690 340 L 740 400 Q 760 430 720 450 L 600 470 L 480 460 L 380 470 Q 320 480 280 460 L 240 440 Q 200 430 200 420 Z",
    sectors: [
      { id: 1, from: 0, to: 0.28, label: "S1 — Eau Rouge / Raidillon" },
      { id: 2, from: 0.28, to: 0.7, label: "S2 — Kemmel + Pouhon" },
      { id: 3, from: 0.7, to: 1, label: "S3 — Stavelot + bus stop" },
    ],
    drs: [
      { from: [320, 370], to: [510, 300], label: "DRS 1 (Kemmel straight)" },
      { from: [200, 420], to: [320, 370], label: "DRS 2 (start/finish)" },
    ],
    pit_lane: { at: [220, 430], label: "Pit lane" },
    overtake_spots: [
      { x: 510, y: 300, label: "Les Combes — into the right-left" },
      { x: 200, y: 420, label: "Bus Stop chicane" },
    ],
    notes: "All-round circuit, often wet. Eau Rouge–Raidillon flat-out is iconic.",
  },
  suzuka: {
    name: "Suzuka International",
    length_km: 5.807,
    corners: 18,
    drs_zones: 1,
    direction: "clockwise",
    laps_2024: 53,
    path: "M 200 420 L 320 420 Q 360 420 370 390 L 380 320 Q 380 280 420 270 L 470 270 Q 510 270 525 305 L 550 360 Q 565 390 600 380 L 660 360 Q 720 340 720 280 L 720 200 Q 720 160 670 160 L 540 160 Q 480 160 470 200 L 460 240 Q 450 280 410 280 L 280 280 Q 220 280 220 340 L 220 380 Q 220 420 200 420 Z",
    sectors: [
      { id: 1, from: 0, to: 0.32, label: "S1 — Esses + Dunlop" },
      { id: 2, from: 0.32, to: 0.66, label: "S2 — Degner + Hairpin" },
      { id: 3, from: 0.66, to: 1, label: "S3 — Spoon + 130R" },
    ],
    drs: [{ from: [200, 420], to: [320, 420], label: "DRS 1 (start/finish)" }],
    pit_lane: { at: [220, 430], label: "Pit lane" },
    overtake_spots: [
      { x: 320, y: 420, label: "T1 — heavy braking" },
      { x: 550, y: 360, label: "Hairpin (T11)" },
      { x: 660, y: 360, label: "Spoon exit (DRS-assisted)" },
    ],
    notes: "Figure-8 layout. High-speed precision rewards the best chassis.",
  },
  abu_dhabi: {
    name: "Yas Marina Circuit",
    length_km: 5.281,
    corners: 16,
    drs_zones: 2,
    direction: "anti-clockwise",
    laps_2024: 58,
    path: "M 200 380 L 380 380 Q 420 380 430 350 L 440 280 Q 440 240 480 240 L 600 240 Q 650 240 660 280 L 670 340 Q 680 380 640 400 L 480 440 Q 420 450 390 420 L 360 380 Q 330 340 280 340 L 220 340 Q 200 340 200 360 Z",
    sectors: [
      { id: 1, from: 0, to: 0.32, label: "S1" },
      { id: 2, from: 0.32, to: 0.66, label: "S2" },
      { id: 3, from: 0.66, to: 1, label: "S3" },
    ],
    drs: [
      { from: [200, 380], to: [380, 380], label: "DRS 1" },
      { from: [440, 280], to: [600, 240], label: "DRS 2" },
    ],
    pit_lane: { at: [240, 390], label: "Pit lane" },
    overtake_spots: [
      { x: 380, y: 380, label: "T6 — chicane" },
      { x: 600, y: 240, label: "T9 — long left" },
    ],
    notes: "Season finale. Reconfigured 2021 layout improved overtaking.",
  },
};

export const CIRCUIT_BY_ROUND = {
  // 2024 calendar mapping; falls back to monza if unknown.
  1: "bahrain", 2: "monza", 3: "monza", 4: "suzuka", 5: "monza",
  6: "monza", 7: "monza", 8: "monaco", 9: "monza", 10: "monza",
  11: "monza", 12: "silverstone", 13: "monza", 14: "spa", 15: "monza",
  16: "monza", 17: "monza", 18: "monza", 19: "monza", 20: "monza",
  21: "monza", 22: "monza", 23: "monza", 24: "abu_dhabi",
};
