import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TRACKS } from "./tracks_data.js";

/**
 * Three.js 3D track visualisation with an actual F1 car model, a proper
 * road surface (vertex-coloured per sector), real DRS road segments,
 * corner markers, and start/finish line. Replaces the previous tube +
 * sphere placeholder.
 *
 *   - Track ribbon = a quad strip wide enough to look like a road
 *     surface, with kerbs along both edges
 *   - Sectors = per-vertex colour blend along the ribbon
 *   - DRS zones = bright green road sections + floating "DRS" badge
 *   - Overtake spots = red braking-zone bars across the road
 *   - Start/finish = white/black checker bar at lap start
 *   - Driver = proper low-poly F1 car (body / nose / wings / wheels /
 *     halo) painted in team livery, traveling around the curve at a
 *     speed that varies per sector based on driver affinity.
 */

const SECTOR_DIMENSIONS = {
  1: ["straight_line_speed", "high_speed_cornering"],
  2: ["low_speed_cornering", "tyre_management"],
  3: ["qualifying_pace", "race_pace_conversion"],
};

const ROAD_WIDTH = 14;
const KERB_WIDTH = 1.5;
const SAMPLES = 1200;

export function render3DTrack({
  containerId,
  circuitKey,
  driverColor = "#e8002d",
  signals = {},
}) {
  const container = document.getElementById(containerId);
  if (!container) return () => {};
  const track = TRACKS[circuitKey] || TRACKS.monza;
  container.innerHTML = "";

  const width = container.clientWidth || 720;
  const height = 420;

  // ---------- scene + camera + renderer ----------
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#06060c");
  scene.fog = new THREE.FogExp2("#06060c", 0.0014);

  const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 6000);
  camera.position.set(0, 460, 520);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width, height);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.5;
  controls.minPolarAngle = Math.PI / 8;
  controls.maxPolarAngle = Math.PI / 2.05;

  // ---------- lighting ----------
  scene.add(new THREE.AmbientLight(0x404060, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(400, 800, 200);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xff5577, 0.5);
  fill.position.set(-500, 300, -300);
  scene.add(fill);
  const ground = new THREE.HemisphereLight(0x222233, 0x000000, 0.6);
  scene.add(ground);

  // ---------- ground plane ----------
  const groundMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(3000, 3000),
    new THREE.MeshStandardMaterial({
      color: 0x0a0a12,
      roughness: 1,
      metalness: 0,
    }),
  );
  groundMesh.rotation.x = -Math.PI / 2;
  groundMesh.position.y = -2;
  scene.add(groundMesh);

  // ---------- sample path → 2D points centred at origin ----------
  const samples2D = samplePath(track.path, SAMPLES);
  const cx = samples2D.reduce((a, p) => a + p.x, 0) / samples2D.length;
  const cy = samples2D.reduce((a, p) => a + p.y, 0) / samples2D.length;
  const samples = samples2D.map((p) => ({ x: p.x - cx, y: p.y - cy }));

  // Compute tangents (for road normals) and arc length progress t.
  const tangents = samples.map((p, i) => {
    const n = samples[(i + 1) % samples.length];
    const dx = n.x - p.x;
    const dy = n.y - p.y;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    return { x: dx / len, y: dy / len };
  });

  // ---------- ROAD SURFACE (quad strip) ----------
  // For each path point, place two vertices perpendicular to the tangent.
  const positions = [];
  const colors = [];
  const indices = [];
  const sectorAtT = (t) => track.sectors.find((s) => t >= s.from && t < s.to) || track.sectors[track.sectors.length - 1];
  const sectorRGB = {
    1: new THREE.Color(0xe8002d),
    2: new THREE.Color(0xf5a524),
    3: new THREE.Color(0x3782e5),
  };
  const drsAt = (t) => isInDrs(t, samples, track.drs, cx, cy);

  for (let i = 0; i < samples.length; i++) {
    const p = samples[i];
    const tg = tangents[i];
    // Perpendicular (rotated 90°): (-y, x)
    const nx = -tg.y;
    const nz = tg.x;
    const t = i / samples.length;

    // Left and right edge of the road.
    const lx = p.x + nx * (ROAD_WIDTH / 2);
    const lz = p.y + nz * (ROAD_WIDTH / 2);
    const rx = p.x - nx * (ROAD_WIDTH / 2);
    const rz = p.y - nz * (ROAD_WIDTH / 2);

    positions.push(lx, 0, lz);
    positions.push(rx, 0, rz);

    // Vertex colour: dark asphalt with a hint of sector tint when in DRS.
    const inDrs = drsAt(t);
    const sector = sectorAtT(t);
    const tint = sectorRGB[sector.id];

    let r, g, b;
    if (inDrs) {
      // bright green DRS road
      r = 0.13; g = 0.78; b = 0.36;
    } else {
      // dark asphalt with subtle sector wash
      r = 0.08 + tint.r * 0.08;
      g = 0.08 + tint.g * 0.08;
      b = 0.10 + tint.b * 0.08;
    }
    colors.push(r, g, b);
    colors.push(r, g, b);
  }

  // Triangles connecting (l_i, r_i) → (l_i+1, r_i+1).
  for (let i = 0; i < samples.length; i++) {
    const i0 = i * 2;
    const i1 = i * 2 + 1;
    const j0 = ((i + 1) % samples.length) * 2;
    const j1 = ((i + 1) % samples.length) * 2 + 1;
    indices.push(i0, j0, j1, i0, j1, i1);
  }

  const roadGeom = new THREE.BufferGeometry();
  roadGeom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  roadGeom.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  roadGeom.setIndex(indices);
  roadGeom.computeVertexNormals();
  const roadMat = new THREE.MeshStandardMaterial({
    vertexColors: true,
    metalness: 0.1,
    roughness: 0.75,
  });
  scene.add(new THREE.Mesh(roadGeom, roadMat));

  // ---------- KERBS (red/white striped strip at both edges) ----------
  for (const side of [1, -1]) {
    const kerbPositions = [];
    const kerbColors = [];
    const kerbIndices = [];
    for (let i = 0; i < samples.length; i++) {
      const p = samples[i];
      const tg = tangents[i];
      const nx = -tg.y;
      const nz = tg.x;
      const inner = ROAD_WIDTH / 2;
      const outer = inner + KERB_WIDTH;
      const px1 = p.x + nx * inner * side;
      const pz1 = p.y + nz * inner * side;
      const px2 = p.x + nx * outer * side;
      const pz2 = p.y + nz * outer * side;
      kerbPositions.push(px1, 0.1, pz1);
      kerbPositions.push(px2, 0.1, pz2);
      // Alternate red/white every few samples.
      const stripe = Math.floor(i / 6) % 2 === 0;
      const cr = stripe ? 0.92 : 0.95;
      const cg = stripe ? 0.0 : 0.95;
      const cb = stripe ? 0.16 : 0.95;
      kerbColors.push(cr, cg, cb);
      kerbColors.push(cr, cg, cb);
    }
    for (let i = 0; i < samples.length; i++) {
      const i0 = i * 2, i1 = i * 2 + 1;
      const j0 = ((i + 1) % samples.length) * 2;
      const j1 = ((i + 1) % samples.length) * 2 + 1;
      kerbIndices.push(i0, j0, j1, i0, j1, i1);
    }
    const kg = new THREE.BufferGeometry();
    kg.setAttribute("position", new THREE.Float32BufferAttribute(kerbPositions, 3));
    kg.setAttribute("color", new THREE.Float32BufferAttribute(kerbColors, 3));
    kg.setIndex(kerbIndices);
    kg.computeVertexNormals();
    scene.add(new THREE.Mesh(kg, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.65 })));
  }

  // ---------- SECTOR MARKERS (vertical glowing bars at sector boundaries) ----------
  for (const s of track.sectors) {
    const idx = Math.floor(s.from * samples.length);
    const p = samples[idx];
    const tg = tangents[idx];
    const nx = -tg.y;
    const nz = tg.x;
    const color = sectorRGB[s.id];
    for (let side of [1, -1]) {
      const x = p.x + nx * (ROAD_WIDTH / 2 + 4) * side;
      const z = p.y + nz * (ROAD_WIDTH / 2 + 4) * side;
      const bar = new THREE.Mesh(
        new THREE.BoxGeometry(2, 20, 2),
        new THREE.MeshStandardMaterial({
          color,
          emissive: color,
          emissiveIntensity: 0.6,
        }),
      );
      bar.position.set(x, 10, z);
      scene.add(bar);
    }
  }

  // ---------- DRS BADGES (floating green "DRS" plate above each zone) ----------
  for (const drs of track.drs || []) {
    const midX = (drs.from[0] + drs.to[0]) / 2 - cx;
    const midY = (drs.from[1] + drs.to[1]) / 2 - cy;
    const plate = new THREE.Mesh(
      new THREE.BoxGeometry(20, 6, 3),
      new THREE.MeshStandardMaterial({
        color: 0x22c55e,
        emissive: 0x22c55e,
        emissiveIntensity: 0.9,
      }),
    );
    plate.position.set(midX, 28, midY);
    scene.add(plate);
  }

  // ---------- OVERTAKE BRAKING BARS ----------
  for (const ot of track.overtake_spots || []) {
    const x = ot.x - cx;
    const z = ot.y - cy;
    // Find nearest path index to orient the bar perpendicular to track.
    let nearest = 0;
    let bestDist = Infinity;
    for (let i = 0; i < samples.length; i++) {
      const dx = samples[i].x - x;
      const dz = samples[i].y - z;
      const d = dx * dx + dz * dz;
      if (d < bestDist) { bestDist = d; nearest = i; }
    }
    const tg = tangents[nearest];
    const barGeom = new THREE.BoxGeometry(ROAD_WIDTH + 4, 0.8, 1.6);
    const bar = new THREE.Mesh(barGeom, new THREE.MeshStandardMaterial({
      color: 0xe8002d, emissive: 0xe8002d, emissiveIntensity: 0.5,
    }));
    bar.position.set(x, 0.6, z);
    bar.rotation.y = Math.atan2(tg.x, tg.y);
    scene.add(bar);
  }

  // ---------- START/FINISH CHECKER BAR ----------
  const startIdx = 0;
  {
    const p = samples[startIdx];
    const tg = tangents[startIdx];
    const nx = -tg.y;
    const nz = tg.x;
    for (let side = -1; side <= 1; side += 2) {
      for (let k = 0; k < 6; k++) {
        const px = p.x + nx * (k - 2.5) * 2 * side;
        const pz = p.y + nz * (k - 2.5) * 2 * side;
        const tile = new THREE.Mesh(
          new THREE.BoxGeometry(2, 0.3, 1.4),
          new THREE.MeshStandardMaterial({
            color: k % 2 === 0 ? 0xffffff : 0x111111,
          }),
        );
        tile.position.set(px, 0.2, pz);
        tile.rotation.y = Math.atan2(tg.x, tg.y);
        scene.add(tile);
      }
    }
  }

  // ---------- F1 CAR ----------
  const car = buildF1Car(driverColor);
  scene.add(car);

  // Curve for the car to follow (slightly elevated above road).
  const curvePts = samples.map((p) => new THREE.Vector3(p.x, 1.5, p.y));
  const curve = new THREE.CatmullRomCurve3(curvePts, true);

  // ---------- ANIMATE ----------
  let t = 0;
  let raf;
  const sectorAffinity = sectorVelocityFactor.bind(null, signals);
  function tick() {
    raf = requestAnimationFrame(tick);

    const sector = sectorAt(t, track.sectors);
    const vel = 0.0005 + 0.0011 * sectorAffinity(sector);
    t = (t + vel) % 1;

    // Position + orient the car.
    const pos = curve.getPointAt(t);
    car.position.copy(pos);
    const lookAhead = curve.getPointAt((t + 0.002) % 1);
    car.lookAt(lookAhead.x, pos.y, lookAhead.z);

    controls.update();
    renderer.render(scene, camera);
  }
  tick();

  // ---------- resize ----------
  function handleResize() {
    const w = container.clientWidth || width;
    renderer.setSize(w, height);
    camera.aspect = w / height;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", handleResize);

  return () => {
    cancelAnimationFrame(raf);
    window.removeEventListener("resize", handleResize);
    controls.dispose();
    renderer.dispose();
    container.innerHTML = "";
  };
}

