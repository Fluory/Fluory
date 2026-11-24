// Halftone field for the hero: one draw call of point sprites, all motion in
// the vertex shader (light source, travelling band, pointer glow, and a scroll
// "tidy-up" that pulls the dots into rows). Renders only while the hero is on
// screen and the tab is visible; device pixel ratio is capped.
import {
  WebGLRenderer,
  Scene,
  OrthographicCamera,
  BufferGeometry,
  BufferAttribute,
  ShaderMaterial,
  Points,
  Color,
} from "./vendor/three.min.js";

const VERT = /* glsl */ `
  attribute float aSeed;
  uniform float uTime;
  uniform float uScroll;
  uniform float uSpacing;
  uniform float uDpr;
  uniform float uPointerOn;
  uniform vec2 uPointer;
  uniform vec2 uRes;
  uniform vec2 uCenter;
  uniform float uFadeLeft;
  varying float vI;
  varying float vHi;

  void main() {
    vec3 p = position;
    vec2 n = p.xy / uRes;

    vec2 d = (n - uCenter) * vec2(1.0, 1.3);
    float glow = exp(-dot(d, d) * 6.0);
    float wave = 0.5 + 0.5 * sin(p.x * 0.011 + p.y * 0.017 + uTime * 0.35);
    float drift = 0.5 + 0.5 * sin(p.x * 0.0045 - p.y * 0.009 - uTime * 0.22);

    float diag = n.x + n.y * 0.35;
    float bpos = fract(uTime * 0.055) * 2.4 - 1.2;
    float band = exp(-pow((diag - bpos) * 6.5, 2.0));

    vec2 pd = p.xy - uPointer;
    float pr = exp(-dot(pd, pd) / (2.0 * 150.0 * 150.0)) * uPointerOn;

    // Scroll: the loose field settles into tidy rows and lifts away.
    float tidy = smoothstep(0.0, 0.75, uScroll);
    float row = uSpacing * 3.0;
    p.y = mix(p.y, floor(p.y / row + 0.5) * row, tidy);
    p.y += uScroll * 90.0 * (0.35 + aSeed);

    float fade = mix(1.0, smoothstep(-0.48, 0.02, n.x), uFadeLeft);
    float I = fade * (0.16 + glow * (0.75 + 0.35 * wave) + 0.22 * drift * glow) + band * 0.5 * fade + pr * 0.85;
    I = clamp(I, 0.0, 1.4);
    vI = I;
    vHi = clamp(band * fade * 1.2 + pr, 0.0, 1.0);
    gl_PointSize = max(1.0, (0.9 + I * 4.4) * uDpr);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const FRAG = /* glsl */ `
  precision mediump float;
  uniform vec3 uColor;
  uniform vec3 uAccent;
  uniform float uAlpha;
  varying float vI;
  varying float vHi;

  void main() {
    float r = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.34, r);
    vec3 col = mix(uColor, uAccent, smoothstep(0.12, 0.75, vHi));
    gl_FragColor = vec4(col, a * uAlpha * (0.3 + 0.7 * min(vI, 1.0)));
  }
