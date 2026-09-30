/* Search and paginate complete HTML tables after full and HTMX renders. */
(function () {
  "use strict";
  const instances = new WeakMap();
  let sequence = 0;
  const initialize = table => {
    if (table.dataset.serverPaginated === "true" || instances.has(table) || !table.tBodies.length) return;
    const rows = Array.from(table.tBodies).flatMap(body => Array.from(body.rows));
    if (rows.length <= 20) return;
    const id = table.id || (table.id = "portal-table-" + ++sequence);
    const search = document.createElement("input");
    search.type = "search"; search.className = "input input-bordered input-sm";
    search.placeholder = document.documentElement.lang === "ar" ? "البحث في الجدول" : "Search this table";
    search.setAttribute("aria-label", search.placeholder); search.setAttribute("aria-controls", id);
    const toolbar = document.createElement("div"); toolbar.className = "table-tools";
    const controls = document.createElement("div"); controls.className = "join";
    const previous = document.createElement("button"), next = document.createElement("button");
    previous.type = next.type = "button";
    previous.className = next.className = "btn btn-outline btn-sm";
    previous.textContent = document.documentElement.lang === "ar" ? "السابق" : "Previous";
    next.textContent = document.documentElement.lang === "ar" ? "التالي" : "Next";
    const status = document.createElement("span"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    controls.append(previous, status, next); toolbar.append(search, controls);
    table.before(toolbar);
    const empty = document.createElement("div"); empty.className = "table-search-empty"; empty.hidden = true;
    empty.textContent = document.documentElement.lang === "ar" ? "لا توجد نتائج" : "No matching rows";
    table.after(empty);
    let page = 1, filtered = rows;
    const render = () => {
      const pages = Math.max(1, Math.ceil(filtered.length / 20));
      page = Math.min(Math.max(1, page), pages);
      const shown = new Set(filtered.slice((page - 1) * 20, page * 20));
      rows.forEach(row => { row.hidden = !shown.has(row); });
      previous.disabled = page === 1; next.disabled = page === pages;
      status.textContent = filtered.length ? ((page - 1) * 20 + 1) + "–" + Math.min(page * 20, filtered.length) + " / " + filtered.length : "0 / 0";
      empty.hidden = filtered.length > 0;
    };
    search.addEventListener("input", () => {
      const terms = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      filtered = rows.filter(row => {
        const text = (row.textContent + " " + Array.from(row.querySelectorAll("input,select,textarea")).map(input => input.value).join(" ")).toLocaleLowerCase();
        return terms.every(term => text.includes(term));
      });
      page = 1; render();
    });
    previous.addEventListener("click", () => { page--; render(); });
    next.addEventListener("click", () => { page++; render(); });
    table.addEventListener("invalid", event => {
      const row = event.target.closest("tr");
      if (!row || !rows.includes(row)) return;
      search.value = ""; filtered = rows; page = Math.floor(rows.indexOf(row) / 20) + 1; render();
    }, true);
    instances.set(table, {toolbar, empty, render});
    render();
  };
  const init = context => {
    if (context.matches?.("table")) initialize(context);
    context.querySelectorAll?.("table").forEach(initialize);
  };
  document.addEventListener("DOMContentLoaded", () => init(document));
  document.addEventListener("htmx:load", event => init(event.detail.elt));
  document.addEventListener("glis:tables", () => init(document));
})();
