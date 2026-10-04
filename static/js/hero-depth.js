"use strict";

const hero = document.querySelector("[data-hero-depth]");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
let stop = null;
let starting = false;

async function start() {
  if (!hero || stop || starting || reducedMotion.matches || navigator.connection?.saveData) return;
  starting = true;
  const canvas = document.createElement("canvas");
  canvas.className = "hero-depth-canvas";
  canvas.setAttribute("aria-hidden", "true");
  let renderer;
  try {
    const context = canvas.getContext("webgl2", {alpha: false, antialias: true, powerPreference: "low-power"});
    if (!context) { hero.dataset.depthState = "fallback"; return; }
    const THREE = await import("../vendor/three/three.module.js");
    if (reducedMotion.matches) return;
    renderer = new THREE.WebGLRenderer({canvas, context, antialias: true});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 3));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10);
    camera.position.z = 3;
    const material = new THREE.MeshBasicMaterial({toneMapped: false});
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
    scene.add(mesh);
    hero.querySelector(".hero-scrim").before(canvas);
    let image = null;
    let texture = null;
    let textureSource = "";
    const textureLoader = new THREE.TextureLoader();
    let visible = true;
    let lost = false;
    let disposed = false;
    let frame = 0;
    let imageVersion = 0;
    let previousTime = 0;
    let elapsed = 0;

    function pause() {
      cancelAnimationFrame(frame);
      frame = 0;
      previousTime = 0;
    }
    function wake() {
      if (!frame && texture && visible && !lost && !disposed && !document.hidden) frame = requestAnimationFrame(draw);
    }
    function draw(time) {
      frame = 0;
      if (disposed || lost || !visible || document.hidden) return;
      if (previousTime && time - previousTime < 1000 / 30 - 1) { wake(); return; }
      if (previousTime) elapsed += Math.min(time - previousTime, 100) / 1000;
      previousTime = time;
      const phase = elapsed * Math.PI * 2 / 24;
      const x = Math.sin(phase) * 0.12;
      const y = Math.sin(phase * 2) * 0.045;
      camera.position.set(x, y, 3);
      camera.lookAt(x * 0.3, y * 0.3, 0);
      try { renderer.render(scene, camera); }
      catch { stop?.(); hero.dataset.depthState = "fallback"; return; }
      hero.classList.add("has-depth");
      hero.dataset.depthState = "ready";
      wake();
    }
    function geometry() {
      if (!image || !texture) return;
      const {width, height} = hero.getBoundingClientRect();
      if (!width || !height) return;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      const imageAspect = texture.image.width / texture.image.height;
      const [x, y] = getComputedStyle(image).objectPosition.split(" ").map(value => clamp(parseFloat(value) / 100, 0, 1));
      const cropX = Math.min(1, camera.aspect / imageAspect);
      const cropY = Math.min(1, imageAspect / camera.aspect);
      const viewHeight = 6 * Math.tan(THREE.MathUtils.degToRad(35 / 2));
      const plane = new THREE.PlaneGeometry(viewHeight * camera.aspect * 1.09, viewHeight * 1.09, 112, 64);
      const positions = plane.attributes.position;
      const uv = plane.attributes.uv;
      // Compensate perspective at rest so the photo is not stretched into a dome.
      for (let index = 0; index < positions.count; index++) {
        const u = (1 - cropX) * x + uv.getX(index) * cropX;
        const v = (1 - cropY) * (1 - y) + uv.getY(index) * cropY;
        const subject = Math.exp(-(((u - 0.53) / 0.19) ** 2 + ((v - 0.47) / 0.29) ** 2) * 1.4);
        const foreground = (1 - THREE.MathUtils.smoothstep(v, 0.03, 0.45)) * 0.09;
        const depth = subject * 0.28 + foreground;
        const compensation = (3 - depth) / 3;
        positions.setXYZ(index, positions.getX(index) * compensation, positions.getY(index) * compensation, depth);
        uv.setXY(index, u, v);
      }
      mesh.geometry.dispose();
      mesh.geometry = plane;
      wake();
    }
    async function refreshImage() {
      const active = Array.from(hero.querySelectorAll(".hero-photo img, .mobile-hero-photo img")).find(photo => photo.getClientRects().length);
      if (!active) return;
      const version = ++imageVersion;
      if (image !== active) hero.classList.remove("has-depth");
      try { await active.decode(); } catch { return; }
      if (version !== imageVersion || disposed) return;
      const source = active.currentSrc || active.src;
      if (textureSource !== source) {
        // A separate image keeps srcset density correction out of GPU texture sizing.
        let loaded;
        try { loaded = await textureLoader.loadAsync(source); }
        catch {
          if (version === imageVersion && !disposed) { stop?.(); hero.dataset.depthState = "fallback"; }
          return;
        }
        if (version !== imageVersion || disposed) { loaded.dispose(); return; }
        texture?.dispose();
        texture = loaded;
        textureSource = source;
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
        material.map = texture;
        material.needsUpdate = true;
      }
      image = active;
      geometry();
    }
    function visibility() { if (document.hidden) pause(); else wake(); }
    function contextLost(event) {
      event.preventDefault();
      lost = true;
      pause();
      hero.classList.remove("has-depth");
      hero.dataset.depthState = "fallback";
    }
    function contextRestored() { lost = false; if (texture) texture.needsUpdate = true; wake(); }
    const resize = new ResizeObserver(refreshImage);
    const intersection = new IntersectionObserver(entries => {
      visible = entries[0].isIntersecting;
      if (visible) wake(); else pause();
    });
    const images = hero.querySelectorAll(".hero-photo img, .mobile-hero-photo img");
    images.forEach(photo => photo.addEventListener("load", refreshImage));
    document.addEventListener("visibilitychange", visibility);
    canvas.addEventListener("webglcontextlost", contextLost);
    canvas.addEventListener("webglcontextrestored", contextRestored);
    resize.observe(hero);
    intersection.observe(hero);
    stop = () => {
      disposed = true;
      pause();
      resize.disconnect();
      intersection.disconnect();
      images.forEach(photo => photo.removeEventListener("load", refreshImage));
      document.removeEventListener("visibilitychange", visibility);
      canvas.removeEventListener("webglcontextlost", contextLost);
      canvas.removeEventListener("webglcontextrestored", contextRestored);
      texture?.dispose();
      material.dispose();
      mesh.geometry.dispose();
      renderer.dispose();
      canvas.remove();
      hero.classList.remove("has-depth");
      hero.dataset.depthState = "static";
      stop = null;
    };
    await refreshImage();
  } catch {
    if (stop) stop();
    else { renderer?.dispose(); canvas.remove(); }
    hero?.classList.remove("has-depth");
    if (hero) hero.dataset.depthState = "fallback";
  } finally { starting = false; }
}

reducedMotion.addEventListener("change", () => {
  if (reducedMotion.matches) stop?.();
  else start();
});
window.addEventListener("pagehide", event => { if (!event.persisted) stop?.(); });
start();