`;

function cssColor(name) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const m = v.match(/rgba?\(([^)]+)\)/);
  if (m) {
    const [r, g, b] = m[1].split(",").map((x) => parseFloat(x));
    return new Color(r / 255, g / 255, b / 255);
  }
  return new Color(v || "#ffffff");
}

export function createField(host, { onFirstFrame } = {}) {
  let renderer;
  try {
    renderer = new WebGLRenderer({ antialias: false, alpha: true, powerPreference: "low-power" });
  } catch (e) {
    return null;
  }
  if (!renderer.getContext()) return null;

  // Software rasterisers (no GPU) get a lower internal resolution and 30 fps.
  const gl = renderer.getContext();
  let software = false;
  try {
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    const name = info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "";
    software = /swiftshader|llvmpipe|software|basic render/i.test(name);
  } catch (e) {}
  const dpr = software ? 0.75 : Math.min(window.devicePixelRatio || 1, 1.5);
  let minFrame = software ? 1000 / 30 - 2 : 0;
  renderer.setPixelRatio(dpr);
  renderer.setClearColor(0x000000, 0);
  host.appendChild(renderer.domElement);

  const scene = new Scene();
  const camera = new OrthographicCamera(-1, 1, 1, -1, -10, 10);
  const uniforms = {
    uTime: { value: 0 },
    uScroll: { value: 0 },
    uSpacing: { value: 18 },
    uDpr: { value: dpr },
    uPointerOn: { value: 0 },
    uPointer: { value: [0, 0] },
    uRes: { value: [1, 1] },
    uCenter: { value: [0.22, 0.06] },
    uFadeLeft: { value: 1 },
    uColor: { value: new Color() },
    uAccent: { value: new Color() },
    uAlpha: { value: 0.6 },
  };
  const material = new ShaderMaterial({
    uniforms,
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });
  const geometry = new BufferGeometry();
  const points = new Points(geometry, material);
  points.frustumCulled = false;
  scene.add(points);

  function theme() {
    uniforms.uColor.value.copy(cssColor("--fg"));
    uniforms.uAccent.value.copy(cssColor("--ice"));
    const light = getComputedStyle(document.documentElement).colorScheme.includes("light");
    uniforms.uAlpha.value = light ? 0.42 : 0.62;
  }

  let w = 0;
  let h = 0;
  function build() {
    const rect = host.getBoundingClientRect();
    w = Math.max(1, Math.round(rect.width));
    h = Math.max(1, Math.round(rect.height));
    const narrow = w < 720;
    const step = narrow ? 16 : 18;
    uniforms.uSpacing.value = step;
    uniforms.uRes.value = [w, h];
    uniforms.uCenter.value = narrow ? [0.32, 0.36] : [0.22, 0.06];
    uniforms.uFadeLeft.value = narrow ? 0 : 1;
    camera.left = -w / 2;
    camera.right = w / 2;
    camera.top = h / 2;
    camera.bottom = -h / 2;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);

    const rowStep = step * 0.866;
    const cols = Math.ceil(w / step) + 2;
    const rows = Math.ceil((h + 140) / rowStep) + 2;
    const pos = new Float32Array(cols * rows * 3);
    const seed = new Float32Array(cols * rows);
    let i = 0;
    for (let r = 0; r < rows; r++) {
      const y = -h / 2 - 140 + r * rowStep;
      const off = r % 2 ? step / 2 : 0;
      for (let c = 0; c < cols; c++) {
        pos[i * 3] = -w / 2 - step + c * step + off;
        pos[i * 3 + 1] = y;
        pos[i * 3 + 2] = 0;
        seed[i] = Math.abs(Math.sin(i * 12.9898) * 43758.5453) % 1;
        i++;
      }
    }
    geometry.setAttribute("position", new BufferAttribute(pos, 3));
    geometry.setAttribute("aSeed", new BufferAttribute(seed, 1));
    geometry.computeBoundingSphere();
    stats.points = cols * rows;
  }

  const stats = { frames: 0, cpuMs: 0, points: 0, start: performance.now(), software };
  window.__field = stats;

  // Pointer: eased towards the target, glow fades out when the pointer rests.
  const target = { x: 0, y: 0 };
  let lastMove = -1e9;
  function onPointer(e) {
    const rect = host.getBoundingClientRect();
    target.x = e.clientX - rect.left - w / 2;
    target.y = h / 2 - (e.clientY - rect.top);
    lastMove = performance.now();
  }
  window.addEventListener("pointermove", onPointer, { passive: true });

  let running = false;
  let inView = true;
  let raf = 0;
  let t0 = performance.now();
  let time = 0;
  let first = true;

  // Adaptive: if frames arrive slowly anyway, settle at 30 fps instead of
  // keeping the main thread busy.
  let slow = 0;
  let last = 0;
  function frame(now) {
    raf = 0;
    if (!running) return;
    if (minFrame && now - last < minFrame) {
      raf = requestAnimationFrame(frame);
      return;
    }
    if (last && !minFrame) {
      slow = now - last > 24 ? slow + 1 : Math.max(0, slow - 1);
      if (slow > 45) minFrame = 1000 / 30 - 2;
    }
    last = now;
    const dt = Math.min(0.05, (now - t0) / 1000);
    t0 = now;
    time += dt;
    const c0 = performance.now();
    uniforms.uTime.value = time;
    const p = uniforms.uPointer.value;
    p[0] += (target.x - p[0]) * Math.min(1, dt * 6);
    p[1] += (target.y - p[1]) * Math.min(1, dt * 6);
    const on = now - lastMove < 1600 ? 1 : 0;
    uniforms.uPointerOn.value += (on - uniforms.uPointerOn.value) * Math.min(1, dt * (on ? 4 : 1.2));
    renderer.render(scene, camera);
    stats.cpuMs += performance.now() - c0;
    stats.frames++;
    if (first) {
      first = false;
      onFirstFrame && onFirstFrame();
    }
    raf = requestAnimationFrame(frame);
  }
  function update() {
    const should = inView && !document.hidden;
    if (should && !running) {
      running = true;
      t0 = performance.now();
      raf = requestAnimationFrame(frame);
    } else if (!should && running) {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    }
    stats.running = running;
  }

  const io = new IntersectionObserver((entries) => {
    inView = entries[0].isIntersecting;
    update();
  });
  io.observe(host);
  document.addEventListener("visibilitychange", update);

  let resizeTimer = 0;
  const ro = new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      build();
      if (!running) renderer.render(scene, camera);
    }, 120);
  });

  theme();
  build();
  ro.observe(host);
  update();

  return {
    setScroll(v) {
      uniforms.uScroll.value = v;
    },
    theme() {
      theme();
      if (!running) renderer.render(scene, camera);
    },
  };
}
