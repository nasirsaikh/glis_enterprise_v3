const {test, before, after} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {chromium} = require("playwright");

let browser;
before(async () => { browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined, args: ["--no-sandbox"]}); });
after(async () => { await browser?.close(); });

const css = paths => paths.map(path => fs.readFileSync("static/css/" + path, "utf8")).join("\n");
const portalCSS = css(["bootstrap-layout.css", "portal-polish.css", "ui.css", "portal-compact.css", "style.css"]);
const publicCSS = css(["bootstrap-layout.css", "glis.css", "public-greenline.css", "ui.css", "public-layout.css", "style.css"]);
const bootstrapJS = fs.readFileSync("static/js/bootstrap.bundle.min.js", "utf8");
const mainJS = fs.readFileSync("static/js/main.js", "utf8");
const tableJS = fs.readFileSync("static/js/portal-tables.js", "utf8");
const portalJS = fs.readFileSync("static/js/portal.js", "utf8");
const tpaJS = fs.readFileSync("static/js/tpa.js", "utf8");
const rows = count => Array.from({length: count}, (_, number) => '<tr><td>Record ' + number + '</td><td><input value="Value ' + number + '"></td></tr>').join("");
const visibleRows = page => page.locator("tbody tr:visible").count();

test("TPA member notes stay in a modal and compact rows fit the viewport", async () => {
  const page = await fixture('<body class="glis-portal-app"><div id="portal-main"><div data-workflow-workspace><div class="overflow-x-auto"><table class="table table-sm tpa-processing-table"><tbody><tr><td>Sam Example</td><td><form id="member-form"></form><input class="form-control" form="member-form" value="000123"></td><td><input class="form-control" type="date" value="2026-07-01" form="member-form"></td><td>OMR 100.000</td><td><input class="form-control" value="100.000" form="member-form"></td><td><button type="button" class="btn btn-sm" data-open-dialog="member-notes">Notes</button></td><td><button class="btn btn-sm" form="member-form">Save</button></td></tr></tbody></table></div><div tabindex="-1" aria-hidden="true" id="member-notes" class="modal fade" data-tpa-notes-dialog><div class="modal-dialog modal-dialog-centered modal-dialog-scrollable"><div class="modal-content"><label>Processing notes<textarea form="member-form" name="comments">Existing note</textarea></label><button type="button" data-cancel-tpa-notes>Cancel</button></div></div></div></div></div></body>', portalCSS + css(["tpa-wizard.css"]));
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  try {
    await page.evaluate(() => { window.glisThemeStorage = {get: () => "light", set: () => {}}; });
    await page.addScriptTag({content: portalJS});
    await page.addScriptTag({content: tpaJS});
    assert.equal(await page.locator("table textarea").count(), 0);
    const height = (await page.locator("tr").boundingBox()).height;
    assert.ok(height < 80);
    await page.locator('[data-open-dialog="member-notes"]').click();
    await page.locator("#member-notes.show").waitFor({state:"visible"});
    await page.locator("textarea").fill("Changed note");
    await page.locator("textarea").evaluate(field => { if (field.form?.id !== "member-form") throw new Error("Notes detached from member form"); });
    await page.locator("[data-cancel-tpa-notes]").click();
    assert.equal(await page.locator("textarea").inputValue(), "Existing note");
    for (const width of [1280, 390]) {
      await page.setViewportSize({width, height: 844});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});
async function fixture(body, style = portalCSS, viewport = {width: 1280, height: 900}) {
  const page = await browser.newPage({viewport});
  await page.setContent('<!doctype html><html lang="en" data-theme="light" data-bs-theme="light"><head><style id="bootstrap-css">' + css(["bootstrap.min.css"]) + '</style><style>' + style + '</style></head>' + body + '</html>');
  await page.addScriptTag({content: bootstrapJS});
  await page.addScriptTag({content: mainJS});
  await page.evaluate(() => document.dispatchEvent(new Event("DOMContentLoaded")));
  return page;
}

async function transition(page, selector, event, action) {
  await page.evaluate(({selector,event}) => {
    window.uiTransition = new Promise(resolve => document.querySelector(selector).addEventListener(event,resolve,{once:true}));
  }, {selector,event});
  await action();
  await page.evaluate(() => window.uiTransition);
}

test("Bootstrap dialogs preserve HTMX targets and clean up after workspace replacement", async () => {
  const page = await fixture('<body><main id="workspace" hx-target="#workspace" hx-swap="outerHTML" hx-sync="#workspace:drop" hx-indicator="#busy"><button id="open" class="btn" data-bs-toggle="modal" data-bs-target="#edit">Edit</button><div id="busy"></div><div class="modal fade" id="edit" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body"><h2>Edit row</h2><form><input class="form-control" name="name" value="Sam"><button type="button" class="btn" data-bs-dismiss="modal">Cancel</button></form></div></div></div></div></main></body>');
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  try {
    await transition(page,"#edit","shown.bs.modal",()=>page.locator("#open").click());
    await page.locator("#edit.show").waitFor({state:"visible"});
    assert.equal(await page.locator("#edit").getAttribute("hx-target"), "#workspace");
    assert.equal(await page.locator("#edit").getAttribute("hx-sync"), "#workspace:drop");
    assert.equal(await page.locator(".modal-backdrop").count(), 1);
    await transition(page,"#edit","hidden.bs.modal",()=>page.locator("#edit input").press("Escape"));
    await page.locator(".modal-backdrop").waitFor({state:"detached"});
    assert.equal(await page.locator("#open").evaluate(el => el === document.activeElement), true);
    assert.equal(await page.locator("#workspace #edit").count(), 1, "Closed dialog must remain in the HTMX history snapshot");
    await transition(page,"#edit","shown.bs.modal",()=>page.locator("#open").click());
    await page.locator("#edit input").fill("Updated row");
    await page.evaluate(() => {
      const target = document.getElementById("workspace");
      document.dispatchEvent(new CustomEvent("htmx:beforeSwap", {detail:{target,shouldSwap:true}}));
      target.outerHTML = '<main id="workspace"><p>Updated workspace</p></main>';
      document.dispatchEvent(new CustomEvent("htmx:afterSwap", {detail:{target:document.getElementById("workspace")}}));
    });
    await page.waitForFunction(() => !document.body.classList.contains("modal-open"));
    assert.equal(await page.locator(".modal-backdrop").count(), 0);
    assert.equal(await page.locator("body").evaluate(el => el.classList.contains("modal-open")), false);
    assert.equal(await page.locator("#edit").count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test("Bootstrap dropdowns and member tabs support keyboard use after HTMX replacement", async () => {
  const tabs = '<div class="nav nav-tabs" role="tablist"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#valid" role="tab" aria-selected="true">Validated</button><button class="nav-link" data-bs-toggle="tab" data-bs-target="#errors" role="tab" aria-selected="false">Errors</button></div><div class="tab-content"><section id="valid" class="tab-pane active">Valid row</section><section id="errors" class="tab-pane">Missing date</section></div>';
  const page = await fixture('<body><div class="dropdown"><button class="btn" data-bs-toggle="dropdown" id="menu">Actions</button><ul class="dropdown-menu"><li><a class="dropdown-item" href="#one">First action</a></li><li><a class="dropdown-item" href="#two">Second action</a></li></ul></div><main>'+tabs+'</main></body>');
  try {
    await page.locator("#menu").focus(); await page.locator("#menu").press("ArrowDown");
    assert.equal(await page.getByText("First action").evaluate(el => el === document.activeElement), true);
    await page.keyboard.press("Escape");
    assert.equal(await page.locator(".dropdown-menu").isVisible(), false);
    for (let i=0; i<2; i++) {
      await page.getByRole("tab", {name:"Errors",exact:true}).click();
      assert.equal(await page.locator("#errors").isVisible(), true);
      assert.equal(await page.locator("#valid").isVisible(), false);
      await page.getByRole("tab", {name:"Validated",exact:true}).click();
      assert.equal(await page.locator("#valid").isVisible(), true);
      await page.evaluate(tabs => {
        document.querySelector("main").innerHTML = tabs;
        document.dispatchEvent(new CustomEvent("htmx:afterSwap",{detail:{target:document.querySelector("main")}}));
      }, tabs);
    }
  } finally { await page.close(); }
});

test("Bootstrap offcanvas navigation closes and leaves the mobile page scrollable", async () => {
  const page = await fixture('<body class="glis-portal-app"><div class="glis-shell"><div class="glis-shell-content"><button class="btn" data-bs-toggle="offcanvas" data-bs-target="#portal-navigation">Open navigation</button><main id="portal-main">Workspace</main></div><div class="offcanvas-lg offcanvas-start glis-sidebar-container" id="portal-navigation" tabindex="-1"><aside id="portal-sidebar"><button class="btn" data-bs-dismiss="offcanvas" data-bs-target="#portal-navigation">Close navigation</button><nav><ul class="glis-menu"><li><a href="#tickets">Tickets</a></li></ul></nav></aside></div></div></body>', portalCSS, {width:390,height:844});
  try {
    for (const direction of ["ltr","rtl"]) {
      await page.evaluate(({direction,rtl}) => { document.documentElement.dir=direction; document.getElementById("bootstrap-css").textContent=rtl; },{direction,rtl:css([direction==="rtl"?"bootstrap.rtl.min.css":"bootstrap.min.css"])});
      await transition(page,"#portal-navigation","shown.bs.offcanvas",()=>page.getByRole("button",{name:"Open navigation"}).click());
      await page.locator(".offcanvas-backdrop.show").waitFor({state:"visible"});
      await page.locator("#portal-navigation.show").waitFor({state:"visible"});
      assert.equal(await page.getByRole("link",{name:"Tickets"}).isVisible(),true);
      await transition(page,"#portal-navigation","hidden.bs.offcanvas",()=>page.getByRole("button",{name:"Close navigation"}).click());
      await page.locator(".offcanvas-backdrop").waitFor({state:"detached"});
      assert.equal(await page.locator("body").evaluate(el=>getComputedStyle(el).overflow!=="hidden"),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    }
  } finally { await page.close(); }
});

test("choice labels toggle independent controls and remain usable after HTMX replacement", async () => {
  const options = '<div class="choice-options" id="id_users"><div><label for="id_users_0"><input class="form-check-input" type="checkbox" name="users" value="1" id="id_users_0">First staff member</label></div><div><label for="id_users_1"><input class="form-check-input" type="checkbox" name="users" value="2" id="id_users_1">Second staff member with a long email address</label></div></div>';
  const page = await fixture('<body class="glis-portal-app"><main id="portal-main"><form><fieldset class="glis-field"><legend class="form-label">Users</legend>' + options + '</fieldset><label><input class="form-check-input" name="replace" type="checkbox" checked>Replace current assignment</label></form></main></body>');
  try {
    for (const theme of ["light", "dark"]) {
      for (const direction of ["ltr", "rtl"]) {
        for (const width of [1280, 390]) {
          await page.setViewportSize({width, height: 844});
          await page.evaluate(({theme, direction, options}) => {
            document.documentElement.dataset.theme = theme;
            document.documentElement.dataset.bsTheme = theme;
            document.documentElement.dir = direction;
            document.querySelector(".choice-options").outerHTML = options;
            document.dispatchEvent(new CustomEvent("htmx:load", {detail: {elt: document.querySelector(".choice-options")}}));
          }, {theme, direction, options});
          await page.getByText("First staff member", {exact: true}).click();
          assert.equal(await page.locator("#id_users_0").isChecked(), true);
          assert.equal(await page.locator("#id_users_1").isChecked(), false);
          await page.locator("#id_users_1").focus();
          await page.locator("#id_users_1").press("Space");
          assert.equal(await page.locator("#id_users_1").isChecked(), true);
          assert.deepEqual(await page.evaluate(() => new FormData(document.querySelector("form")).getAll("users")), ["1", "2"]);
          await page.getByText("First staff member", {exact: true}).click();
          assert.equal(await page.locator("#id_users_0").isChecked(), false);
          assert.equal(await page.locator("#id_users_1").isChecked(), true);
          const labels = await page.locator(".choice-options label").evaluateAll(items => items.map(item => ({top: item.getBoundingClientRect().top, bottom: item.getBoundingClientRect().bottom, color: getComputedStyle(item).color})));
          assert.ok(labels[1].top >= labels[0].bottom, "Choice rows overlap");
          assert.equal(labels[0].color, labels[1].color);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        }
      }
    }
    await page.locator('[name="replace"]').uncheck();
    assert.equal(await page.locator('[name="replace"]').isChecked(), false);
  } finally { await page.close(); }
});

test("comment card follows its content height beside a taller sidebar", async () => {
  const page = await fixture('<body class="glis-portal-app"><main id="portal-main"><div class="d-grid gap-3 ticket-layout"><section class="card ticket-conversation"><div class="card-body"><h2>Conversation</h2><p>Short comment text.</p><form><textarea class="form-control">Reply</textarea><button class="btn" type="button">Post comment</button></form></div></section><aside class="card" style="min-height: 1300px">Request details and history</aside></div></main></body>');
  try {
    for (const width of [1440, 390]) {
      await page.setViewportSize({width, height: 900});
      const card = await page.locator(".ticket-conversation").boundingBox();
      const sidebar = await page.locator("aside").boundingBox();
      const content = await page.locator(".ticket-conversation .card-body").boundingBox();
      assert.ok(card.height < sidebar.height / 2);
      assert.ok(card.y + card.height - (content.y + content.height) < 3);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
  } finally { await page.close(); }
});

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
    Array.from({length: 4}, (_, i) => '<label class="glis-field"><span class="form-label">Plan field ' + i + '</span><input class="form-control w-100"></label>').join("") +
    '<label class="plan-active"><input type="checkbox">Active</label><button class="btn btn-primary">Create</button></form></div></div>' +
    '<div class="review-layout"><section class="card"><div class="card-body"><label class="glis-field"><span class="form-label">Subject</span><input id="subject" class="form-control w-100"></label><div class="richtext-editor"><div contenteditable="true">Request details</div></div></div></section><aside class="review-context">Summary</aside></div></main></body>');
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
  const page = await fixture('<body class="glis-portal-app"><button id="vanna-new-session">New chat</button><main id="portal-main"><div id="vanna-workbench" class="vanna-workspace" data-session-detail-template="/sessions/00000000-0000-0000-0000-000000000000/"><section><div id="vanna-conversation" class="glis-flex-fill overflow-y-auto"><div id="vanna-welcome"></div><div id="vanna-history-loading"></div></div><form id="vanna-form" action="https://example.test/ask"><input id="vanna-session" name="session_id"><textarea id="vanna-question"></textarea><button id="vanna-send">Send</button></form><div id="vanna-error"></div></section><div id="vanna-session-list"></div><div id="vanna-diagnostic-log"></div><span id="vanna-diagnostic-count"></span></div></main></body>');
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

const searchableJS = fs.readFileSync('static/js/searchable-selects.js', 'utf8');
const selectCSS = css(['searchable-selects.css']);
const multiselectJS = fs.readFileSync('static/vendor/bootstrap-multiselect/bootstrap-multiselect.bundle.js', 'utf8');
const multiselectCSS = fs.readFileSync('static/vendor/bootstrap-multiselect/bootstrap-multiselect.css', 'utf8');
const dashboardFiltersJS = fs.readFileSync('static/js/dashboard-filters.js', 'utf8');
const ticketLiveJS = fs.readFileSync('static/js/ticket-live.js', 'utf8');

test('repeated HTMX select replacements leave one control for each native select', async () => {
  const page = await multiselectFixture('<body><form><label>Project<select id="project" name="project"><option value="">Choose</option><option value="1">Medical</option></select></label><label>Tag users<select id="users" name="users" multiple><option value="1">Amina</option><option value="2">Sara</option></select></label></form></body>');
  try {
    for (let iteration = 0; iteration < 4; iteration++) {
      await page.evaluate(() => {
        for (const id of ['project', 'users']) {
          const target = document.getElementById(id);
          document.dispatchEvent(new CustomEvent('htmx:beforeSwap', {detail: {target, shouldSwap: true}}));
          target.outerHTML = id === 'project'
            ? '<select id="project" name="project"><option value="">Choose</option><option value="2">Motor</option></select>'
            : '<select id="users" name="users" multiple><option value="1">Amina</option><option value="2">Sara</option></select>';
          document.dispatchEvent(new CustomEvent('htmx:afterSwap', {detail: {target: document.getElementById(id)}}));
        }
      });
      assert.equal(await page.locator('select').count(), 2);
      assert.equal(await page.locator('.glis-select-control').count(), 2);
      assert.equal(await page.locator('.glis-searchable-select').count(), 2);
    }
    await page.getByRole('button', {name: 'Project: Choose'}).click();
    await page.getByRole('option', {name: 'Motor', exact: true}).click();
    await page.getByRole('button', {name: /Tag users:/}).click();
    await page.getByRole('checkbox', {name: 'Amina', exact: true}).check();
    await page.getByRole('checkbox', {name: 'Sara', exact: true}).check();
    assert.deepEqual(await page.evaluate(() => [...new FormData(document.querySelector('form'))]), [['project','2'],['users','1'],['users','2']]);
  } finally { await page.close(); }
});

test('source files accumulate across browse and drop, can be removed and reset', async () => {
  const page = await fixture('<body><form><div data-tpa-dropzone><input type="file" multiple name="documents"><span data-tpa-file-count></span><div data-tpa-file-list></div></div><button type="reset">Reset files</button></form></body>');
  try {
    await page.addScriptTag({content: tpaJS});
    const input = page.locator('input[type=file]');
    await input.setInputFiles({name: 'first.csv', mimeType: 'text/csv', buffer: Buffer.from('first')});
    await input.setInputFiles({name: 'second.pdf', mimeType: 'application/pdf', buffer: Buffer.from('second')});
    await page.locator('[data-tpa-dropzone]').evaluate(zone => {
      const transfer = new DataTransfer(); transfer.items.add(new File(['third'], 'third.png', {type:'image/png', lastModified:1}));
      zone.dispatchEvent(new DragEvent('drop', {bubbles:true, dataTransfer:transfer}));
      zone.dispatchEvent(new DragEvent('drop', {bubbles:true, dataTransfer:transfer}));
    });
    assert.deepEqual(await input.evaluate(field => [...field.files].map(file => file.name)), ['first.csv','second.pdf','third.png']);
    assert.equal(await page.locator('[data-tpa-file-list] button').count(), 3);
    await page.getByRole('button', {name: 'Remove second.pdf'}).click();
    assert.deepEqual(await page.evaluate(() => new FormData(document.querySelector('form')).getAll('documents').map(file => file.name)), ['first.csv','third.png']);
    await page.getByRole('button', {name: 'Reset files'}).click();
    await page.waitForFunction(() => document.querySelector('[data-tpa-file-list]').childElementCount === 0);
    assert.equal(await input.evaluate(field => field.files.length), 0);
    assert.equal(await page.locator('[data-tpa-file-list] button').count(), 0);
  } finally { await page.close(); }
});

test('Parent principal is hidden for the parent and required for a dependent', async () => {
  const page = await fixture('<body><form><select name="relationship"><option value="PRINCIPAL">Parent / Principal</option><option value="CHILD">Child</option></select><fieldset><label>Parent Principal<select name="principal_reference"><option value="">Select</option><option value="1">Existing parent</option></select></label></fieldset></form></body>');
  try {
    await page.addScriptTag({content: tpaJS});
    assert.equal(await page.locator('fieldset').isVisible(), false);
    assert.equal(await page.locator('[name=principal_reference]').evaluate(field => field.required), false);
    await page.locator('[name=relationship]').selectOption('CHILD');
    assert.equal(await page.locator('fieldset').isVisible(), true);
    assert.equal(await page.locator('[name=principal_reference]').evaluate(field => field.required), true);
    await page.locator('[name=principal_reference]').selectOption('1');
    await page.locator('[name=relationship]').selectOption('PRINCIPAL');
    assert.equal(await page.locator('[name=principal_reference]').inputValue(), '');
    assert.equal(await page.locator('fieldset').isVisible(), false);
  } finally { await page.close(); }
});

test('five-row editors expand and analytics formatting submits readable text', async () => {
  const page = await fixture('<body class="glis-portal-app"><main id="portal-main"><form><label for="question">Analytics question</label><textarea id="question" name="question" rows="5" class="richtext-source" data-editor-format="text"></textarea></form></main></body>');
  try {
    await page.evaluate(() => {window.glisThemeStorage = {get: () => 'light', set: () => {}};});
    await page.addScriptTag({content: portalJS});
    await page.evaluate(() => document.dispatchEvent(new Event('DOMContentLoaded')));
    const editor = page.locator('.richtext-canvas');
    const defaultHeight = (await editor.boundingBox()).height;
    assert.ok(defaultHeight >= 140 && defaultHeight <= 180, 'Default editor fits five rows');
    assert.equal(await page.locator('[data-image-button]').count(), 0);
    await editor.fill('Show active policies');
    await editor.evaluate(el => {el.innerHTML = '<b>Show active</b> policies'; el.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.equal(await page.evaluate(() => new FormData(document.querySelector('form')).get('question')), 'Show active policies');
    await page.getByRole('button', {name:'Expand editor'}).click();
    assert.ok((await editor.boundingBox()).height > defaultHeight * 2);
    await page.getByRole('button', {name:'Collapse editor'}).click();
    assert.equal((await editor.boundingBox()).height, defaultHeight);
    await editor.evaluate(el => {el.style.height = '300px';});
    assert.equal((await editor.boundingBox()).height, 300);
  } finally { await page.close(); }
});

test('live changes preserve an unsaved draft and prevent stale submissions', async () => {
  const page = await fixture('<body data-ticket-live data-ticket-reference="TEST-1" data-ticket-revision="4" data-ticket-updates-url="/updates/"><main id="portal-main"><form method="post"><textarea name="body">Original</textarea><input type="file" name="attachment"><button type="submit">Send</button></form></main><footer><form id="logout" method="post" action="/accounts/logout/"><button type="submit">Sign out</button></form></footer></body>');
  try {
    await page.evaluate(() => { window.feedRevision = 4; window.fetch = async () => ({ok:true,status:200,json:async()=>({revision:window.feedRevision})}); });
    await page.addScriptTag({content: ticketLiveJS});
    assert.equal(await page.locator('[name=ticket_revision]').inputValue(), '4');
    await page.locator('textarea').fill('Unsaved draft');
    await page.evaluate(() => {window.feedRevision=5; document.dispatchEvent(new Event('visibilitychange'));});
    await page.getByRole('alert').waitFor();
    assert.equal(await page.locator('textarea').inputValue(), 'Unsaved draft');
    assert.equal(await page.getByRole('button', {name:'Send',exact:true}).isDisabled(), true);
    assert.equal(await page.getByRole('button', {name:'Sign out',exact:true}).isDisabled(), false);
    assert.equal(await page.locator('#logout [name=ticket_revision]').count(), 0);
    assert.equal(await page.locator('#logout').evaluate(form => form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))), true);
    assert.equal(await page.evaluate(() => {
      const event = new Event('submit', {bubbles:true,cancelable:true}); return document.querySelector('form').dispatchEvent(event);
    }), false);
  } finally { await page.close(); }
});

test('own HTMX updates advance the live revision while stale responses preserve the draft', async () => {
  const page = await fixture('<body data-ticket-live data-ticket-reference="TEST-1" data-ticket-revision="4" data-ticket-updates-url="/updates/"><main id="portal-main"><form method="post"><textarea name="body">Original</textarea><button type="submit">Send</button></form></main></body>');
  try {
    await page.evaluate(() => {window.fetch=async()=>({ok:true,status:200,json:async()=>({revision:5})});});
    await page.addScriptTag({content: ticketLiveJS});
    await page.locator('textarea').fill('Own saved comment');
    await page.evaluate(() => {
      const form = document.querySelector('form'), detail = {elt:form,verb:'post',parameters:{}};
      document.dispatchEvent(new CustomEvent('htmx:configRequest',{detail})); window.sentRevision=detail.parameters.ticket_revision;
      document.dispatchEvent(new CustomEvent('htmx:beforeRequest',{detail:{elt:form}}));
      document.dispatchEvent(new CustomEvent('htmx:afterRequest',{detail:{elt:form,successful:true,xhr:{getResponseHeader:key=>key==='X-Ticket-Revision'?'5':null}}}));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    assert.equal(await page.evaluate(() => window.sentRevision), '4');
    assert.equal(await page.locator('[name=ticket_revision]').inputValue(), '5');
    assert.equal(await page.getByRole('alert').count(), 0);
    await page.locator('textarea').fill('Next unsaved comment');
    await page.evaluate(() => document.dispatchEvent(new CustomEvent('htmx:afterRequest',{detail:{elt:document.querySelector('form'),successful:false,xhr:{getResponseHeader:key=>key==='X-Ticket-Stale'?'true':null,responseText:'Reload latest record before submitting.'}}})));
    assert.equal(await page.locator('textarea').inputValue(), 'Next unsaved comment');
    assert.equal(await page.getByRole('button', {name:'Send',exact:true}).isDisabled(), true);
  } finally { await page.close(); }
});

test('live polling survives form replacement and cancelled HTMX requests', async () => {
  const page = await fixture('<body data-ticket-live data-ticket-reference="TEST-1" data-ticket-revision="4" data-ticket-updates-url="/updates/"><main id="portal-main"><form method="post"><textarea name="body">Original</textarea><button type="submit">Send</button></form></main></body>');
  try {
    await page.evaluate(() => {window.feedRevision=5; window.fetch=async()=>({ok:true,status:200,json:async()=>({revision:window.feedRevision})});});
    await page.addScriptTag({content: ticketLiveJS});
    await page.evaluate(() => {
      const form = document.querySelector('form'), xhr={getResponseHeader:key=>key==='X-Ticket-Revision'?'5':null};
      document.dispatchEvent(new CustomEvent('htmx:beforeRequest',{detail:{elt:form,xhr}}));
      form.outerHTML='<form method="post"><textarea name="body">Saved response</textarea><button type="submit">Send</button></form>';
      document.dispatchEvent(new CustomEvent('htmx:afterSwap',{detail:{target:document.querySelector('form')}}));
      document.dispatchEvent(new CustomEvent('htmx:afterRequest',{detail:{elt:form,xhr,successful:true}}));
    });
    assert.equal(await page.locator('[name=ticket_revision]').inputValue(), '5');
    await page.locator('textarea').fill('Preserve new draft');
    await page.evaluate(() => {
      const form=document.querySelector('form');
      const cancelled=new CustomEvent('htmx:beforeRequest',{cancelable:true,detail:{elt:form,xhr:{}}}); cancelled.preventDefault(); document.dispatchEvent(cancelled);
      const xhr={}; document.dispatchEvent(new CustomEvent('htmx:beforeRequest',{detail:{elt:form,xhr}}));
      document.dispatchEvent(new CustomEvent('htmx:sendAbort',{detail:{elt:form,xhr}}));
      window.feedRevision=6; document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.getByRole('alert').waitFor();
    assert.equal(await page.locator('textarea').inputValue(), 'Preserve new draft');
  } finally { await page.close(); }
});

async function multiselectFixture(body, viewport) {
  const page = await fixture(body, portalCSS + multiselectCSS + selectCSS, viewport);
  page.on('pageerror', error => console.error(error.stack));
  await page.addScriptTag({content: multiselectJS});
  await page.addScriptTag({content: dashboardFiltersJS});
  await page.addScriptTag({content: searchableJS});
  return page;
}

test('Bootstrap multiselect searches, selects filtered results and preserves native values and globals', async () => {
  const page = await fixture('<body><form><label>Members<select name="members" multiple data-placeholder="All members"><option value="1">Amina</option><option value="2">Sara</option><option value="3">Sam</option><option value="4" disabled>Sam disabled</option></select></label><button type="reset">Reset</button></form></body>', portalCSS + multiselectCSS + selectCSS);
  const errors=[]; page.on('pageerror', error => errors.push(error.message));
  try {
    await page.addScriptTag({content: multiselectJS});
    await page.evaluate(() => {window.previousJQuery = window.jQuery = window.glisJQuery; window.previousDollar = window.$ = window.glisJQuery; window.changes=0; document.querySelector('select').addEventListener('change',()=>window.changes++);});
    await page.addScriptTag({content: multiselectJS});
    await page.addScriptTag({content: searchableJS});
    assert.equal(await page.evaluate(() => window.jQuery === window.previousJQuery && window.$ === window.previousDollar), true);
    await page.getByRole('button', {name:'Members: All members'}).click();
    await page.getByRole('checkbox', {name:'Amina',exact:true}).check();
    await page.getByRole('searchbox', {name:'Search options'}).fill('sa');
    await page.waitForFunction(() => document.querySelector('.multiselect-option').style.display === 'none');
    await page.getByRole('checkbox', {name:/Select all results/}).check();
    assert.deepEqual(await page.evaluate(()=>new FormData(document.querySelector('form')).getAll('members')), ['1','2','3']);
    assert.equal(await page.getByRole('checkbox', {name:'Sam disabled',exact:true}).isDisabled(), true);
    assert.equal(await page.evaluate(()=>window.changes),2);
    await page.getByRole('searchbox', {name:'Search options'}).press('Escape');
    await page.getByRole('button', {name:'Reset',exact:true}).click();
    await page.getByRole('button', {name:'Members: All members'}).waitFor();
    assert.deepEqual(await page.evaluate(()=>new FormData(document.querySelector('form')).getAll('members')), []);
    assert.deepEqual(errors, []);
  } finally {await page.close();}
});

test('advanced filter mirrors share selections and checkbox menus fit mobile RTL modals', async () => {
  const page=await multiselectFixture('<body class="glis-portal-app"><form id="dashboard-filter-form"><label>Projects<select id="id_project" name="project" multiple data-placeholder="All projects"><option value="1">Medical</option><option value="2">Motor</option></select></label></form><button data-bs-toggle="modal" data-bs-target="#advanced">Advanced</button><div class="modal fade" id="advanced" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body"><label>Projects<div data-filter-mirror="id_project"></div></label><label>Statuses<select name="status" multiple form="dashboard-filter-form"><option value="open">Open</option><option value="closed">Closed</option></select></label></div><div class="modal-footer"><button data-bs-dismiss="modal" type="button">Close</button></div></div></div></div></body>', {width:390,height:844});
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  try {
    await transition(page,'#advanced','shown.bs.modal',()=>page.getByRole('button',{name:'Advanced',exact:true}).click());
    for(const direction of ['ltr','rtl']) {
      await page.evaluate(direction=>{document.documentElement.dir=direction; document.documentElement.dataset.bsTheme='dark';},direction);
      assert.equal(await page.locator('#advanced .multiselect').first().evaluate(button=>getComputedStyle(button).textAlign),'start');
      await page.locator('#advanced .multiselect').first().click();
      const menu=await page.locator('.glis-multiselect-menu.show').boundingBox();
      assert.ok(menu.x >= 0 && menu.x + menu.width <= 391);
      await page.getByRole('checkbox',{name:'Motor',exact:true}).setChecked(direction==='ltr');
      await page.getByRole('searchbox',{name:'Search options'}).press('Escape');
      assert.deepEqual(await page.evaluate(()=>new FormData(document.querySelector('form')).getAll('project')), direction==='ltr'?['2']:[]);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    }
    await page.locator('#advanced .multiselect').last().click();
    await page.getByRole('checkbox',{name:'Open',exact:true}).check();
    assert.deepEqual(await page.evaluate(()=>new FormData(document.querySelector('form')).getAll('status')),['open']);
    await page.getByRole('searchbox',{name:'Search options'}).press('Escape');
    await transition(page,'#advanced','hidden.bs.modal',()=>page.getByRole('button',{name:'Close',exact:true}).click());
    assert.equal(await page.locator('.glis-multiselect-menu.show').count(),0);
    assert.deepEqual(errors,[]);
  } finally {await page.close();}
});

test('Bootstrap multiselect validates required choices and rebuilds after HTMX option and workspace changes',async()=>{
  const page=await multiselectFixture('<body><main><form><label>Approvers<select name="approvers" multiple required><option value="1">First approver</option><option value="2">Second approver</option></select></label><button type="submit">Save</button></form></main></body>');
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try {
    await page.getByRole('button',{name:'Save',exact:true}).click();
    assert.equal(await page.locator('.multiselect').getAttribute('aria-invalid'),'true');
    await page.getByRole('checkbox',{name:'First approver',exact:true}).check();
    assert.equal(await page.locator('form').evaluate(form=>form.checkValidity()),true);
    await page.getByRole('searchbox',{name:'Search options'}).press('Escape');
    await page.evaluate(()=>{const select=document.querySelector('select');select.innerHTML='<option value="3">Replacement approver</option>';document.dispatchEvent(new CustomEvent('htmx:afterSwap',{detail:{target:select}}));});
    await page.locator('.multiselect').click();
    await page.getByRole('checkbox',{name:'Replacement approver',exact:true}).check();
    assert.deepEqual(await page.evaluate(()=>new FormData(document.querySelector('form')).getAll('approvers')),['3']);
    await page.evaluate(()=>{const target=document.querySelector('main');document.dispatchEvent(new CustomEvent('htmx:beforeSwap',{detail:{target}}));target.innerHTML='<select name="other" multiple><option value="x">Other choice</option></select>';document.dispatchEvent(new CustomEvent('htmx:afterSwap',{detail:{target}}));});
    assert.equal(await page.locator('.glis-multiselect-menu.show').count(),0);
    assert.equal(await page.locator('.multiselect').count(),1);
    assert.deepEqual(errors,[]);
  } finally {await page.close();}
});

test('searchable selects preserve values, labels and dependent HTMX changes', async () => {
  const page = await fixture('<body><form><label for="project">Project</label><select class="form-select" id="project" name="project" hx-get="/products"><option value="">All projects</option><option value="medical">Medical approvals</option><option value="motor">Motor claims</option><option value="disabled" disabled>Motor archived</option></select></form></body>', portalCSS + selectCSS);
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  try {
    await page.addScriptTag({content: searchableJS});
    await page.evaluate(() => { window.changeCount = 0; document.querySelector('select').addEventListener('change', () => window.changeCount++); });
    await page.getByRole('button', {name: 'Project: All projects'}).click();
    await page.getByRole('combobox', {name: 'Search options'}).fill('motor');
    assert.equal(await page.getByRole('option').count(), 2);
    await page.getByRole('combobox').press('ArrowDown'); await page.getByRole('combobox').press('Enter');
    assert.equal(await page.locator('select').inputValue(), 'motor');
    assert.equal(await page.evaluate(() => new FormData(document.querySelector('form')).get('project')), 'motor');
    assert.equal(await page.evaluate(() => window.changeCount), 1);
    assert.equal(await page.locator('select').getAttribute('hx-get'), '/products');
    await page.evaluate(() => {
      const select = document.querySelector('select'); select.innerHTML = '<option value="new">New dependent choice</option><option value="other">Other choice</option>';
      document.dispatchEvent(new CustomEvent('htmx:afterSwap', {detail: {target: select}}));
    });
    await page.getByRole('button', {name: 'Project: New dependent choice'}).waitFor();
    await page.getByRole('button', {name: 'Project: New dependent choice'}).click();
    await page.getByRole('combobox').press('Escape');
    assert.equal(await page.locator('.glis-select-menu:visible').count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('searchable multiple choices, disabled controls and reset retain native form behavior', async () => {
  const page = await fixture('<body><form><label>Members<select name="members" multiple><option value="1">Amina</option><option value="2">Nasir</option><option value="3">Sara</option></select></label><label>Unavailable<select name="locked" disabled><option>Locked</option></select></label><button type="reset">Reset</button></form></body>', portalCSS + selectCSS);
  try {
    await page.addScriptTag({content: searchableJS});
    await page.locator('.glis-select-control').first().click();
    await page.getByRole('option', {name: 'Amina', exact: true}).click();
    await page.getByRole('option', {name: 'Sara', exact: true}).click();
    assert.deepEqual(await page.evaluate(() => new FormData(document.querySelector('form')).getAll('members')), ['1','3']);
    assert.equal(await page.locator('.glis-select-control').nth(1).isDisabled(), true);
    await page.getByRole('combobox').press('Escape');
    await page.getByRole('button', {name: 'Reset', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('.glis-select-control').textContent === 'Amina');
    assert.deepEqual(await page.evaluate(() => new FormData(document.querySelector('form')).getAll('members')), []);
  } finally { await page.close(); }
});

test('searchable choices stay inside mobile viewports and modal form submissions', async () => {
  const page = await fixture('<body class="glis-portal-app"><form id="filters"></form><button class="btn" data-bs-toggle="modal" data-bs-target="#filters-modal">Advanced filters</button><div class="modal fade" id="filters-modal" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body"><label>Category<select name="category" form="filters"><option value="">All categories</option><option value="health">Health insurance</option><option value="motor">Motor claims</option></select></label></div><div class="modal-footer"><button data-bs-dismiss="modal" type="button">Close</button></div></div></div></div></body>', portalCSS + selectCSS, {width: 390, height: 844});
  try {
    await page.addScriptTag({content: searchableJS});
    await transition(page, '#filters-modal', 'shown.bs.modal', () => page.getByRole('button', {name: 'Advanced filters'}).click());
    for (const direction of ['ltr','rtl']) {
      await page.evaluate(direction => { document.documentElement.dir = direction; document.documentElement.dataset.bsTheme = 'dark'; }, direction);
      await page.locator('.glis-select-control').click();
      await page.getByRole('combobox').fill('motor');
      const menu = await page.locator('.glis-select-menu:visible').boundingBox();
      assert.ok(menu.x >= 0 && menu.x + menu.width <= 391);
      await page.getByRole('combobox').press('Enter');
      assert.equal(await page.evaluate(() => new FormData(document.querySelector('form')).get('category')), 'motor');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    await transition(page, '#filters-modal', 'hidden.bs.modal', () => page.getByRole('button', {name: 'Close', exact: true}).click());
    assert.equal(await page.locator('.glis-select-menu:visible').count(), 0);
  } finally { await page.close(); }
});

test('required searchable fields remain validatable and HTMX replacement cleans menus', async () => {
  const page = await fixture('<body><main><form><label>Policy<select name="policy" required><option value="">Choose policy</option><option value="1">Policy one</option></select></label><button type="submit">Save</button></form></main></body>', portalCSS + selectCSS);
  try {
    await page.addScriptTag({content: searchableJS});
    await page.getByRole('button', {name: 'Save'}).click();
    assert.equal(await page.locator('.glis-select-control').getAttribute('aria-invalid'), 'true');
    assert.equal(await page.getByRole('combobox').isVisible(), true);
    await page.getByRole('option', {name: 'Policy one', exact: true}).click();
    assert.equal(await page.locator('form').evaluate(form => form.checkValidity()), true);
    await page.locator('.glis-select-control').click();
    await page.evaluate(() => {
      document.dispatchEvent(new CustomEvent('htmx:beforeSwap', {detail: {target: document.querySelector('main')}}));
      document.querySelector('main').innerHTML = '<select name="replacement"><option>Replacement choice</option></select>';
      document.dispatchEvent(new CustomEvent('htmx:afterSwap', {detail: {target: document.querySelector('main')}}));
    });
    assert.equal(await page.locator('.glis-select-menu').count(), 0);
    assert.equal(await page.locator('.glis-select-control').count(), 1);
  } finally { await page.close(); }
});

test('comment editors expand and resize while preserving submitted rich text', async () => {
  const page = await fixture('<body class="glis-portal-app"><main id="portal-main"><section class="ticket-conversation"><form><label for="message">Message</label><textarea id="message" class="richtext-source" name="body"><p>Existing note</p></textarea></form></section></main></body>');
  try {
    await page.evaluate(() => { window.glisThemeStorage = {get: () => 'light', set: () => {}}; });
    await page.addScriptTag({content: portalJS});
    await page.evaluate(() => document.dispatchEvent(new Event('DOMContentLoaded')));
    const editor = page.locator('.richtext-canvas');
    const initial = (await editor.boundingBox()).height;
    await editor.fill('Additional evidence and requested dates');
    const expectedContent = await editor.evaluate(el => el.innerHTML);
    await page.getByRole('button', {name: 'Expand editor', exact: true}).click();
    assert.ok((await editor.boundingBox()).height > initial + 100);
    assert.equal(await page.getByRole('button', {name: 'Collapse editor'}).getAttribute('aria-expanded'), 'true');
    assert.equal(await editor.evaluate(el => getComputedStyle(el).resize), 'vertical');
    await page.getByRole('button', {name: 'Collapse editor'}).click();
    assert.ok(Math.abs((await editor.boundingBox()).height - initial) < 2);
    assert.equal(await page.locator('textarea').inputValue(), expectedContent);
  } finally { await page.close(); }
});

test('all dashboard KPIs stay in one scrollable row without expanding the page', async () => {
  const page = await fixture('<body class="glis-portal-app"><main id="portal-main"><div class="portal-dashboard"><section class="portal-metrics">'+Array.from({length:7}, (_,i)=>'<article class="portal-metric"><strong class="portal-metric__value">'+i+'</strong><span>Metric '+i+'</span></article>').join('')+'</section></div></main></body>');
  try {
    for (const width of [1440, 1280, 390]) {
      await page.setViewportSize({width,height:900});
      const tops = await page.locator('.portal-metric').evaluateAll(items=>items.map(item=>item.getBoundingClientRect().top));
      assert.ok(tops.every(top=>Math.abs(top-tops[0])<2));
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), true);
    }
  } finally { await page.close(); }
});
