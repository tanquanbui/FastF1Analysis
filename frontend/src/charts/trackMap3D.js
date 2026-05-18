import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { TRACKS } from "./tracks_data.js";

/**
 * Cinematic night-race 3D circuit + photoreal-ish F1 car.
 * Heavy on emissive accents, bloom postprocessing, dynamic shadows, and
 * properly composed F1 geometry: 80+ primitive components per car —
 * aerofoils, suspension links, brake discs, mirrors, driver helmet,
 * exhaust plume, etc.
 */

const SECTOR_DIMENSIONS = {
  1: ["straight_line_speed", "high_speed_cornering"],
  2: ["low_speed_cornering", "tyre_management"],
  3: ["qualifying_pace", "race_pace_conversion"],
};

const ROAD_WIDTH = 14;
const KERB_WIDTH = 1.4;
const SAMPLES = 1400;

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
  const height = 480;

  // ---------- renderer + composer ----------
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width, height);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();

  // HDR-ish procedural environment via PMREMGenerator.
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  envScene.background = new THREE.Color("#0c0612");
  const envSun = new THREE.Mesh(
    new THREE.SphereGeometry(40, 32, 32),
    new THREE.MeshBasicMaterial({ color: 0xffaa66 }),
  );
  envSun.position.set(60, 30, 0);
  envScene.add(envSun);
  const envFill = new THREE.Mesh(
    new THREE.SphereGeometry(80, 16, 16),
    new THREE.MeshBasicMaterial({ color: 0xff0055 }),
  );
  envFill.position.set(-90, 20, 30);
  envScene.add(envFill);
  scene.environment = pmrem.fromScene(envScene, 0.02).texture;

  const camera = new THREE.PerspectiveCamera(40, width / height, 0.5, 6000);
  camera.position.set(-380, 400, 520);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(width, height), 0.85, 0.45, 0.12);
  bloom.threshold = 0.02;
  bloom.strength = 0.95;
  bloom.radius = 0.7;
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.4;
  controls.minPolarAngle = Math.PI / 8;
  controls.maxPolarAngle = Math.PI / 2.05;

  // ---------- sky dome ----------
  scene.add(new THREE.Mesh(
    new THREE.SphereGeometry(2500, 32, 16),
    new THREE.ShaderMaterial({
      side: THREE.BackSide,
      uniforms: {
        top:    { value: new THREE.Color("#03030d") },
        mid:    { value: new THREE.Color("#160820") },
        bottom: { value: new THREE.Color("#1d0612") },
      },
      vertexShader: `
        varying vec3 vPos;
        void main() {
          vPos = position;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        uniform vec3 top;
        uniform vec3 mid;
        uniform vec3 bottom;
        varying vec3 vPos;
        void main() {
          float h = clamp(vPos.y / 2500.0 + 0.3, 0.0, 1.0);
          vec3 c = h > 0.5
            ? mix(mid, top, (h - 0.5) * 2.0)
            : mix(bottom, mid, h * 2.0);
          gl_FragColor = vec4(c, 1.0);
        }`,
    }),
  ));

  // ---------- lighting ----------
  scene.add(new THREE.AmbientLight(0x161620, 0.4));

  const moon = new THREE.DirectionalLight(0xc8d0ff, 1.5);
  moon.position.set(400, 900, 300);
  moon.castShadow = true;
  moon.shadow.mapSize.set(2048, 2048);
  moon.shadow.camera.left = -400;
  moon.shadow.camera.right = 400;
  moon.shadow.camera.top = 400;
  moon.shadow.camera.bottom = -400;
  moon.shadow.camera.near = 1;
  moon.shadow.camera.far = 2000;
  moon.shadow.bias = -0.0005;
  scene.add(moon);

  const magenta = new THREE.DirectionalLight(0xff2266, 0.55);
  magenta.position.set(-600, 250, -400);
  scene.add(magenta);

  scene.add(new THREE.HemisphereLight(0x1a1a2c, 0x000000, 0.55));

  // ---------- reflective ground ----------
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(4000, 4000),
    new THREE.MeshStandardMaterial({
      color: 0x040408,
      metalness: 0.7,
      roughness: 0.35,
      envMapIntensity: 0.6,
    }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -2.5;
  ground.receiveShadow = true;
  scene.add(ground);

  // ---------- sample path ----------
  const samples2D = samplePath(track.path, SAMPLES);
  const cx = samples2D.reduce((a, p) => a + p.x, 0) / samples2D.length;
  const cy = samples2D.reduce((a, p) => a + p.y, 0) / samples2D.length;
  const samples = samples2D.map((p) => ({ x: p.x - cx, y: p.y - cy }));
  const tangents = samples.map((p, i) => {
    const n = samples[(i + 1) % samples.length];
    const dx = n.x - p.x;
    const dy = n.y - p.y;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    return { x: dx / len, y: dy / len };
  });

  // ---------- road surface ----------
  const sectorRGB = {
    1: new THREE.Color(0xff1e54),
    2: new THREE.Color(0xff9020),
    3: new THREE.Color(0x35a3ff),
  };
  const roadGeom = new THREE.BufferGeometry();
  const roadPositions = [];
  const roadColors = [];
  const roadIndices = [];
  for (let i = 0; i < samples.length; i++) {
    const p = samples[i];
    const tg = tangents[i];
    const nx = -tg.y, nz = tg.x;
    const t = i / samples.length;
    const sector = sectorAt(t, track.sectors);
    const inDrs = isInDrs(t, samples, track.drs, cx, cy);
    const tint = sectorRGB[sector.id];
    roadPositions.push(
      p.x + nx * (ROAD_WIDTH / 2), 0, p.y + nz * (ROAD_WIDTH / 2),
      p.x - nx * (ROAD_WIDTH / 2), 0, p.y - nz * (ROAD_WIDTH / 2),
    );
    let r, g, b;
    if (inDrs) { r = 0.05; g = 0.95; b = 0.35; }
    else {
      r = 0.04 + tint.r * 0.05;
      g = 0.04 + tint.g * 0.05;
      b = 0.06 + tint.b * 0.06;
    }
    roadColors.push(r, g, b, r, g, b);
  }
  for (let i = 0; i < samples.length; i++) {
    const i0 = i * 2, i1 = i * 2 + 1;
    const j0 = ((i + 1) % samples.length) * 2;
    const j1 = ((i + 1) % samples.length) * 2 + 1;
    roadIndices.push(i0, j0, j1, i0, j1, i1);
  }
  roadGeom.setAttribute("position", new THREE.Float32BufferAttribute(roadPositions, 3));
  roadGeom.setAttribute("color", new THREE.Float32BufferAttribute(roadColors, 3));
  roadGeom.setIndex(roadIndices);
  roadGeom.computeVertexNormals();
  const road = new THREE.Mesh(roadGeom, new THREE.MeshStandardMaterial({
    vertexColors: true, metalness: 0.55, roughness: 0.4, envMapIntensity: 0.5,
  }));
  road.receiveShadow = true;
  scene.add(road);

  // ---------- neon edge ribbons ----------
  for (const side of [1, -1]) {
    const edgePositions = [];
    const edgeColors = [];
    const edgeIndices = [];
    const edgeCol = side === 1 ? new THREE.Color("#22d3ee") : new THREE.Color("#ff007a");
    for (let i = 0; i < samples.length; i++) {
      const p = samples[i];
      const tg = tangents[i];
      const nx = -tg.y, nz = tg.x;
      const inner = ROAD_WIDTH / 2 + 0.3;
      const outer = inner + 0.5;
      edgePositions.push(
        p.x + nx * inner * side, 0.05, p.y + nz * inner * side,
        p.x + nx * outer * side, 0.05, p.y + nz * outer * side,
      );
      edgeColors.push(edgeCol.r, edgeCol.g, edgeCol.b, edgeCol.r, edgeCol.g, edgeCol.b);
    }
    for (let i = 0; i < samples.length; i++) {
      const i0 = i * 2, i1 = i * 2 + 1;
      const j0 = ((i + 1) % samples.length) * 2;
      const j1 = ((i + 1) % samples.length) * 2 + 1;
      edgeIndices.push(i0, j0, j1, i0, j1, i1);
    }
    const eg = new THREE.BufferGeometry();
    eg.setAttribute("position", new THREE.Float32BufferAttribute(edgePositions, 3));
    eg.setAttribute("color", new THREE.Float32BufferAttribute(edgeColors, 3));
    eg.setIndex(edgeIndices);
    scene.add(new THREE.Mesh(eg, new THREE.MeshBasicMaterial({
      vertexColors: true, toneMapped: false,
    })));
  }

  // ---------- kerbs ----------
  for (const side of [1, -1]) {
    const kpos = [], kcol = [], kidx = [];
    for (let i = 0; i < samples.length; i++) {
      const p = samples[i];
      const tg = tangents[i];
      const nx = -tg.y, nz = tg.x;
      const inner = ROAD_WIDTH / 2 + 1.1;
      const outer = inner + KERB_WIDTH;
      kpos.push(
        p.x + nx * inner * side, 0.16, p.y + nz * inner * side,
        p.x + nx * outer * side, 0.16, p.y + nz * outer * side,
      );
      const stripe = Math.floor(i / 7) % 2 === 0;
      const cr = stripe ? 0.85 : 0.95;
      const cg = stripe ? 0.05 : 0.95;
      const cb = stripe ? 0.18 : 0.95;
      kcol.push(cr, cg, cb, cr, cg, cb);
    }
    for (let i = 0; i < samples.length; i++) {
      const i0 = i * 2, i1 = i * 2 + 1;
      const j0 = ((i + 1) % samples.length) * 2;
      const j1 = ((i + 1) % samples.length) * 2 + 1;
      kidx.push(i0, j0, j1, i0, j1, i1);
    }
    const kg = new THREE.BufferGeometry();
    kg.setAttribute("position", new THREE.Float32BufferAttribute(kpos, 3));
    kg.setAttribute("color", new THREE.Float32BufferAttribute(kcol, 3));
    kg.setIndex(kidx);
    kg.computeVertexNormals();
    const kerb = new THREE.Mesh(kg, new THREE.MeshStandardMaterial({
      vertexColors: true, roughness: 0.6, metalness: 0.2,
    }));
    kerb.receiveShadow = true;
    scene.add(kerb);
  }

  // sector orbs on towers
  for (const s of track.sectors) {
    const idx = Math.floor(s.from * samples.length);
    const p = samples[idx];
    const tg = tangents[idx];
    const nx = -tg.y, nz = tg.x;
    const color = sectorRGB[s.id];
    for (const side of [1, -1]) {
      const x = p.x + nx * (ROAD_WIDTH / 2 + 6) * side;
      const z = p.y + nz * (ROAD_WIDTH / 2 + 6) * side;
      const tower = new THREE.Mesh(
        new THREE.CylinderGeometry(0.6, 0.8, 26, 12),
        new THREE.MeshStandardMaterial({ color: 0x05050a, metalness: 0.7, roughness: 0.35 }),
      );
      tower.position.set(x, 13, z);
      tower.castShadow = true;
      scene.add(tower);
      const orb = new THREE.Mesh(
        new THREE.SphereGeometry(1.8, 24, 24),
        new THREE.MeshBasicMaterial({ color, toneMapped: false }),
      );
      orb.position.set(x, 27, z);
      scene.add(orb);
    }
  }

  // DRS signage
  for (const drs of track.drs || []) {
    const midX = (drs.from[0] + drs.to[0]) / 2 - cx;
    const midY = (drs.from[1] + drs.to[1]) / 2 - cy;
    const stand = new THREE.Mesh(
      new THREE.CylinderGeometry(0.35, 0.35, 28, 8),
      new THREE.MeshStandardMaterial({ color: 0x06060f, metalness: 0.7, roughness: 0.3 }),
    );
    stand.position.set(midX, 14, midY);
    scene.add(stand);
    const plate = new THREE.Mesh(
      new THREE.BoxGeometry(20, 5.5, 1.2),
      new THREE.MeshBasicMaterial({ color: 0x00ff66, toneMapped: false }),
    );
    plate.position.set(midX, 30, midY);
    scene.add(plate);
  }

  // overtake braking bars
  for (const ot of track.overtake_spots || []) {
    const x = ot.x - cx;
    const z = ot.y - cy;
    let nearest = 0;
    let best = Infinity;
    for (let i = 0; i < samples.length; i++) {
      const dx = samples[i].x - x, dz = samples[i].y - z;
      const d = dx * dx + dz * dz;
      if (d < best) { best = d; nearest = i; }
    }
    const tg = tangents[nearest];
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(ROAD_WIDTH + 5, 0.5, 1.6),
      new THREE.MeshBasicMaterial({ color: 0xff1144, toneMapped: false }),
    );
    bar.position.set(x, 0.4, z);
    bar.rotation.y = Math.atan2(tg.x, tg.y);
    scene.add(bar);
  }

  // start/finish chequered band
  {
    const p = samples[0];
    const tg = tangents[0];
    const nx = -tg.y, nz = tg.x;
    for (let row = 0; row < 2; row++) {
      for (let k = 0; k < 14; k++) {
        const slot = k - 6.5;
        const px = p.x + nx * slot * 1.6 + tg.x * row * 1.6;
        const pz = p.y + nz * slot * 1.6 + tg.y * row * 1.6;
        const tile = new THREE.Mesh(
          new THREE.BoxGeometry(1.5, 0.15, 1.5),
          new THREE.MeshStandardMaterial({ color: (k + row) % 2 === 0 ? 0xffffff : 0x06060e }),
        );
        tile.position.set(px, 0.16, pz);
        tile.rotation.y = Math.atan2(tg.x, tg.y);
        tile.receiveShadow = true;
        scene.add(tile);
      }
    }
  }

  // ---------- F1 CAR ----------
  const car = buildF1Car(driverColor);
  scene.add(car);

  const curvePts = samples.map((p) => new THREE.Vector3(p.x, 1.45, p.y));
  const curve = new THREE.CatmullRomCurve3(curvePts, true);

  // particle trail
  const trailLen = 100;
  const trailPositions = new Float32Array(trailLen * 3);
  const trailColors = new Float32Array(trailLen * 3);
  const trailGeom = new THREE.BufferGeometry();
  trailGeom.setAttribute("position", new THREE.BufferAttribute(trailPositions, 3));
  trailGeom.setAttribute("color", new THREE.BufferAttribute(trailColors, 3));
  const trail = new THREE.Points(trailGeom, new THREE.PointsMaterial({
    size: 2.4, vertexColors: true, transparent: true, opacity: 0.95,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }));
  scene.add(trail);
  const trailBase = new THREE.Color(driverColor);

  // ---------- animate ----------
  let t = 0;
  let raf;
  const sectorAffinity = sectorVelocityFactor.bind(null, signals);

  // Spin wheels and DRS hint.
  const wheelMeshes = car.userData.wheels || [];
  function tick() {
    raf = requestAnimationFrame(tick);
    const sector = sectorAt(t, track.sectors);
    const vel = 0.0006 + 0.0012 * sectorAffinity(sector);
    t = (t + vel) % 1;

    const pos = curve.getPointAt(t);
    car.position.copy(pos);
    const look = curve.getPointAt((t + 0.003) % 1);
    car.lookAt(look.x, pos.y, look.z);

    // wheels spin
    const spin = vel * 80;
    wheelMeshes.forEach((w) => (w.rotation.x -= spin));

    for (let i = trailLen - 1; i > 0; i--) {
      trailPositions[i * 3] = trailPositions[(i - 1) * 3];
      trailPositions[i * 3 + 1] = trailPositions[(i - 1) * 3 + 1];
      trailPositions[i * 3 + 2] = trailPositions[(i - 1) * 3 + 2];
    }
    trailPositions[0] = pos.x;
    trailPositions[1] = pos.y - 0.15;
    trailPositions[2] = pos.z;
    for (let i = 0; i < trailLen; i++) {
      const fade = 1 - i / trailLen;
      trailColors[i * 3] = trailBase.r * fade * 1.4;
      trailColors[i * 3 + 1] = trailBase.g * fade * 1.4;
      trailColors[i * 3 + 2] = trailBase.b * fade * 1.4;
    }
    trailGeom.attributes.position.needsUpdate = true;
    trailGeom.attributes.color.needsUpdate = true;

    controls.update();
    composer.render();
  }
  tick();

  function handleResize() {
    const w = container.clientWidth || width;
    renderer.setSize(w, height);
    composer.setSize(w, height);
    camera.aspect = w / height;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", handleResize);

  return () => {
    cancelAnimationFrame(raf);
    window.removeEventListener("resize", handleResize);
    controls.dispose();
    pmrem.dispose();
    composer.dispose?.();
    renderer.dispose();
    container.innerHTML = "";
  };
}