// =============================================================
//                    F1 car model
// =============================================================

function buildF1Car(liveryHex) {
  const livery = new THREE.Color(liveryHex);
  const dark = new THREE.Color("#111118");
  const tyre = new THREE.Color("#0a0a0c");
  const wing = new THREE.Color("#000000");

  const car = new THREE.Group();

  const bodyMat = new THREE.MeshStandardMaterial({
    color: livery, metalness: 0.45, roughness: 0.32,
    emissive: livery, emissiveIntensity: 0.15,
  });
  const darkMat = new THREE.MeshStandardMaterial({
    color: dark, metalness: 0.3, roughness: 0.5,
  });
  const tyreMat = new THREE.MeshStandardMaterial({
    color: tyre, metalness: 0.0, roughness: 0.9,
  });
  const wingMat = new THREE.MeshStandardMaterial({
    color: wing, metalness: 0.4, roughness: 0.4,
  });

  // Main floor / chassis — long thin box.
  const floor = new THREE.Mesh(new THREE.BoxGeometry(4.6, 0.7, 12), bodyMat);
  floor.position.y = 0.9;
  car.add(floor);

  // Nose — wedge pointing forward (in +Z by convention here).
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.9, 4, 4), bodyMat);
  nose.rotation.x = Math.PI / 2;
  nose.rotation.z = Math.PI / 4;
  nose.position.set(0, 1.0, 7.4);
  car.add(nose);

  // Engine cover / shark fin behind the cockpit.
  const sharkFin = new THREE.Mesh(new THREE.BoxGeometry(0.4, 1.6, 4.5), bodyMat);
  sharkFin.position.set(0, 2.1, -2.5);
  car.add(sharkFin);

  // Cockpit / driver hump.
  const cockpit = new THREE.Mesh(new THREE.BoxGeometry(2.6, 1.0, 3.5), bodyMat);
  cockpit.position.set(0, 1.8, 1.0);
  car.add(cockpit);

  // Halo (a torus segment in front of driver).
  const halo = new THREE.Mesh(
    new THREE.TorusGeometry(1.6, 0.18, 8, 16, Math.PI),
    darkMat,
  );
  halo.position.set(0, 2.3, 1.6);
  halo.rotation.x = Math.PI / 2;
  car.add(halo);

  // Front wing — wide, low, with end-plates.
  const fwMain = new THREE.Mesh(new THREE.BoxGeometry(6.0, 0.3, 1.6), wingMat);
  fwMain.position.set(0, 0.5, 8.4);
  car.add(fwMain);
  for (const side of [1, -1]) {
    const ep = new THREE.Mesh(new THREE.BoxGeometry(0.4, 1.2, 1.8), wingMat);
    ep.position.set(side * 3.0, 0.9, 8.4);
    car.add(ep);
  }

  // Rear wing — tall vertical element.
  const rwMain = new THREE.Mesh(new THREE.BoxGeometry(5.2, 1.6, 0.3), wingMat);
  rwMain.position.set(0, 2.4, -5.8);
  car.add(rwMain);
  for (const side of [1, -1]) {
    const ep = new THREE.Mesh(new THREE.BoxGeometry(0.4, 2.4, 1.4), wingMat);
    ep.position.set(side * 2.6, 1.8, -5.5);
    car.add(ep);
  }
  // DRS flap.
  const drsFlap = new THREE.Mesh(new THREE.BoxGeometry(4.6, 0.5, 0.2), wingMat);
  drsFlap.position.set(0, 2.95, -5.65);
  car.add(drsFlap);

  // Wheels — 4 thick cylinders, axis along X.
  const wheelGeom = new THREE.CylinderGeometry(1.3, 1.3, 1.6, 24);
  const wheelOffsetX = 3.0;
  const wheelOffsetZ = 4.6;
  const wheelY = 1.0;
  for (const x of [wheelOffsetX, -wheelOffsetX]) {
    for (const z of [wheelOffsetZ, -wheelOffsetZ]) {
      const wheel = new THREE.Mesh(wheelGeom, tyreMat);
      wheel.position.set(x, wheelY, z);
      wheel.rotation.z = Math.PI / 2;
      // simple rim look
      const rim = new THREE.Mesh(
        new THREE.CylinderGeometry(0.55, 0.55, 1.62, 16),
        darkMat,
      );
      rim.rotation.z = Math.PI / 2;
      wheel.add(rim);
      car.add(wheel);
    }
  }

  // Side pods (the bulges next to the cockpit).
  for (const side of [1, -1]) {
    const sp = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.0, 4.5), bodyMat);
    sp.position.set(side * 1.8, 1.3, -0.5);
    car.add(sp);
  }

  // Rear diffuser / under-floor.
  const diffuser = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.4, 1.6), darkMat);
  diffuser.position.set(0, 0.4, -5.6);
  car.add(diffuser);

  // The whole car was modelled with the nose pointing +Z. Rotate so it
  // points along the path tangent: our lookAt drives orientation.
  // Scale down to read at our world units.
  car.scale.setScalar(0.55);
  return car;
}

