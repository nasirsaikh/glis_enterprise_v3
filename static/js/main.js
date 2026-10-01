/* GLIS Bootstrap behavior, adapted from the Course Planner main.js v1.97.
 * Preserve GLIS's CSRF, navigation, theme, processing and HTMX contracts.
 */
(() => {
  "use strict";
  const movedModals = new Map();
  const closingModals = new Set();
  const resolve = value => typeof value === "string" ? document.getElementById(value.replace(/^#/, "")) : value;
  const text = (en, ar) => document.documentElement.lang === "ar" ? ar : en;

  function prepareModal(modal) {
    if (!modal || !window.bootstrap) return null;
    if (!modal.getAttribute("aria-labelledby") && !modal.getAttribute("aria-label")) {
      const heading = modal.querySelector("h1,h2,h3,h4,h5");
      if (heading) { heading.id ||= `${modal.id}-title`; modal.setAttribute("aria-labelledby", heading.id); }
    }
    // Fixed dialogs sit above transformed cards. A placeholder keeps them part
    // of their original HTMX workspace for replacement and backdrop cleanup.
    if (modal.parentElement !== document.body && !movedModals.has(modal)) {
      const slot = document.createComment("Bootstrap modal position");
      for (const attribute of ["hx-target", "hx-swap", "hx-encoding", "hx-push-url", "hx-sync", "hx-indicator"]) {
        if (modal.hasAttribute(attribute)) continue;
        const parent = modal.closest(`[${attribute}]`);
        if (!parent) continue;
        let value = parent.getAttribute(attribute);
        if (attribute === "hx-target" && value === "this") {
          parent.id ||= `${modal.id}-workspace`; value = `#${parent.id}`;
        }
        modal.setAttribute(attribute, value);
      }
      modal.before(slot); movedModals.set(modal, slot); document.body.append(modal);
    }
    return bootstrap.Modal.getOrCreateInstance(modal);
  }
  function openModal(value) {
    const modal = resolve(value);
    if (!modal) return;
    if (closingModals.size) {
      Promise.all([...closingModals]).then(() => openModal(modal));
      return;
    }
    const current = document.querySelector(".modal.show");
    if (current && current !== modal) {
      current.addEventListener("hidden.bs.modal", () => prepareModal(modal)?.show(), {once:true});
      bootstrap.Modal.getInstance(current)?.hide();
    } else prepareModal(modal)?.show();
  }
  function closeModal(value) {
    const modal = resolve(value);
    if (modal) bootstrap.Modal.getInstance(modal)?.hide();
  }
  window.glisUI = {openModal, closeModal};

  function restoreModals(target) {
    if (!target?.contains) return;
    for (const [modal, slot] of movedModals) {
      if (!target.contains(slot)) continue;
      const instance = bootstrap.Modal.getInstance(modal);
      const state = modal.dataset.glisModalState;
      if (instance && state && state !== "closed") {
        let complete;
        const closing = new Promise(resolve => { complete = resolve; });
        closingModals.add(closing);
        modal.addEventListener("hidden.bs.modal", () => {
          instance.dispose(); closingModals.delete(closing); complete();
        }, {once:true});
        const hide = () => { modal.classList.remove("fade"); instance.hide(); };
        // Let Bootstrap finish an opening transition before asking it to hide.
        // Keep the instance alive until its backdrop and scroll lock are gone.
        if (state === "opening") modal.addEventListener("shown.bs.modal", hide, {once:true});
        else if (state === "open") hide();
      } else instance?.dispose();
      slot.replaceWith(modal); movedModals.delete(modal);
    }
  }
  function init(scope = document) {
    if (!window.bootstrap) return;
    scope.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => bootstrap.Tooltip.getOrCreateInstance(el));
    scope.querySelectorAll('.dropdown.glis-dropdown-end > .dropdown-menu').forEach(el => el.classList.add("dropdown-menu-end"));
    scope.querySelectorAll("details.glis-disclosure:not([data-disclosure-ready])").forEach(el => {
      el.dataset.disclosureReady = "true";
      const sync = () => {
        el.querySelector("summary")?.classList.toggle("collapsed", !el.open);
        el.querySelector("summary")?.setAttribute("aria-expanded", String(el.open));
      };
      el.addEventListener("toggle", sync); sync();
    });
    scope.querySelectorAll(".glis-flash-stack .alert:not([data-flash-ready])").forEach(el => {
      el.dataset.flashReady = "true"; el.classList.add("alert-dismissible", "fade", "show");
      const close = document.createElement("button"); close.type = "button"; close.className = "btn-close";
      close.setAttribute("data-bs-dismiss", "alert"); close.setAttribute("aria-label", text("Close", "إغلاق")); el.append(close);
      setTimeout(() => { if (el.isConnected) bootstrap.Alert.getOrCreateInstance(el).close(); }, 5000);
    });
  }
  // Prepare declarative modals before Bootstrap's delegated click handler runs.
  document.addEventListener("click", event => {
    const trigger = event.target.closest('[data-bs-toggle="modal"]');
    if (trigger) {
      const selector = trigger.getAttribute("data-bs-target") || trigger.getAttribute("href");
      if (selector?.startsWith("#")) {
        if (closingModals.size) {
          event.preventDefault(); event.stopPropagation(); openModal(resolve(selector));
        } else prepareModal(resolve(selector));
      }
    }
  }, true);
  for (const [event, state] of [["show.bs.modal","opening"],["shown.bs.modal","open"],["hide.bs.modal","closing"],["hidden.bs.modal","closed"]]) {
    document.addEventListener(event, event => { event.target.dataset.glisModalState = state; });
  }
  document.addEventListener("shown.bs.modal", event => {
    event.target.querySelector("[autofocus], [data-form-errors], input:not([type=hidden]), textarea, select, button")?.focus({preventScroll:true});
  });
  document.addEventListener("hidden.bs.modal", event => {
    const slot = movedModals.get(event.target);
    if (slot?.isConnected) {
      slot.replaceWith(event.target); movedModals.delete(event.target);
    }
  });
  document.addEventListener("htmx:beforeHistorySave", event => restoreModals(event.detail.historyElt || document.body));
  document.addEventListener("htmx:beforeSwap", event => { if (event.detail.shouldSwap) restoreModals(event.detail.target); });
  document.addEventListener("htmx:beforeCleanupElement", event => restoreModals(event.detail.elt));
  document.addEventListener("htmx:afterSwap", event => {
    const target = event.detail.target;
    init(target?.isConnected ? target : document.getElementById(target?.id) || document);
  });
  document.addEventListener("htmx:historyRestore", () => init());
  document.addEventListener("DOMContentLoaded", () => init());

  // Safe Bootstrap toast API: messages are text, never HTML.
  window.showToast = (message, type = "info", duration = 4000) => {
    let container = document.getElementById("glis-toast-container");
    if (!container) {
      container = document.createElement("div"); container.id = "glis-toast-container";
      container.className = "toast-container position-fixed top-0 end-0 p-3";
      container.setAttribute("aria-live", "polite"); document.body.append(container);
    }
    const toast = document.createElement("div"); toast.className = "toast"; toast.setAttribute("role", "status");
    const body = document.createElement("div"); body.className = "toast-body d-flex align-items-center gap-2";
    const icon = document.createElement("i");
    const variant = {error:"danger", danger:"danger", success:"success", warning:"warning", info:"info"}[type] || "info";
    icon.className = `bi bi-info-circle text-${variant}`;
    const content = document.createElement("span"); content.className = "flex-grow-1"; content.textContent = String(message);
    const close = document.createElement("button"); close.type = "button"; close.className = "btn-close";
    close.setAttribute("data-bs-dismiss", "toast"); close.setAttribute("aria-label", text("Close", "إغلاق"));
    body.append(icon, content, close); toast.append(body); container.append(toast);
    toast.addEventListener("hidden.bs.toast", () => toast.remove(), {once:true});
    bootstrap.Toast.getOrCreateInstance(toast, {delay:duration}).show();
  };
})();
