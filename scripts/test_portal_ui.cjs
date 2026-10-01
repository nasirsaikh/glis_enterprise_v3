const {test, before, after} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {chromium} = require("playwright");

let browser;
before(async () => { browser = await chromium.launch({headless: true}); });
after(async () => { await browser?.close(); });

const css = paths => paths.map(path => fs.readFileSync("static/css/" + path, "utf8")).join("\n");
const portalCSS = css(["output.css", "portal-polish.css", "ui.css", "portal-compact.css"]);
const publicCSS = css(["bootstrap-compat.css", "glis.css", "output.css", "public-greenline.css", "ui.css", "public-layout.css"]);
const tableJS = fs.readFileSync("static/js/portal-tables.js", "utf8");
const portalJS = fs.readFileSync("static/js/portal.js", "utf8");
const tpaJS = fs.readFileSync("static/js/tpa.js", "utf8");
const rows = count => Array.from({length: count}, (_, number) => '<tr><td>Record ' + number + '</td><td><input value="Value ' + number + '"></td></tr>').join("");
const visibleRows = page => page.locator("tbody tr:visible").count();

test("TPA member notes stay in a modal and compact rows fit the viewport", async () => {
  const page = await fixture('<body class="glis-portal-app"><div id="portal-main"><div data-workflow-workspace><div class="overflow-x-auto"><table class="table table-sm tpa-processing-table"><tbody><tr><td>Sam Example</td><td><form id="member-form"></form><input class="input" form="member-form" value="000123"></td><td><input class="input" type="date" value="2026-07-01" form="member-form"></td><td>OMR 100.000</td><td><input class="input" value="100.000" form="member-form"></td><td><button type="button" class="btn btn-sm" data-open-dialog="member-notes">Notes</button></td><td><button class="btn btn-sm" form="member-form">Save</button></td></tr></tbody></table></div><dialog id="member-notes" class="modal" data-tpa-notes-dialog><div class="modal-box"><label>Processing notes<textarea form="member-form" name="comments">Existing note</textarea></label><button type="button" data-cancel-tpa-notes>Cancel</button></div></dialog></div></div></body>', portalCSS + css(["tpa-wizard.css"]));
  try {
    await page.addScriptTag({content: portalJS});
    await page.addScriptTag({content: tpaJS});
    assert.equal(await page.locator("table textarea").count(), 0);
    const height = (await page.locator("tr").boundingBox()).height;
    assert.ok(height < 80);
    await page.locator('[data-open-dialog="member-notes"]').click();
    assert.equal(await page.locator("dialog").evaluate(dialog => dialog.open), true);
    await page.locator("textarea").fill("Changed note");
    await page.locator("textarea").evaluate(field => { if (field.form?.id !== "member-form") throw new Error("Notes detached from member form"); });
    await page.locator("[data-cancel-tpa-notes]").click();
    assert.equal(await page.locator("textarea").inputValue(), "Existing note");
    for (const width of [1280, 390]) {
      await page.setViewportSize({width, height: 844});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
  } finally { await page.close(); }
});
async function fixture(body, style = portalCSS, viewport = {width: 1280, height: 900}) {
  const page = await browser.newPage({viewport});
  await page.setContent('<!doctype html><html lang="en" data-theme="light"><head><style>' + style + '</style></head>' + body + '</html>');
  return page;
}

test("public inner-page CMS grid is centered, responsive and fits viewport", async () => {
  const page = await fixture('<body class="public-shell public-inner-page"><main id="main-content"><div class="container"><div class="row"><article class="col-md-8">Main content</article><aside class="col-md-4">Sidebar</aside></div></div></main></body>', publicCSS);
  try {
    const container = await page.locator(".container").boundingBox();
    const main = await page.locator("article").boundingBox();
    const aside = await page.locator("aside").boundingBox();
    assert.ok(Math.abs(container.width - 1180) < 1);
    assert.ok(Math.abs(container.x - 50) < 1);
    assert.ok(Math.abs(main.width / aside.width - 2) < 0.02);
    assert.ok(Math.abs(main.y - aside.y) < 1);
    await page.setViewportSize({width: 390, height: 844});
    const mobileMain = await page.locator("article").boundingBox();
    const mobileAside = await page.locator("aside").boundingBox();
    assert.ok(Math.abs(mobileMain.width - mobileAside.width) < 1);
    assert.ok(mobileAside.y > mobileMain.y);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  } finally { await page.close(); }
});

test("compact forms, benefit plan row and review editor fit their cards", async () => {
  const page = await fixture('<body class="glis-portal-app"><main id="portal-main"><div class="card"><div class="card-body"><form class="compact-plan-row">' +
    Array.from({length: 4}, (_, i) => '<label class="fieldset"><span class="fieldset-legend">Plan field ' + i + '</span><input class="input input-bordered w-full"></label>').join("") +
    '<label class="plan-active"><input type="checkbox">Active</label><button class="btn btn-primary">Create</button></form></div></div>' +
    '<div class="review-layout"><section class="card"><div class="card-body"><label class="fieldset"><span class="fieldset-legend">Subject</span><input id="subject" class="input w-full"></label><div class="richtext-editor"><div contenteditable="true">Request details</div></div></div></section><aside class="review-context">Summary</aside></div></main></body>');
  try {
    const boxes = await page.locator(".compact-plan-row > *").evaluateAll(items => items.map(item => item.getBoundingClientRect().bottom));
    assert.ok(Math.max(...boxes) - Math.min(...boxes) < 25);
    const subject = await page.locator("#subject").boundingBox();
    const editor = await page.locator(".richtext-editor").boundingBox();
    assert.ok(Math.abs(subject.width - editor.width) < 1);
    assert.ok(subject.height <= 36);
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  } finally { await page.close(); }
});

test("table pager searches all rows, pages by 20, handles empty search and HTMX", async () => {
  const page = await fixture('<body class="glis-portal-app"><table><tbody>' + rows(45) + '</tbody></table></body>');
  try {
    await page.addScriptTag({content: tableJS});
    await page.evaluate(() => document.dispatchEvent(new Event("DOMContentLoaded")));
    assert.equal(await visibleRows(page), 20);
    await page.getByRole("button", {name: "Next", exact: true}).click();
    assert.equal(await visibleRows(page), 20);
    await page.getByRole("button", {name: "Next", exact: true}).click();
    assert.equal(await visibleRows(page), 5);
    await page.getByRole("searchbox").fill("Record 44");
    assert.equal(await visibleRows(page), 1);
    await page.getByRole("searchbox").fill("not present");
    assert.equal(await visibleRows(page), 0);
    assert.equal(await page.locator(".table-search-empty").isVisible(), true);
    await page.getByRole("searchbox").fill("");
    await page.evaluate(() => document.dispatchEvent(new CustomEvent("htmx:load", {detail: {elt: document.body}})));
    assert.equal(await page.locator(".table-tools").count(), 1);
    await page.evaluate(() => document.querySelectorAll("tbody input")[41].dispatchEvent(new Event("invalid", {bubbles: false})));
    assert.equal(await page.locator("tbody tr").nth(41).isVisible(), true);
  } finally { await page.close(); }
});

test("small and server-paginated tables do not receive duplicate controls", async () => {
  const page = await fixture('<body><table><tbody>' + rows(20) + '</tbody></table><table data-server-paginated="true"><tbody>' + rows(25) + '</tbody></table></body>');
  try {
    await page.addScriptTag({content: tableJS});
    await page.evaluate(() => document.dispatchEvent(new Event("DOMContentLoaded")));
    assert.equal(await page.locator(".table-tools").count(), 0);
  } finally { await page.close(); }
});

test("Vanna renders ApexCharts, preserves null values and cleans up charts on new chat", async () => {
  const page = await fixture('<body class="glis-portal-app"><button id="vanna-new-session">New chat</button><main id="portal-main"><div id="vanna-workbench" class="vanna-workspace" data-session-detail-template="/sessions/00000000-0000-0000-0000-000000000000/"><section><div id="vanna-conversation" class="flex-1 overflow-y-auto"><div id="vanna-welcome"></div><div id="vanna-history-loading"></div></div><form id="vanna-form" action="https://example.test/ask"><input id="vanna-session" name="session_id"><textarea id="vanna-question"></textarea><button id="vanna-send">Send</button></form><div id="vanna-error"></div></section><div id="vanna-session-list"></div><div id="vanna-diagnostic-log"></div><span id="vanna-diagnostic-count"></span></div></main></body>');
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  try {
    await page.evaluate(() => {
      window.glisThemeStorage = {get: () => "light", set: () => {}};
      window.chartCalls = [];
      window.ApexCharts = class {
        constructor(element, options) { this.element = element; this.options = options; window.chartCalls.push(this); }
        render() {}
        destroy() { this.destroyed = true; }
      };
      window.fetch = async () => ({ok: true, json: async () => ({query: {id: 1, status: "completed", summary: "Test chart", data: [{month: "Jan", total: 12}, {month: "Feb", total: null}], chart: {type: "line", x: "month", y: "total"}}})});
    });
    await page.addScriptTag({content: portalJS});
    await page.addScriptTag({content: tableJS});
    await page.evaluate(() => document.dispatchEvent(new Event("DOMContentLoaded")));
    await page.locator("#vanna-question").fill("Show monthly totals");
    await page.locator("#vanna-send").click();
    await page.waitForFunction(() => window.chartCalls.length === 1);
    assert.deepEqual(await page.evaluate(() => window.chartCalls[0].options.series[0].data), [12, null]);
    assert.equal(await page.evaluate(() => window.chartCalls[0].options.chart.type), "line");
    assert.equal(await page.locator(".vanna-answer-card").count(), 1);
    await page.locator("#vanna-new-session").click();
    assert.equal(await page.evaluate(() => window.chartCalls[0].destroyed), true);
    assert.equal(await page.locator(".ai-message").count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});
