"use strict";
(() => {
  const camera = document.querySelector("[data-pixel-camera]");
  const backdrop = document.querySelector("[data-pixel-camera-backdrop]");
  if (!camera || !backdrop || camera.dataset.initialized) return;
  camera.dataset.initialized = "true";
  const pendingKey = "mrsaintj.camera.pending.v1";
  const flashKey = "mrsaintj.camera.flash.v1";
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const publicPath = /^\/(en|fr)\/(?:|(?:work|about|contact|privacy|shortlist)\/|(?:stories|services)\/(?:[a-z0-9-]+\/)?|photos\/[a-f0-9-]{36}\/)$/;
  let cleanup;
  let activationTimer;
  let pendingActivation;

  function reset() {
    clearTimeout(cleanup);
    camera.classList.remove("is-playing");
    camera.hidden = true;
    backdrop.classList.remove("is-playing");
    backdrop.hidden = true;
  }

  function normalized(url) { return url.pathname + url.search; }

  function discardPendingNavigation() {
    clearTimeout(activationTimer);
    pendingActivation = null;
    try { sessionStorage.removeItem(pendingKey); } catch { /* Optional decoration. */ }
  }

  function commitPendingNavigation() {
    clearTimeout(activationTimer);
    const activation = pendingActivation;
    pendingActivation = null;
    if (!activation || activation.event.defaultPrevented) return;
    try {
      sessionStorage.setItem(pendingKey, JSON.stringify({destination: activation.destination, createdAt: activation.createdAt}));
    } catch { /* Optional decoration. */ }
  }

  function cooldownElapsed(now) {
    const raw = sessionStorage.getItem(flashKey);
    const last = raw === null ? 0 : Number(raw);
    return Number.isFinite(last) && last >= 0 && now - last >= 1000;
  }

  function blocked() {
    return !!document.querySelector('dialog[open], .menu-toggle[aria-expanded="true"]');
  }

  function consumePendingNavigation() {
    let record;
    try {
      const raw = sessionStorage.getItem(pendingKey);
      sessionStorage.removeItem(pendingKey);
      if (!raw) return false;
      record = JSON.parse(raw);
    } catch { return false; }
    const now = Date.now();
    if (!record || typeof record.destination !== "string" || !Number.isFinite(record.createdAt)
        || now - record.createdAt < 0 || now - record.createdAt > 15000
        || record.destination !== normalized(location) || !publicPath.test(location.pathname)) return false;
    const navigation = performance.getEntriesByType("navigation")[0];
    return !navigation || navigation.type === "navigate";
  }

  function play() {
    if (motion.matches || document.visibilityState !== "visible"
        || getComputedStyle(camera).position !== "fixed" || getComputedStyle(backdrop).position !== "fixed") return;
    try {
      if (!cooldownElapsed(Date.now())) return;
      // Check write access without reserving a flash that might be cancelled.
      sessionStorage.setItem(flashKey, sessionStorage.getItem(flashKey) ?? "0");
    } catch { return; }
    camera.hidden = false;
    backdrop.hidden = false;
    if (blocked()) { reset(); return; }
    camera.classList.add("is-playing");
    backdrop.classList.add("is-playing");
    cleanup = setTimeout(reset, 600);
  }

  function isEligibleLink(event) {
    const link = event.target.closest?.("a[data-camera-transition]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey
        || link.hasAttribute("download") || (link.target && link.target !== "_self")
        || link.closest("[data-lightbox-index], form, .gallery-filters, .pagination")
        || motion.matches || document.visibilityState !== "visible") return null;
    let url;
    try { url = new URL(link.href, location.href); } catch { return null; }
    if (url.origin !== location.origin || !publicPath.test(url.pathname)
        || url.hash || url.pathname === location.pathname) return null;
    return url;
  }

  window.addEventListener("click", event => {
    reset();
    discardPendingNavigation();
    const url = isEligibleLink(event);
    if (!url) return;
    // Finish click dispatch before checking cancellation; native navigation never waits.
    pendingActivation = {event, destination: normalized(url), createdAt: Date.now()};
    activationTimer = setTimeout(commitPendingNavigation, 0);
  });
  document.addEventListener("submit", () => {
    reset();
    discardPendingNavigation();
  });
  camera.addEventListener("animationstart", event => {
    if (event.animationName !== "pixel-camera-flash" || camera.hidden) return;
    try {
      const now = Date.now();
      if (motion.matches || document.hidden || !cooldownElapsed(now)) { reset(); return; }
      sessionStorage.setItem(flashKey, String(now));
    } catch { reset(); }
  });
  camera.addEventListener("animationend", event => { if (event.target === camera) reset(); });
  motion.addEventListener("change", reset);
  document.addEventListener("visibilitychange", () => { if (document.hidden) reset(); });
  window.addEventListener("pagehide", () => { commitPendingNavigation(); reset(); });
  window.addEventListener("resize", reset);
  document.addEventListener("scroll", reset, {passive: true});
  document.addEventListener("focusin", reset);
  window.addEventListener("pageshow", event => {
    if (event.persisted) { reset(); discardPendingNavigation(); }
  });
  new MutationObserver(() => {
    if (!camera.hidden && blocked()) reset();
  }).observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ["open", "aria-expanded"]});
  if (consumePendingNavigation()) play();
})();
