"use strict";

(() => {
  const key = "mrsaintj.shortlist.v1";
  const idPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const body = document.body;
  const status = document.querySelector("[data-shortlist-status]");
  const field = document.getElementById("id_selected_photos");
  let ids = [];
  let available = true;
  let generation = 0;

  function decode(value) {
    const parsed = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? [...new Set(parsed.filter(id => typeof id === "string" && idPattern.test(id)).map(id => id.toLowerCase()))].slice(0, 12) : [];
  }
  function announce(message) {
    status.textContent = message;
    status.hidden = !message;
  }
  try {
    ids = decode(localStorage.getItem(key));
    localStorage.setItem(key, JSON.stringify(ids));
  } catch {
    try { localStorage.removeItem(key); } catch { available = false; }
  }
  if (field && field.value && field.value !== "[]") {
    try { ids = decode(field.value); } catch { ids = []; }
  }

  function save() {
    try { localStorage.setItem(key, JSON.stringify(ids)); }
    catch { available = false; announce(body.dataset.shortlistError); }
  }
  function refresh() {
    document.querySelectorAll("[data-save-photo]").forEach(button => {
      const selected = ids.includes(button.dataset.savePhoto);
      const label = selected ? body.dataset.removeLabel : body.dataset.saveLabel;
      button.setAttribute("aria-pressed", String(selected));
      button.setAttribute("aria-label", label);
      button.title = label;
      button.disabled = !available;
    });
    document.querySelectorAll("[data-shortlist-count]").forEach(element => { element.textContent = String(ids.length); });
    document.querySelectorAll("[data-shortlist-inquiry]").forEach(element => { element.hidden = ids.length === 0; });
    document.querySelectorAll("[data-shortlist-clear]").forEach(element => { element.disabled = ids.length === 0; });
    if (field) field.value = JSON.stringify(ids);
    const preview = document.querySelector("[data-inquiry-selection]");
    if (preview) preview.hidden = ids.length === 0;
  }
  function removeButton(id) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "icon-button save-photo";
    button.dataset.savePhoto = id;
    const icon = document.createElement("img");
    icon.src = body.dataset.removeIcon;
    icon.width = icon.height = 20;
    icon.alt = "";
    button.append(icon);
    return button;
  }
  function render(photos) {
    document.querySelectorAll("[data-shortlist-root]").forEach(root => {
      const focused = root.contains(document.activeElement);
      const focusedId = focused ? document.activeElement.dataset.savePhoto : "";
      root.replaceChildren();
      if (!photos.length) {
        const empty = document.createElement("p");
        empty.className = "empty-state";
        empty.textContent = root.dataset.empty;
        root.append(empty);
      }
      photos.forEach(photo => {
        const figure = document.createElement("figure");
        figure.className = "photo-item";
        const link = document.createElement("a");
        link.href = photo.href;
        const image = document.createElement("img");
        Object.assign(image, {src: photo.src, alt: photo.alt, width: photo.width, height: photo.height, loading: "lazy"});
        link.append(image);
        const caption = document.createElement("figcaption");
        const title = document.createElement("span");
        title.textContent = photo.title;
        caption.append(title, removeButton(photo.id));
        figure.append(link, caption);
        root.append(figure);
      });
      if (focused) {
        const next = Array.from(root.querySelectorAll("[data-save-photo]")).find(button => button.dataset.savePhoto === focusedId)
          || root.querySelector("[data-save-photo]") || document.querySelector("[data-shortlist-clear]");
        if (next && !next.disabled) next.focus();
        else { root.tabIndex = -1; root.focus(); }
      }
    });
    refresh();
  }
  async function validate() {
    const current = ++generation;
    if (!ids.length) { render([]); return; }
    try {
      const url = new URL(body.dataset.shortlistEndpoint, location.origin);
      url.searchParams.set("ids", ids.join(","));
      const response = await fetch(url, {headers: {Accept: "application/json"}, cache: "no-store"});
      if (!response.ok) throw new Error("Selection unavailable");
      const result = await response.json();
      if (current !== generation) return;
      ids = result.photos.map(photo => photo.id);
      save();
      render(result.photos);
    } catch {
      if (current === generation) announce(body.dataset.shortlistError);
    }
  }
  document.addEventListener("click", event => {
    const button = event.target.closest("[data-save-photo]");
    const clear = event.target.closest("[data-shortlist-clear]");
    if (!button && !clear) return;
    if (button) {
      const id = button.dataset.savePhoto;
      if (!idPattern.test(id) || !available) return;
      if (ids.includes(id)) ids = ids.filter(item => item !== id);
      else if (ids.length < 12) ids.push(id);
      else { announce(body.dataset.shortlistLimit); return; }
    } else ids = [];
    announce("");
    save();
    refresh();
    validate();
  });
  document.addEventListener("shortlist:refresh", refresh);
  window.addEventListener("storage", event => {
    if (event.key !== key && event.key !== null) return;
    try { ids = decode(localStorage.getItem(key)); } catch { ids = []; }
    refresh();
    validate();
  });
  refresh();
  validate();
})();
