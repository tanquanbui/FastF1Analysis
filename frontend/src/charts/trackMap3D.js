import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { TRACKS } from "./tracks_data.js";

/**
 * Cinematic night-race 3D circuit visualisation.
 *
 *   - HDR-ish sky dome with deep-navy gradient
 *   - Real road ribbon with sector + DRS vertex colouring
 *   - Neon-pink/cyan edge lights ringing the track (point lights)
 *   - Detailed F1 car: glowing rims, headlights, taillights, halo,
 *     animated DRS flap, engine plume sprite
 *   - Particle trail of fading dots behind the car
 *   - UnrealBloomPass postprocessing for genuine glow on every emissive
 *     surface, ACES tone mapping, slow cinematic camera
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
  const height = 460;

  // ---------- renderer + composer ----------
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width, height);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, width / height, 0.5, 6000);
  camera.position.set(-360, 380, 480);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(width, height), 0.95, 0.55, 0.18);
  bloom.threshold = 0.04;
  bloom.strength = 1.05;
  bloom.radius = 0.85;
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  // ---------- controls ----------
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.35;
  controls.minPolarAngle = Math.PI / 8;
  controls.maxPolarAngle = Math.PI / 2.05;

  // ---------- sky dome ----------
  const skyGeom = new THREE.SphereGeometry(2500, 32, 16);
  const skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    uniforms: {
      top:    { value: new THREE.Color("#02020a") },
      bottom: { value: new THREE.Color("#1a0612") },
    },
    vertexShader: `
      varying vec3 vPos;
      void main() {
        vPos = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 top;
      uniform vec3 bottom;
      varying vec3 vPos;
      void main() {
        float h = clamp((vPos.y / 2500.0) + 0.2, 0.0, 1.0);
        vec3 c = mix(bottom, top, h);
        gl_FragColor = vec4(c, 1.0);
      }
    `,
  });
  scene.add(new THREE.Mesh(skyGeom, skyMat));

  // ---------- lighting ----------
  scene.add(new THREE.AmbientLight(0x202028, 0.45));

  const moon = new THREE.DirectionalLight(0xbcc6ff, 1.2);
  moon.position.set(400, 900, 300);
  scene.add(moon);

  const rim = new THREE.DirectionalLight(0xff3366, 0.7);
  rim.position.set(-600, 250, -400);
  scene.add(rim);

  scene.add(new THREE.HemisphereLight(0x1a1a2c, 0x000000, 0.6));

  // ---------- ground plane ----------
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(4000, 4000, 64, 64),
    new THREE.MeshStandardMaterial({
      color: 0x05050a,
      roughness: 1,
      metalness: 0,
    }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -2.5;
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

    const lx = p.x + nx * (ROAD_WIDTH / 2);
    const lz = p.y + nz * (ROAD_WIDTH / 2);
    const rx = p.x - nx * (ROAD_WIDTH / 2);
    const rz = p.y - nz * (ROAD_WIDTH / 2);
    roadPositions.push(lx, 0, lz, rx, 0, rz);

    let r, g, b;
    if (inDrs) {
      // glowing green DRS road
      r = 0.05; g = 0.95; b = 0.35;
    } else {
      // very dark asphalt with a touch of sector tint
      r = 0.03 + tint.r * 0.04;
      g = 0.03 + tint.g * 0.04;
      b = 0.05 + tint.b * 0.05;
    }
    roadColors.push(r, g, b, r, g, b);
  }
  for (let i = 0; i < samples.length; i++) {
    const i0 = i * 2, i1 = i * 2 + 1;
    const j0 = ((i + 1) % samples.length) * 2;
    const j1 = ((i + 1) % samples.length) * 2 + 1;
    roadIndices.push(i0, j0, j1, i0, j1, i1);
  }

  const roadGeom = new THREE.BufferGeometry();
  roadGeom.setAttribute("position", new THREE.Float32BufferAttribute(roadPositions, 3));
  roadGeom.setAttribute("color", new THREE.Float32BufferAttribute(roadColors, 3));
  roadGeom.setIndex(roadIndices);
  roadGeom.computeVertexNormals();
  scene.add(new THREE.Mesh(roadGeom, new THREE.MeshStandardMaterial({
    vertexColors: true, metalness: 0.5, roughness: 0.45,
  })));

  // ---------- bright glowing edge ribbons (cyan / magenta) ----------
  for (const side of [1, -1]) {
    const edgePositions = [];
    const edgeColors = [];
    const edgeIndices = [];
    const edgeColor = side === 1 ? new THREE.Color("#22d3ee") : new THREE.Color("#ff007a");
    for (let i = 0; i < samples.length; i++) {
      const p = samples[i];
      const tg = tangents[i];
      const nx = -tg.y, nz = tg.x;
      const inner = ROAD_WIDTH / 2 + 0.4;
      const outer = inner + 0.6;
      edgePositions.push(
        p.x + nx * inner * side, 0.05, p.y + nz * inner * side,
        p.x + nx * outer * side, 0.05, p.y + nz * outer * side,
      );
      edgeColors.push(edgeColor.r, edgeColor.g, edgeColor.b, edgeColor.r, edgeColor.g, edgeColor.b);
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
    scene.add(new THREE.Mesh(eg, new THREE.MeshStandardMaterial({
      vertexColors: true, emissive: 0xffffff, emissiveIntensity: 0.0,
      // The bloom + bright colour gives glow.
      toneMapped: false,
    })));
  }

  // ---------- kerbs ----------
  for (const side of [1, -1]) {
    const kerbPositions = [];
    const kerbColors = [];
    const kerbIndices = [];
    for (let i = 0; i < samples.length; i++) {
      const p = samples[i];
      const tg = tangents[i];
      const nx = -tg.y, nz = tg.x;
      const inner = ROAD_WIDTH / 2 + 1.2;
      const outer = inner + KERB_WIDTH;
      kerbPositions.push(
        p.x + nx * inner * side, 0.15, p.y + nz * inner * side,
        p.x + nx * outer * side, 0.15, p.y + nz * outer * side,
      );
      const stripe = Math.floor(i / 7) % 2 === 0;
      const cr = stripe ? 0.85 : 0.95;
      const cg = stripe ? 0.05 : 0.95;
      const cb = stripe ? 0.18 : 0.95;
      kerbColors.push(cr, cg, cb, cr, cg, cb);
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
    scene.add(new THREE.Mesh(kg, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55 })));
  }

  // ---------- sector boundary towers ----------
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
        new THREE.CylinderGeometry(0.7, 0.9, 26, 12),
        new THREE.MeshStandardMaterial({
          color: 0x06060c, metalness: 0.6, roughness: 0.4,
        }),
      );
      tower.position.set(x, 13, z);
      scene.add(tower);
      const orb = new THREE.Mesh(
        new THREE.SphereGeometry(1.8, 16, 16),
        new THREE.MeshStandardMaterial({
          color, emissive: color, emissiveIntensity: 1.6, toneMapped: false,
        }),
      );
      orb.position.set(x, 27, z);
      scene.add(orb);
    }
  }

  // ---------- DRS floating signs ----------
  for (const drs of track.drs || []) {
    const midX = (drs.from[0] + drs.to[0]) / 2 - cx;
    const midY = (drs.from[1] + drs.to[1]) / 2 - cy;
    const stand = new THREE.Mesh(
      new THREE.CylinderGeometry(0.4, 0.4, 28, 8),
      new THREE.MeshStandardMaterial({ color: 0x080814, metalness: 0.6 }),
    );
    stand.position.set(midX, 14, midY);
    scene.add(stand);
    const plate = new THREE.Mesh(
      new THREE.BoxGeometry(18, 5, 1),
      new THREE.MeshStandardMaterial({
        color: 0x00ff66, emissive: 0x00ff66, emissiveIntensity: 1.4, toneMapped: false,
      }),
    );
    plate.position.set(midX, 30, midY);
    scene.add(plate);
  }

  // ---------- overtake braking-zone bars ----------
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
      new THREE.BoxGeometry(ROAD_WIDTH + 5, 0.6, 1.6),
      new THREE.MeshStandardMaterial({
        color: 0xff1144, emissive: 0xff1144, emissiveIntensity: 1.3, toneMapped: false,
      }),
    );
    bar.position.set(x, 0.4, z);
    bar.rotation.y = Math.atan2(tg.x, tg.y);
    scene.add(bar);
  }

  // ---------- start/finish chequered pattern ----------
  {
    const p = samples[0];
    const tg = tangents[0];
    const nx = -tg.y, nz = tg.x;
    for (let row = 0; row < 2; row++) {
      for (let k = 0; k < 14; k++) {
        const slot = (k - 6.5);
        const px = p.x + nx * slot * 1.6 + tg.x * row * 1.6;
        const pz = p.y + nz * slot * 1.6 + tg.y * row * 1.6;
        const tile = new THREE.Mesh(
          new THREE.BoxGeometry(1.5, 0.18, 1.5),
          new THREE.MeshStandardMaterial({
            color: (k + row) % 2 === 0 ? 0xffffff : 0x080810,
          }),
        );
        tile.position.set(px, 0.18, pz);
        tile.rotation.y = Math.atan2(tg.x, tg.y);
        scene.add(tile);
      }
    }
  }

  // ---------- F1 CAR ----------
  const car = buildF1Car(driverColor);
  scene.add(car);

  const curvePts = samples.map((p) => new THREE.Vector3(p.x, 1.6, p.y));
  const curve = new THREE.CatmullRomCurve3(curvePts, true);

  // ---------- particle trail ----------
  const trailLen = 90;
  const trailPositions = new Float32Array(trailLen * 3);
  const trailColors = new Float32Array(trailLen * 3);
  const trailGeom = new THREE.BufferGeometry();
  trailGeom.setAttribute("position", new THREE.BufferAttribute(trailPositions, 3));
  trailGeom.setAttribute("color", new THREE.BufferAttribute(trailColors, 3));
  const trailMat = new THREE.PointsMaterial({
    size: 2.2,
    vertexColors: true,
    transparent: true,
    opacity: 0.95,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const trail = new THREE.Points(trailGeom, trailMat);
  scene.add(trail);
  const trailBase = new THREE.Color(driverColor);

  // ---------- animate ----------
  let t = 0;
  let raf;
  let frame = 0;
  const sectorAffinity = sectorVelocityFactor.bind(null, signals);
  function tick() {
    raf = requestAnimationFrame(tick);
    frame++;

    const sector = sectorAt(t, track.sectors);
    const vel = 0.0006 + 0.0012 * sectorAffinity(sector);
    t = (t + vel) % 1;

    const pos = curve.getPointAt(t);
    car.position.copy(pos);
    const look = curve.getPointAt((t + 0.003) % 1);
    car.lookAt(look.x, pos.y, look.z);

    // shift trail
    for (let i = trailLen - 1; i > 0; i--) {
      trailPositions[i * 3 + 0] = trailPositions[(i - 1) * 3 + 0];
      trailPositions[i * 3 + 1] = trailPositions[(i - 1) * 3 + 1];
      trailPositions[i * 3 + 2] = trailPositions[(i - 1) * 3 + 2];
    }
    trailPositions[0] = pos.x;
    trailPositions[1] = pos.y - 0.2;
    trailPositions[2] = pos.z;

    for (let i = 0; i < trailLen; i++) {
      const fade = 1 - i / trailLen;
      trailColors[i * 3 + 0] = trailBase.r * fade;
      trailColors[i * 3 + 1] = trailBase.g * fade;
      trailColors[i * 3 + 2] = trailBase.b * fade;
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
    composer.dispose?.();
    renderer.dispose();
    container.innerHTML = "";
  };
}

// =============================================================
//                    F1 car model
// =============================================================

function buildF1Car(liveryHex) {
  const livery = new THREE.Color(liveryHex);
  const dark = new THREE.Color("#0d0d12");
  const tyre = new THREE.Color("#08080a");
  const wing = new THREE.Color("#03030a");

  const car = new THREE.Group();

  const bodyMat = new THREE.MeshStandardMaterial({
    color: livery, metalness: 0.78, roughness: 0.18,
    emissive: livery, emissiveIntensity: 0.18,
  });
  const darkMat = new THREE.MeshStandardMaterial({
    color: dark, metalness: 0.55, roughness: 0.35,
  });
  const tyreMat = new THREE.MeshStandardMaterial({
    color: tyre, metalness: 0.0, roughness: 0.95,
  });
  const wingMat = new THREE.MeshStandardMaterial({
    color: wing, metalness: 0.55, roughness: 0.3,
  });
  const glowWhite = new THREE.MeshStandardMaterial({
    color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 1.4, toneMapped: false,
  });
  const glowRed = new THREE.MeshStandardMaterial({
    color: 0xff0033, emissive: 0xff0033, emissiveIntensity: 1.6, toneMapped: false,
  });
  const glowOrange = new THREE.MeshStandardMaterial({
    color: 0xff7733, emissive: 0xff5500, emissiveIntensity: 2.0, toneMapped: false,
  });

  // Main floor
  const floor = new THREE.Mesh(new THREE.BoxGeometry(4.6, 0.6, 12), bodyMat);
  floor.position.y = 0.85;
  car.add(floor);

  // Nose wedge
  const noseGeom = new THREE.ConeGeometry(0.95, 3.8, 6);
  const nose = new THREE.Mesh(noseGeom, bodyMat);
  nose.rotation.x = Math.PI / 2;
  nose.position.set(0, 0.95, 7.6);
  car.add(nose);

  // Engine cover / shark fin
  const sharkFin = new THREE.Mesh(new THREE.BoxGeometry(0.4, 1.6, 4.5), bodyMat);
  sharkFin.position.set(0, 2.1, -2.5);
  car.add(sharkFin);

  // Cockpit hump (rounded box-ish via Sphere)
  const cockpit = new THREE.Mesh(new THREE.SphereGeometry(1.4, 16, 12), bodyMat);
  cockpit.scale.set(1.0, 0.55, 1.4);
  cockpit.position.set(0, 1.85, 1.2);
  car.add(cockpit);

  // Halo arc — proper rounded torus segment
  const halo = new THREE.Mesh(
    new THREE.TorusGeometry(1.55, 0.18, 12, 24, Math.PI),
    darkMat,
  );
  halo.position.set(0, 2.35, 1.6);
  halo.rotation.x = Math.PI / 2;
  car.add(halo);

  // Front wing main plane + flaps
  const fwMain = new THREE.Mesh(new THREE.BoxGeometry(6.2, 0.3, 1.6), wingMat);
  fwMain.position.set(0, 0.5, 8.4);
  car.add(fwMain);
  const fwFlap = new THREE.Mesh(new THREE.BoxGeometry(5.8, 0.18, 1.0), wingMat);
  fwFlap.position.set(0, 0.8, 8.7);
  car.add(fwFlap);
  for (const side of [1, -1]) {
    const ep = new THREE.Mesh(new THREE.BoxGeometry(0.35, 1.4, 1.8), wingMat);
    ep.position.set(side * 3.05, 0.95, 8.4);
    car.add(ep);
  }

  // Headlights (small glowing tabs on the nose).
  for (const side of [1, -1]) {
    const hl = new THREE.Mesh(
      new THREE.BoxGeometry(0.4, 0.25, 0.4),
      glowWhite,
    );
    hl.position.set(side * 0.5, 1.0, 9.1);
    car.add(hl);
  }

  // Rear wing
  const rwEnd = new THREE.Mesh(new THREE.BoxGeometry(5.6, 1.7, 0.3), wingMat);
  rwEnd.position.set(0, 2.5, -5.9);
  car.add(rwEnd);
  for (const side of [1, -1]) {
    const ep = new THREE.Mesh(new THREE.BoxGeometry(0.35, 2.5, 1.4), wingMat);
    ep.position.set(side * 2.65, 1.9, -5.6);
    car.add(ep);
  }
  // DRS flap (sits on top of rear wing).
  const drsFlap = new THREE.Mesh(new THREE.BoxGeometry(4.8, 0.4, 0.2), wingMat);
  drsFlap.position.set(0, 3.1, -5.75);
  car.add(drsFlap);
  // Rear taillight (glowing red bar in the middle of the rear wing).
  const tail = new THREE.Mesh(
    new THREE.BoxGeometry(0.8, 0.4, 0.15),
    glowRed,
  );
  tail.position.set(0, 2.5, -6.05);
  car.add(tail);

  // Engine exhaust plume (orange glowing core).
  const plume = new THREE.Mesh(
    new THREE.SphereGeometry(0.6, 12, 12),
    glowOrange,
  );
  plume.scale.set(1.0, 1.0, 1.8);
  plume.position.set(0, 1.5, -6.6);
  car.add(plume);

  // Side pods (the bulges next to the cockpit).
  for (const side of [1, -1]) {
    const sp = new THREE.Mesh(new THREE.BoxGeometry(1.3, 1.05, 4.5), bodyMat);
    sp.position.set(side * 1.85, 1.3, -0.5);
    car.add(sp);
  }

  // Rear diffuser.
  const diffuser = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.4, 1.8), darkMat);
  diffuser.position.set(0, 0.4, -5.8);
  car.add(diffuser);

  // Wheels with glowing rims.
  const wheelGeom = new THREE.CylinderGeometry(1.3, 1.3, 1.6, 28);
  const rimGeom = new THREE.CylinderGeometry(0.55, 0.55, 1.62, 20);
  const rimMat = new THREE.MeshStandardMaterial({
    color: 0x1a1a24, metalness: 0.85, roughness: 0.15,
    emissive: 0x301030, emissiveIntensity: 0.5,
  });
  const wheelOffsetX = 3.1;
  const wheelOffsetZ = 4.6;
  const wheelY = 1.0;
  for (const x of [wheelOffsetX, -wheelOffsetX]) {
    for (const z of [wheelOffsetZ, -wheelOffsetZ]) {
      const wheel = new THREE.Mesh(wheelGeom, tyreMat);
      wheel.position.set(x, wheelY, z);
      wheel.rotation.z = Math.PI / 2;
      const rim = new THREE.Mesh(rimGeom, rimMat);
      rim.rotation.z = Math.PI / 2;
      wheel.add(rim);
      car.add(wheel);
    }
  }

  // T-cam fin on top of the airbox.
  const tcam = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.35, 0.4), bodyMat);
  tcam.position.set(0, 2.7, -0.5);
  car.add(tcam);

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