// =============================================================
//                    Helpers
// =============================================================

function samplePath(d, count) {
  const svgNS = "http://www.w3.org/2000/svg";
  const tmp = document.createElementNS(svgNS, "svg");
  tmp.setAttribute("viewBox", "0 0 1000 600");
  tmp.style.position = "absolute";
  tmp.style.left = "-9999px";
  document.body.appendChild(tmp);
  const path = document.createElementNS(svgNS, "path");
  path.setAttribute("d", d);
  tmp.appendChild(path);
  const len = path.getTotalLength();
  const pts = [];
  for (let i = 0; i < count; i++) {
    const p = path.getPointAtLength((i / count) * len);
    pts.push({ x: p.x, y: p.y });
  }
  document.body.removeChild(tmp);
  return pts;
}

function isInDrs(t, samples, drsList, cx, cy) {
  if (!drsList?.length) return false;
  const idx = Math.floor(t * samples.length);
  const px = samples[idx].x + cx;
  const py = samples[idx].y + cy;
  for (const z of drsList) {
    // Check if the point projects onto the DRS segment within 30 units.
    const ax = z.from[0], ay = z.from[1];
    const bx = z.to[0], by = z.to[1];
    const abx = bx - ax, aby = by - ay;
    const apx = px - ax, apy = py - ay;
    const lenSq = abx * abx + aby * aby;
    let t01 = (apx * abx + apy * aby) / lenSq;
    if (t01 < 0 || t01 > 1) continue;
    const ix = ax + abx * t01;
    const iy = ay + aby * t01;
    const dx = px - ix, dy = py - iy;
    if (dx * dx + dy * dy < 30 * 30) return true;
  }
  return false;
}

function sectorAt(t, sectors) {
  for (const s of sectors) {
    if (t >= s.from && t < s.to) return s;
  }
  return sectors[sectors.length - 1];
}

function sectorVelocityFactor(signals, sector) {
  if (!sector) return 0.5;
  const keys = SECTOR_DIMENSIONS[sector.id] || [];
  const scores = keys.map((k) => signals?.[k]).filter((v) => v != null);
  if (!scores.length) {
    const fb = signals?.combined ?? signals?.qualifying ?? 50;
    return Math.max(0.15, Math.min(1, fb / 100));
  }
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
  return Math.max(0.15, Math.min(1, avg / 100));
}
