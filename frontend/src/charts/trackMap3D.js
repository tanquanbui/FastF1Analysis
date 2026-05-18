import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TRACKS } from "./tracks_data.js";

/**
 * Three.js 3D visualisation of how a driver will tackle a given circuit.
 *
 *  - Track surface = a flat ribbon following the 2D SVG path, with
 *    procedural elevation per sector.
 *  - Sector colours match the dashboard (S1 red, S2 orange, S3 blue).
 *  - DRS zones rendered as floating green markers above the track.
 *  - A glowing "driver dot" travels around the circuit, its colour
 *    pulled from the team livery. Its speed varies per sector based on
 *    the driver's fingerprint score for that sector's dominant dim:
 *      S1 / S2 / S3 each rewarded by 1-3 fingerprint dimensions; we
 *      take the driver's best fit value, normalise, and scale the
 *      car's per-sector velocity.
 *
 * Returns a teardown function the caller invokes when the modal closes.
 */

const SECTOR_DIMENSIONS = {
  1: ["straight_line_speed", "high_speed_cornering"],
  2: ["low_speed_cornering", "tyre_management"],
  3: ["qualifying_pace", "race_pace_conversion"],
};

export function render3DTrack({
  containerId,
  circuitKey,
  driverColor = "#e8002d",
  driverCode = "?",
  signals = {},   // optional fingerprint-style per-sector affinities
}) {
  const container = document.getElementById(containerId);
  if (!container) return () => {};

  const track = TRACKS[circuitKey] || TRACKS.monza;
  container.innerHTML = "";

  const width = container.clientWidth || 700;
  const height = 360;

  // 1. Scene + camera + renderer.
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#0a0a0f");
  scene.fog = new THREE.FogExp2("#0a0a0f", 0.0018);

  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 5000);
  camera.position.set(0, 380, 480);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width, height);
  renderer.shadowMap.enabled = false;
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.6;
  controls.minPolarAngle = Math.PI / 6;
  controls.maxPolarAngle = Math.PI / 2.1;

  // 2. Lighting.
  scene.add(new THREE.AmbientLight(0x404060, 1.4));
  const key = new THREE.DirectionalLight(0xffffff, 1.0);
  key.position.set(200, 600, 200);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xff0040, 0.6);
  rim.position.set(-400, 200, -200);
  scene.add(rim);

  // 3. Sample the 2D SVG path → 3D points.
  const samples = samplePath(track.path, 400);
  const center = samples.reduce(
    (acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }),
    { x: 0, y: 0 },
  );
  center.x /= samples.length;
  center.y /= samples.length;

  // Map XY → world coords centred at origin. Add a touch of Z elevation
  // proportional to per-sector affinity so high-fit sectors physically
  // rise out of the floor.
  const points3D = samples.map((p, i) => {
    const t = i / samples.length;
    const sector = sectorAt(t, track.sectors);
    const elev = sectorElevation(sector, signals);
    return new THREE.Vector3(p.x - center.x, elev, p.y - center.y);
  });

  // 4. Track ribbon — extrude a flat band along the spline.
  const curve = new THREE.CatmullRomCurve3(points3D, true);

  // Base track surface: thick dark ribbon.
  const tubeGeom = new THREE.TubeGeometry(curve, 600, 8, 8, true);
  const tubeMat = new THREE.MeshStandardMaterial({
    color: 0x161620,
    metalness: 0.2,
    roughness: 0.7,
  });
  const tubeMesh = new THREE.Mesh(tubeGeom, tubeMat);
  scene.add(tubeMesh);

  // 5. Sector overlays — three coloured tubes on top of the base.
  const sectorColors = { 1: 0xe8002d, 2: 0xf5a524, 3: 0x3782e5 };
  for (const s of track.sectors) {
    const pts = points3D
      .map((p, i) => ({ p, t: i / points3D.length }))
      .filter(({ t }) => t >= s.from && t <= s.to)
      .map(({ p }) => p);
    if (pts.length < 2) continue;
    const segCurve = new THREE.CatmullRomCurve3(pts, false);
    const segGeom = new THREE.TubeGeometry(segCurve, pts.length * 2, 9.5, 8, false);
    const segMat = new THREE.MeshStandardMaterial({
      color: sectorColors[s.id] || 0xffffff,
      emissive: sectorColors[s.id] || 0xffffff,
      emissiveIntensity: 0.4,
      metalness: 0.0,
      roughness: 0.55,
    });
    scene.add(new THREE.Mesh(segGeom, segMat));
  }

  // 6. DRS markers — small green pyramids hovering above each DRS zone.
  for (const drs of track.drs || []) {
    const midX = (drs.from[0] + drs.to[0]) / 2 - center.x;
    const midY = (drs.from[1] + drs.to[1]) / 2 - center.y;
    const geom = new THREE.ConeGeometry(8, 18, 4);
    const mat = new THREE.MeshStandardMaterial({
      color: 0x22c55e,
      emissive: 0x22c55e,
      emissiveIntensity: 0.6,
    });
    const cone = new THREE.Mesh(geom, mat);
    cone.position.set(midX, 28, midY);
    cone.rotation.x = Math.PI;
    scene.add(cone);
  }

  // 7. Overtake spots — pulsing red rings.
  for (const ot of track.overtake_spots || []) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(12, 2, 8, 32),
      new THREE.MeshStandardMaterial({
        color: 0xe8002d,
        emissive: 0xe8002d,
        emissiveIntensity: 0.5,
      }),
    );
    ring.position.set(ot.x - center.x, 14, ot.y - center.y);
    ring.rotation.x = Math.PI / 2;
    ring.userData.pulse = Math.random() * Math.PI * 2;
    scene.add(ring);
  }

  // 8. Driver dot — glowing sphere following the curve, coloured by livery.
  const driver = new THREE.Mesh(
    new THREE.SphereGeometry(7, 16, 16),
    new THREE.MeshStandardMaterial({
      color: new THREE.Color(driverColor),
      emissive: new THREE.Color(driverColor),
      emissiveIntensity: 1.0,
    }),
  );
  scene.add(driver);

  // Driver trail — line behind the dot.
  const trailLen = 40;
  const trailPositions = new Float32Array(trailLen * 3);
  const trailGeom = new THREE.BufferGeometry();
  trailGeom.setAttribute("position", new THREE.BufferAttribute(trailPositions, 3));
  const trailMat = new THREE.LineBasicMaterial({
    color: new THREE.Color(driverColor),
    transparent: true,
    opacity: 0.7,
  });
  const trail = new THREE.Line(trailGeom, trailMat);
  scene.add(trail);

  // 9. Animate.
  let t = 0;
  let raf;
  function tick() {
    raf = requestAnimationFrame(tick);

    // Per-sector velocity scaled by driver affinity.
    const sector = sectorAt(t, track.sectors);
    const vel = 0.0008 + 0.0009 * driverSpeedFactor(sector, signals);
    t = (t + vel) % 1;

    const pos = curve.getPointAt(t);
    driver.position.copy(pos);
    driver.position.y += 14;

    // Shift trail positions back, write head.
    for (let i = trailLen - 1; i > 0; i--) {
      trailPositions[i * 3 + 0] = trailPositions[(i - 1) * 3 + 0];
      trailPositions[i * 3 + 1] = trailPositions[(i - 1) * 3 + 1];
      trailPositions[i * 3 + 2] = trailPositions[(i - 1) * 3 + 2];
    }
    trailPositions[0] = driver.position.x;
    trailPositions[1] = driver.position.y - 4;
    trailPositions[2] = driver.position.z;
    trailGeom.attributes.position.needsUpdate = true;

    scene.traverse((obj) => {
      if (obj.userData?.pulse != null) {
        obj.userData.pulse += 0.05;
        obj.scale.setScalar(1 + 0.15 * Math.sin(obj.userData.pulse));
      }
    });

    controls.update();
    renderer.render(scene, camera);
  }
  tick();

  // 10. Resize handling.
  function handleResize() {
    const w = container.clientWidth || width;
    renderer.setSize(w, height);
    camera.aspect = w / height;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", handleResize);

  // Teardown function.
  return () => {
    cancelAnimationFrame(raf);
    window.removeEventListener("resize", handleResize);
    controls.dispose();
    renderer.dispose();
    container.innerHTML = "";
  };
}

// ---------- helpers ----------

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

function sectorAt(t, sectors) {
  for (const s of sectors) {
    if (t >= s.from && t < s.to) return s;
  }
  return sectors[sectors.length - 1];
}

function sectorElevation(sector, signals) {
  if (!sector) return 0;
  const dims = SECTOR_DIMENSIONS[sector.id] || [];
  const scores = dims
    .map((d) => signals?.[d])
    .filter((v) => v != null);
  if (!scores.length) return 4;
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
  // Map 0-100 → 0-22 height.
  return 4 + (avg / 100) * 18;
}

function driverSpeedFactor(sector, signals) {
  if (!sector) return 0.5;
  // Cross-reference signal scores against sector dimensions.
  const keys = SECTOR_DIMENSIONS[sector.id] || [];
  const scores = keys.map((k) => signals?.[k]).filter((v) => v != null);
  if (!scores.length) {
    // Fall back to combined / qualifying scores if no per-dim data.
    const fallback = signals?.combined ?? signals?.qualifying ?? 50;
    return Math.max(0.15, Math.min(1, fallback / 100));
  }
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
  return Math.max(0.15, Math.min(1, avg / 100));
}
