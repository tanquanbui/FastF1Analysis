import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { TRACKS } from "./tracks_data.js";

/**
 * Minimal 3D track scene: just the circuit outline as a glowing tube
 * and a single dot in the driver's team livery flying around it.
 * No sector chrome, no DRS overlays, no kerbs, no signage clutter.
 */

const SAMPLES = 1400;

export function render3DTrack({
  containerId,
  circuitKey,
  driverColor = "#e8002d",
  signals = {},
}) {
  const container = document.getElementById(containerId);
  if (!container) return () => {};
  const track = TRACKS[circuitKey] || Object.values(TRACKS)[0];
  container.innerHTML = "";

  const width = container.clientWidth || 720;
  const height = 460;

  // ---------- renderer + composer ----------
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width, height);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, width / height, 0.5, 6000);
  const introStartPos = new THREE.Vector3(-1800, 1500, 1800);
  const introEndPos = new THREE.Vector3(-420, 380, 520);
  camera.position.copy(introStartPos);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(width, height), 0.7, 0.6, 0.3);
  bloom.threshold = 0.4;
  bloom.strength = 0.85;
  bloom.radius = 0.55;
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 0.35;
  controls.minPolarAngle = Math.PI / 8;
  controls.maxPolarAngle = Math.PI / 2.05;
  controls.enabled = false;

  // ---------- sky dome ----------
  scene.add(new THREE.Mesh(
    new THREE.SphereGeometry(2500, 32, 16),
    new THREE.ShaderMaterial({
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
        }`,
      fragmentShader: `
        uniform vec3 top;
        uniform vec3 bottom;
        varying vec3 vPos;
        void main() {
          float h = clamp(vPos.y / 2500.0 + 0.2, 0.0, 1.0);
          gl_FragColor = vec4(mix(bottom, top, h), 1.0);
        }`,
    }),
  ));

  // ---------- lighting ----------
  scene.add(new THREE.AmbientLight(0x1a1a26, 0.55));
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(400, 800, 200);
  scene.add(key);
  scene.add(new THREE.HemisphereLight(0x222233, 0x000000, 0.4));

  // ---------- ground ----------
  scene.add((() => {
    const g = new THREE.Mesh(
      new THREE.PlaneGeometry(4000, 4000),
      new THREE.MeshStandardMaterial({ color: 0x04040a, roughness: 1, metalness: 0 }),
    );
    g.rotation.x = -Math.PI / 2;
    g.position.y = -2.5;
    return g;
  })());

  // ---------- sample + smooth path ----------
  const rawSamples = samplePath(track.path, 200);
  const cx = rawSamples.reduce((a, p) => a + p.x, 0) / rawSamples.length;
  const cy = rawSamples.reduce((a, p) => a + p.y, 0) / rawSamples.length;
  const smoothCurve = new THREE.CatmullRomCurve3(
    rawSamples.map((p) => new THREE.Vector3(p.x - cx, 1.2, p.y - cy)),
    true,
    "catmullrom",
    0.5,
  );
  const points = [];
  for (let i = 0; i < SAMPLES; i++) {
    points.push(smoothCurve.getPointAt(i / SAMPLES));
  }
  const curve = new THREE.CatmullRomCurve3(points, true, "catmullrom", 0.5);

  // ---------- TRACK OUTLINE: bright glowing tube ----------
  const tubeGeom = new THREE.TubeGeometry(curve, 800, 1.8, 12, true);
  const tubeMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color(driverColor),
    emissive: new THREE.Color(driverColor),
    emissiveIntensity: 1.6,
    metalness: 0.5,
    roughness: 0.35,
    toneMapped: false,
  });
  scene.add(new THREE.Mesh(tubeGeom, tubeMat));

  // Subtle underline beneath the tube for a sense of physical track.
  const baseTube = new THREE.TubeGeometry(curve, 600, 4, 10, true);
  const baseMat = new THREE.MeshStandardMaterial({
    color: 0x101018, metalness: 0.4, roughness: 0.5,
  });
  scene.add(new THREE.Mesh(baseTube, baseMat));

  // ---------- DRIVER DOT ----------
  const dot = new THREE.Mesh(
    new THREE.SphereGeometry(2.4, 24, 24),
    new THREE.MeshStandardMaterial({
      color: new THREE.Color(driverColor),
      emissive: new THREE.Color(driverColor),
      emissiveIntensity: 2.0,
      toneMapped: false,
    }),
  );
  scene.add(dot);

  // particle trail behind the dot
  const trailLen = 80;
  const trailPositions = new Float32Array(trailLen * 3);
  const trailColors = new Float32Array(trailLen * 3);
  const trailGeom = new THREE.BufferGeometry();
  trailGeom.setAttribute("position", new THREE.BufferAttribute(trailPositions, 3));
  trailGeom.setAttribute("color", new THREE.BufferAttribute(trailColors, 3));
  const trail = new THREE.Points(trailGeom, new THREE.PointsMaterial({
    size: 2.2, vertexColors: true, transparent: true, opacity: 1,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }));
  scene.add(trail);
  const trailBase = new THREE.Color(driverColor);

  // ---------- animate ----------
  let t = 0;
  let raf;
  const INTRO_MS = 2000;
  const introStart = performance.now();
  let introDone = false;
  const easeInOutCubic = (x) =>
    x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;

  // velocity factor (defaults to mid-pace if signals missing)
  const vBase = Math.max(0.5, Math.min(1, (signals?.combined ?? 60) / 100));

  function tick() {
    raf = requestAnimationFrame(tick);

    if (!introDone) {
      const u = Math.min(1, (performance.now() - introStart) / INTRO_MS);
      const eased = easeInOutCubic(u);
      camera.position.lerpVectors(introStartPos, introEndPos, eased);
      camera.lookAt(0, 0, 0);
      bloom.strength = 0.85 * eased;
      if (u >= 1) {
        introDone = true;
        controls.enabled = true;
        controls.autoRotate = true;
      }
    }

    t = (t + 0.0006 + 0.0008 * vBase) % 1;
    const pos = curve.getPointAt(t);
    dot.position.copy(pos);
    dot.position.y += 1.5;

    for (let i = trailLen - 1; i > 0; i--) {
      trailPositions[i * 3] = trailPositions[(i - 1) * 3];
      trailPositions[i * 3 + 1] = trailPositions[(i - 1) * 3 + 1];
      trailPositions[i * 3 + 2] = trailPositions[(i - 1) * 3 + 2];
    }
    trailPositions[0] = pos.x;
    trailPositions[1] = pos.y + 1.5;
    trailPositions[2] = pos.z;
    for (let i = 0; i < trailLen; i++) {
      const fade = 1 - i / trailLen;
      trailColors[i * 3 + 0] = trailBase.r * fade * 1.4;
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
    composer.dispose?.();
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
