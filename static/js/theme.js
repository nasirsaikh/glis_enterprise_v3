/* Apply the saved choice before styles paint on public and portal pages. */
(function () {
  "use strict";
  const choices = new Set(["system", "light", "dark"]);
  const normalize = value => choices.has(value) ? value : "system";
  let stored = "";
  try { stored = localStorage.getItem("glis-theme") || ""; } catch (_) { /* Storage can be unavailable. */ }
  const preference = normalize(stored || document.documentElement.dataset.userTheme || "system");
  let memoryChoice = preference;
  const theme = preference === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : preference;
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.setAttribute("data-bs-theme", theme);
  window.glisThemeStorage = {
    get: () => { try { return localStorage.getItem("glis-theme") || memoryChoice; } catch (_) { return memoryChoice; } },
    set: choice => { memoryChoice = normalize(choice); try { localStorage.setItem("glis-theme", memoryChoice); } catch (_) { /* Keep the current page preference. */ } }
  };
})();
