"use strict";

document.documentElement.classList.add("js");

const menuButton = document.querySelector(".menu-toggle");
const navigation = document.querySelector(".site-nav");
function closeMenu() {
  navigation.classList.remove("is-open");
  menuButton.setAttribute("aria-expanded", "false");
  menuButton.setAttribute("aria-label", menuButton.dataset.openLabel);
}
menuButton.addEventListener("click", () => {
  const open = navigation.classList.toggle("is-open");
  menuButton.setAttribute("aria-expanded", String(open));
  menuButton.setAttribute("aria-label", open ? menuButton.dataset.closeLabel : menuButton.dataset.openLabel);
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && navigation.classList.contains("is-open")) {
    closeMenu();
    menuButton.focus();
  }
});
document.addEventListener("click", event => {
  if (!event.target.closest(".site-header")) closeMenu();
});
window.matchMedia("(min-width: 601px)").addEventListener("change", closeMenu);

const dialog = document.querySelector(".lightbox");
const dataElement = document.getElementById("lightbox-data");
if (dialog && dataElement && typeof dialog.showModal === "function") {
  const photos = JSON.parse(dataElement.textContent);
  const image = dialog.querySelector(".lightbox-image");
  const count = dialog.querySelector(".lightbox-count");
  const caption = dialog.querySelector(".lightbox-caption p");
  const source = dialog.querySelector(".lightbox-caption a");
  const close = dialog.querySelector(".lightbox-close");
  const previous = dialog.querySelector(".lightbox-prev");
  const next = dialog.querySelector(".lightbox-next");
  let index = 0;
  let origin = null;

  function showPhoto(position) {
    index = (position + photos.length) % photos.length;
    const photo = photos[index];
    const save = dialog.querySelector("[data-save-photo]");
    if (save) {
      save.dataset.savePhoto = photo.id;
      document.dispatchEvent(new Event("shortlist:refresh"));
    }
    image.src = photo.url;
    image.alt = photo.alt;
    caption.textContent = photo.caption;
    count.textContent = `${String(index + 1).padStart(2, "0")} / ${String(photos.length).padStart(2, "0")}`;
    source.hidden = !photo.source;
    if (photo.source) source.href = photo.source;
    previous.hidden = next.hidden = photos.length < 2;
  }

  document.querySelectorAll("[data-lightbox-index]").forEach(link => {
    link.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      origin = link;
      showPhoto(Number(link.dataset.lightboxIndex));
      dialog.showModal();
      document.body.classList.add("lightbox-open");
      close.focus();
    });
  });
  close.addEventListener("click", () => dialog.close());
  previous.addEventListener("click", () => showPhoto(index - 1));
  next.addEventListener("click", () => showPhoto(index + 1));
  dialog.addEventListener("keydown", event => {
    if (event.key === "Tab") {
      const controls = Array.from(dialog.querySelectorAll("button, a[href]")).filter(
        element => !element.hidden && element.getClientRects().length > 0
      );
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      showPhoto(index + (event.key === "ArrowRight" ? 1 : -1));
    }
  });
  dialog.addEventListener("close", () => {
    document.body.classList.remove("lightbox-open");
    if (origin) origin.focus({preventScroll: true});
  });
}
