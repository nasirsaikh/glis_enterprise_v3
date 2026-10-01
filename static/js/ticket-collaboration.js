/* Collaboration forms retain normal POST behavior when HTMX is unavailable. */
(() => {
  function formFor(event) {
    const source = event.detail?.requestConfig?.elt || event.detail?.elt || event.target;
    return source?.closest?.("form[data-ticket-action]");
  }
  document.addEventListener("htmx:beforeRequest", event => {
    const form = formFor(event);
    const error = form?.querySelector("[data-ticket-action-error]");
    if (error) { error.textContent = ""; error.classList.add("hidden"); }
  });
  document.addEventListener("htmx:afterRequest", event => {
    const form = formFor(event);
    if (!form || event.detail.successful) return;
    const error = form.querySelector("[data-ticket-action-error]");
    if (!error) return;
    const response = event.detail.xhr?.responseText || "";
    error.textContent = response.startsWith("<") ? "Unable to complete the request. Refresh and try again." : response;
    error.classList.remove("hidden");
  });
})();