// =============================================================
//   F1 car — built from ~80 primitives for genuine detail
// =============================================================
function buildF1Car(liveryHex) {
  const car = new THREE.Group();
  car.userData.wheels = [];

  const livery = new THREE.Color(liveryHex);
  const carbon = new THREE.MeshStandardMaterial({
    color: 0x080810, metalness: 0.5, roughness: 0.32,
  });
  const liveryMat = new THREE.MeshStandardMaterial({
    color: livery, metalness: 0.85, roughness: 0.18,
    emissive: livery.clone().multiplyScalar(0.12),
    envMapIntensity: 0.9,
  });
  const accentMat = new THREE.MeshStandardMaterial({
    color: 0xeeeeee, metalness: 0.3, roughness: 0.4,
  });
  const tyreMat = new THREE.MeshStandardMaterial({
    color: 0x07070a, metalness: 0.0, roughness: 0.95,
  });
  const rimMat = new THREE.MeshStandardMaterial({
    color: 0x1a1a26, metalness: 0.9, roughness: 0.12,
  });
  const brakeGlow = new THREE.MeshBasicMaterial({
    color: 0xff5500, toneMapped: false,
  });
  const headlight = new THREE.MeshBasicMaterial({ color: 0xfff8e0, toneMapped: false });
  const taillight = new THREE.MeshBasicMaterial({ color: 0xff0033, toneMapped: false });
  const exhaustCore = new THREE.MeshBasicMaterial({ color: 0xffaa44, toneMapped: false });

  // -------------------- floor / chassis tub --------------------
  const floorShape = new THREE.Shape();
  floorShape.moveTo(-2.4, -6.5);
  floorShape.lineTo(2.4, -6.5);
  floorShape.lineTo(2.7, -3);
  floorShape.lineTo(2.7, 3);
  floorShape.lineTo(1.8, 6.5);
  floorShape.lineTo(-1.8, 6.5);
  floorShape.lineTo(-2.7, 3);
  floorShape.lineTo(-2.7, -3);
  floorShape.closePath();
  const floor = new THREE.Mesh(
    new THREE.ExtrudeGeometry(floorShape, {
      depth: 0.45, bevelEnabled: true, bevelSize: 0.18, bevelThickness: 0.12, bevelSegments: 4,
    }),
    carbon,
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = 0.6;
  floor.castShadow = floor.receiveShadow = true;
  car.add(floor);

  // -------------------- nose cone (lathe for smooth taper) --------------------
  const nosePts = [];
  for (let i = 0; i <= 24; i++) {
    const t = i / 24;
    const z = t * 4.2;
    const r = 0.85 * (1 - Math.pow(t, 1.4));
    nosePts.push(new THREE.Vector2(r, z));
  }
  const nose = new THREE.Mesh(
    new THREE.LatheGeometry(nosePts, 24),
    liveryMat,
  );
  nose.rotation.x = Math.PI / 2;
  nose.position.set(0, 0.95, 7.2);
  nose.castShadow = true;
  car.add(nose);

  // nose accent stripe
  const stripe = new THREE.Mesh(
    new THREE.BoxGeometry(0.4, 0.05, 4),
    accentMat,
  );
  stripe.position.set(0, 1.3, 8.2);
  car.add(stripe);

  // -------------------- airbox + engine cover --------------------
  // Airbox intake (above driver, sloped triangular shape)
  const airboxShape = new THREE.Shape();
  airboxShape.moveTo(-0.8, 0);
  airboxShape.lineTo(0.8, 0);
  airboxShape.quadraticCurveTo(0.6, 1.6, 0, 1.7);
  airboxShape.quadraticCurveTo(-0.6, 1.6, -0.8, 0);
  const airbox = new THREE.Mesh(
    new THREE.ExtrudeGeometry(airboxShape, { depth: 1.4, bevelEnabled: false }),
    carbon,
  );
  airbox.position.set(0, 1.95, -0.3);
  airbox.castShadow = true;
  car.add(airbox);

  // shark fin
  const sharkFin = new THREE.Mesh(
    new THREE.BoxGeometry(0.18, 1.55, 4.4),
    carbon,
  );
  sharkFin.position.set(0, 2.35, -2.6);
  car.add(sharkFin);

  // engine cover (sphere flattened)
  const eng = new THREE.Mesh(
    new THREE.SphereGeometry(1.5, 24, 18),
    liveryMat,
  );
  eng.scale.set(1.0, 0.5, 1.4);
  eng.position.set(0, 1.8, -1.9);
  eng.castShadow = true;
  car.add(eng);

  // -------------------- cockpit + halo + helmet --------------------
  const cockpit = new THREE.Mesh(
    new THREE.SphereGeometry(1.3, 24, 18),
    carbon,
  );
  cockpit.scale.set(0.95, 0.55, 1.4);
  cockpit.position.set(0, 1.65, 1.4);
  car.add(cockpit);

  // helmet (visible above cockpit)
  const helmet = new THREE.Mesh(
    new THREE.SphereGeometry(0.55, 24, 18),
    new THREE.MeshStandardMaterial({
      color: 0xfafafa, metalness: 0.4, roughness: 0.25,
      emissive: livery, emissiveIntensity: 0.1,
    }),
  );
  helmet.position.set(0, 2.45, 1.4);
  car.add(helmet);

  // helmet visor (a curved dark band)
  const visor = new THREE.Mesh(
    new THREE.TorusGeometry(0.55, 0.13, 8, 24, Math.PI * 0.7),
    new THREE.MeshStandardMaterial({
      color: 0x0a0a14, metalness: 0.95, roughness: 0.05,
    }),
  );
  visor.position.set(0, 2.45, 1.4);
  visor.rotation.x = Math.PI / 2;
  visor.rotation.y = Math.PI;
  car.add(visor);

  // halo arc (proper 180° torus)
  const halo = new THREE.Mesh(
    new THREE.TorusGeometry(1.55, 0.16, 16, 32, Math.PI),
    new THREE.MeshStandardMaterial({
      color: 0x0a0a14, metalness: 0.6, roughness: 0.35,
    }),
  );
  halo.position.set(0, 2.55, 1.6);
  halo.rotation.x = Math.PI / 2;
  car.add(halo);
  // halo support strut to nose
  const haloStrut = new THREE.Mesh(
    new THREE.CylinderGeometry(0.1, 0.1, 1.3, 6),
    carbon,
  );
  haloStrut.position.set(0, 2.0, 2.4);
  haloStrut.rotation.x = Math.PI / 2.6;
  car.add(haloStrut);

  // mirrors
  for (const side of [1, -1]) {
    const mirrorPod = new THREE.Mesh(
      new THREE.SphereGeometry(0.28, 16, 12),
      liveryMat,
    );
    mirrorPod.scale.set(1.5, 1.0, 1.0);
    mirrorPod.position.set(side * 1.7, 2.0, 1.6);
    car.add(mirrorPod);
    const mirrorStem = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.06, 0.5, 6),
      carbon,
    );
    mirrorStem.position.set(side * 1.3, 2.0, 1.6);
    mirrorStem.rotation.z = Math.PI / 2;
    car.add(mirrorStem);
  }

  // -------------------- side pods + bargeboards --------------------
  for (const side of [1, -1]) {
    // main pod
    const pod = new THREE.Mesh(
      new THREE.BoxGeometry(1.4, 1.15, 4.5),
      liveryMat,
    );
    pod.position.set(side * 1.9, 1.2, -0.8);
    pod.castShadow = true;
    car.add(pod);
    // side intake
    const intake = new THREE.Mesh(
      new THREE.BoxGeometry(0.3, 0.7, 1.2),
      new THREE.MeshStandardMaterial({ color: 0x000000, metalness: 0.4, roughness: 0.7 }),
    );
    intake.position.set(side * 2.55, 1.2, 0.6);
    car.add(intake);
    // bargeboard (vertical curved vane in front of sidepod)
    const bargeShape = new THREE.Shape();
    bargeShape.moveTo(0, 0);
    bargeShape.quadraticCurveTo(0.4, 0.7, 0.3, 1.5);
    bargeShape.lineTo(0.5, 1.5);
    bargeShape.quadraticCurveTo(0.5, 0.6, 0.15, 0);
    bargeShape.closePath();
    const barge = new THREE.Mesh(
      new THREE.ExtrudeGeometry(bargeShape, { depth: 1.6, bevelEnabled: false }),
      carbon,
    );
    barge.position.set(side * 1.8, 0.5, 3.0);
    barge.rotation.y = side > 0 ? Math.PI : 0;
    car.add(barge);
  }

  // -------------------- front wing (multi-element) --------------------
  // Each "flap" is a thin slightly tilted box. End-plates are L-shapes.
  const fwY = 0.42;
  const fwZ = 8.4;
  // main plane
  for (let i = 0; i < 4; i++) {
    const flap = new THREE.Mesh(
      new THREE.BoxGeometry(6.0 - i * 0.2, 0.18, 0.6),
      carbon,
    );
    flap.position.set(0, fwY + i * 0.2, fwZ - i * 0.15);
    flap.rotation.x = -0.08 * (i + 1);
    flap.castShadow = true;
    car.add(flap);
  }
  // accent paint on the top flap
  const fwAccent = new THREE.Mesh(
    new THREE.BoxGeometry(5.4, 0.08, 0.6),
    liveryMat,
  );
  fwAccent.position.set(0, fwY + 0.8, fwZ - 0.6);
  fwAccent.rotation.x = -0.32;
  car.add(fwAccent);
  // end plates
  for (const side of [1, -1]) {
    const ep = new THREE.Mesh(
      new THREE.BoxGeometry(0.18, 1.4, 1.9),
      carbon,
    );
    ep.position.set(side * 3.0, fwY + 0.5, fwZ);
    car.add(ep);
    // flick-up wingtip
    const flick = new THREE.Mesh(
      new THREE.BoxGeometry(0.6, 0.18, 0.9),
      carbon,
    );
    flick.position.set(side * 2.7, fwY + 1.0, fwZ + 0.5);
    flick.rotation.z = side * 0.3;
    car.add(flick);
  }

  // headlights
  for (const side of [1, -1]) {
    const hl = new THREE.Mesh(
      new THREE.BoxGeometry(0.5, 0.25, 0.4),
      headlight,
    );
    hl.position.set(side * 0.7, 1.0, 9.2);
    car.add(hl);
  }

  // -------------------- rear wing (multi-element) --------------------
  const rwY = 2.4;
  const rwZ = -5.95;
  // main plane
  const rwMain = new THREE.Mesh(
    new THREE.BoxGeometry(5.6, 1.2, 0.25),
    carbon,
  );
  rwMain.position.set(0, rwY, rwZ);
  rwMain.castShadow = true;
  car.add(rwMain);
  // DRS upper flap (sits ~30° tilted)
  const drsFlap = new THREE.Mesh(
    new THREE.BoxGeometry(5.0, 0.45, 0.2),
    carbon,
  );
  drsFlap.position.set(0, rwY + 0.85, rwZ);
  drsFlap.rotation.x = -0.4;
  car.add(drsFlap);
  // accent stripe across rear wing
  const rwStripe = new THREE.Mesh(
    new THREE.BoxGeometry(4.6, 0.12, 0.27),
    liveryMat,
  );
  rwStripe.position.set(0, rwY + 0.3, rwZ);
  car.add(rwStripe);
  // beam wing under the main plane
  const beam = new THREE.Mesh(
    new THREE.BoxGeometry(4.0, 0.15, 0.6),
    carbon,
  );
  beam.position.set(0, 1.4, rwZ + 0.2);
  car.add(beam);
  // end plates with vents
  for (const side of [1, -1]) {
    const ep = new THREE.Mesh(
      new THREE.BoxGeometry(0.22, 2.6, 1.5),
      carbon,
    );
    ep.position.set(side * 2.7, rwY - 0.2, rwZ + 0.4);
    car.add(ep);
    // vent slits
    for (let v = 0; v < 3; v++) {
      const slit = new THREE.Mesh(
        new THREE.BoxGeometry(0.25, 0.06, 0.6),
        accentMat,
      );
      slit.position.set(side * 2.7, rwY - 0.6 + v * 0.5, rwZ + 0.3);
      car.add(slit);
    }
  }
  // taillight (FIA-spec red rain light)
  const tail = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.4, 0.16), taillight);
  tail.position.set(0, rwY, rwZ - 0.18);
  car.add(tail);

  // -------------------- engine exhaust plume --------------------
  const exhPipe = new THREE.Mesh(
    new THREE.CylinderGeometry(0.22, 0.28, 0.9, 16),
    new THREE.MeshStandardMaterial({ color: 0x222226, metalness: 0.95, roughness: 0.15 }),
  );
  exhPipe.position.set(0, 1.6, -6.3);
  exhPipe.rotation.x = Math.PI / 2;
  car.add(exhPipe);
  const plume = new THREE.Mesh(
    new THREE.SphereGeometry(0.5, 12, 12),
    exhaustCore,
  );
  plume.scale.set(1.0, 1.0, 2.4);
  plume.position.set(0, 1.6, -7.1);
  car.add(plume);

  // -------------------- rear diffuser --------------------
  const diffShape = new THREE.Shape();
  diffShape.moveTo(-2.2, 0);
  diffShape.lineTo(2.2, 0);
  diffShape.lineTo(1.8, 1.2);
  diffShape.lineTo(-1.8, 1.2);
  diffShape.closePath();
  const diff = new THREE.Mesh(
    new THREE.ExtrudeGeometry(diffShape, { depth: 1.8, bevelEnabled: false }),
    carbon,
  );
  diff.rotation.x = -Math.PI / 2;
  diff.position.set(0, 0.4, -7.0);
  car.add(diff);
  // diffuser vertical fins
  for (let i = -2; i <= 2; i++) {
    const fin = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.45, 1.6),
      accentMat,
    );
    fin.position.set(i * 0.7, 0.6, -6.6);
    car.add(fin);
  }

  // -------------------- wheels (with brake discs + spokes + suspension) --------------------
  const wheelOffsetX = 3.0;
  const wheelOffsetZ = 4.6;
  const wheelY = 1.05;
  for (const x of [wheelOffsetX, -wheelOffsetX]) {
    for (const z of [wheelOffsetZ, -wheelOffsetZ]) {
      const wheelGroup = new THREE.Group();
      wheelGroup.position.set(x, wheelY, z);

      // tyre
      const tyre = new THREE.Mesh(
        new THREE.CylinderGeometry(1.35, 1.35, 1.55, 32, 1, false),
        tyreMat,
      );
      tyre.rotation.z = Math.PI / 2;
      tyre.castShadow = true;
      wheelGroup.add(tyre);

      // sidewall ring (slight raised lip)
      for (const sw of [-0.8, 0.8]) {
        const sidewall = new THREE.Mesh(
          new THREE.TorusGeometry(1.32, 0.06, 8, 32),
          tyreMat,
        );
        sidewall.position.x = sw;
        sidewall.rotation.y = Math.PI / 2;
        wheelGroup.add(sidewall);
      }

      // rim (multi-spoke wheel)
      const rim = new THREE.Mesh(
        new THREE.CylinderGeometry(0.65, 0.65, 1.58, 24),
        rimMat,
      );
      rim.rotation.z = Math.PI / 2;
      wheelGroup.add(rim);

      // 5 spokes
      for (let s = 0; s < 5; s++) {
        const spoke = new THREE.Mesh(
          new THREE.BoxGeometry(1.4, 0.12, 0.06),
          accentMat,
        );
        spoke.rotation.x = (s * Math.PI * 2) / 5;
        wheelGroup.add(spoke);
      }
      // central hub cap
      const hub = new THREE.Mesh(
        new THREE.CylinderGeometry(0.25, 0.25, 1.7, 12),
        new THREE.MeshStandardMaterial({ color: 0xaaaaaa, metalness: 0.95, roughness: 0.18 }),
      );
      hub.rotation.z = Math.PI / 2;
      wheelGroup.add(hub);

      // brake disc (visible orange glow when hot)
      const brake = new THREE.Mesh(
        new THREE.CylinderGeometry(1.0, 1.0, 0.18, 24),
        brakeGlow,
      );
      brake.rotation.z = Math.PI / 2;
      // position slightly inset toward car
      brake.position.x = x > 0 ? -0.45 : 0.45;
      wheelGroup.add(brake);

      car.userData.wheels.push(wheelGroup);
      car.add(wheelGroup);

      // suspension links — 2 wishbones from wheel to chassis
      const linkMat = carbon;
      const towardX = -Math.sign(x);
      for (const off of [0.4, -0.4]) {
        const link = new THREE.Mesh(
          new THREE.CylinderGeometry(0.08, 0.08, 2.4, 6),
          linkMat,
        );
        link.position.set(x + towardX * 1.2, wheelY + 0.1, z + off);
        link.rotation.z = Math.PI / 2;
        link.rotation.y = towardX * 0.15;
        car.add(link);
      }
      // push-rod (diagonal from wheel up to chassis)
      const pushrod = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.08, 2.0, 6),
        linkMat,
      );
      pushrod.position.set(x + towardX * 0.9, wheelY + 0.7, z);
      pushrod.rotation.z = Math.PI / 2.5;
      pushrod.rotation.y = towardX * 0.1;
      car.add(pushrod);
    }
  }

  // -------------------- T-cam fin + onboard cam tip --------------------
  const tcam = new THREE.Mesh(
    new THREE.BoxGeometry(0.28, 0.5, 0.4),
    carbon,
  );
  tcam.position.set(0, 2.85, -0.2);
  car.add(tcam);
  const tcamLens = new THREE.Mesh(
    new THREE.CylinderGeometry(0.08, 0.08, 0.2, 12),
    new THREE.MeshStandardMaterial({ color: 0xeeeeee, metalness: 0.9, roughness: 0.1 }),
  );
  tcamLens.position.set(0, 3.05, -0.2);
  car.add(tcamLens);

  // -------------------- antenna / pitot tubes --------------------
  for (const side of [1, -1]) {
    const pitot = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.04, 0.9, 6),
      accentMat,
    );
    pitot.position.set(side * 0.35, 1.4, 9.0);
    car.add(pitot);
  }

  car.scale.setScalar(0.58);

  // Cast shadows on most mesh children.
  car.traverse((obj) => {
    if (obj.isMesh) {
      obj.castShadow = true;
    }
  });

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
    if (dx * dx + dy * dy < 32 * 32) return true;
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
