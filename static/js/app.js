(function () {
  "use strict";
  const root = document.documentElement;
  const preferredTheme = () => localStorage.getItem("glis-theme") || "system";
  const resolvedTheme = (choice) => choice === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : choice;
  const applyTheme = (choice) => {
    root.setAttribute("data-bs-theme", resolvedTheme(choice));
    document.dispatchEvent(new CustomEvent("glis:theme", {detail: {theme: resolvedTheme(choice)}}));
  };
  applyTheme(preferredTheme());

  document.addEventListener("alpine:init", () => {
    Alpine.data("siteShell", () => ({
      theme: preferredTheme(),
      get themeIcon() { return resolvedTheme(this.theme) === "dark" ? "bi-sun" : "bi-moon-stars"; },
      toggleTheme() {
        this.theme = resolvedTheme(this.theme) === "dark" ? "light" : "dark";
        localStorage.setItem("glis-theme", this.theme);
        applyTheme(this.theme);
      }
    }));
  });

  const reveal = () => {
    const items = document.querySelectorAll("[data-reveal]");
    if (!items.length) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) {
      items.forEach((item) => item.classList.add("is-visible")); return;
    }
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add("is-visible"); observer.unobserve(entry.target); }
    }), {threshold: .12});
    items.forEach((item) => observer.observe(item));
  };

  const chartLayout = () => {
    const isDark = root.getAttribute("data-bs-theme") === "dark";
    return {
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: {family: "Inter, Cairo, sans-serif", size: 11, color: isDark ? "#dce9e2" : "#4c5c54"},
      margin: {l: 45, r: 18, t: 18, b: 48}, showlegend: false,
      xaxis: {gridcolor: isDark ? "#2d3d34" : "#edf1ef", automargin: true},
      yaxis: {gridcolor: isDark ? "#2d3d34" : "#edf1ef", rangemode: "tozero", automargin: true}
    };
  };
  const plot = (id, traces, layout = {}) => {
    const element = document.getElementById(id);
    if (!element || !window.Plotly) return;
    Plotly.newPlot(element, traces, {...chartLayout(), ...layout}, {displayModeBar: false, responsive: true});
  };
  const labels = (rows, key = "label") => rows.map((row) => String(row[key] || "Unassigned").replaceAll("_", " "));
  const renderCharts = () => {
    const source = document.getElementById("dashboard-data");
    if (!source || !window.Plotly) return;
    const data = JSON.parse(source.textContent);
    const colors = ["#147A50", "#2563EB", "#D99400", "#C2413B", "#7357C7", "#3CA37A", "#6B7280"];
    plot("ticket-status-chart", [{type: "pie", labels: labels(data.status || [], "status"), values: (data.status || []).map(x => x.total), hole: .55, marker: {colors}, textinfo: "label+percent", hovertemplate: "%{label}: %{value}<extra></extra>"}], {margin: {l: 10, r: 10, t: 10, b: 10}});
    plot("ticket-priority-chart", [{type: "pie", labels: labels(data.priority || [], "priority"), values: (data.priority || []).map(x => x.total), hole: .55, marker: {colors: ["#7ACFA5", "#2563EB", "#D99400", "#C2413B"]}, textinfo: "label+percent"}], {margin: {l: 10, r: 10, t: 10, b: 10}});
    plot("ticket-assignee-chart", [{type: "pie", labels: labels(data.assignee || []), values: (data.assignee || []).map(x => x.total), hole: .45, marker: {colors}, textinfo: "label+value"}], {margin: {l: 8, r: 8, t: 8, b: 8}});
    ["category", "product", "project"].forEach((name) => {
      const rows = data[name] || [];
      plot("ticket-" + name + "-chart", [{type: "bar", orientation: "h", y: labels(rows).reverse(), x: rows.map(x => x.total).reverse(), marker: {color: name === "category" ? "#147A50" : name === "product" ? "#2563EB" : "#7357C7", cornerradius: 4}, hovertemplate: "%{y}: %{x}<extra></extra>"}], {margin: {l: 120, r: 20, t: 10, b: 35}});
    });
    const daily = data.daily_open || [];
    plot("ticket-daily-chart", [{type: "scatter", mode: "lines+markers", x: daily.map(x => x.day), y: daily.map(x => x.total), line: {color: "#147A50", width: 3, shape: "spline"}, marker: {size: 7, color: "#147A50"}, fill: "tozeroy", fillcolor: "rgba(20,122,80,.10)", hovertemplate: "%{x}: %{y}<extra></extra>"}]);
  };

  const setupSidebar = () => {
    const button = document.getElementById("sidebar-toggle");
    if (!button) return;
    const modes = ["full", "mini", "hidden"];
    const currentMode = () => modes.find(mode => document.body.classList.contains("sidebar-mode-" + mode)) || "mini";
    const applyMode = (mode) => {
      modes.forEach(value => document.body.classList.toggle("sidebar-mode-" + value, value === mode));
      button.setAttribute("aria-expanded", String(mode === "full"));
      button.dataset.mode = mode;
      button.querySelector("i").className = "bi " + (mode === "full" ? "bi-layout-sidebar-inset-reverse" : mode === "mini" ? "bi-layout-sidebar-inset" : "bi-layout-sidebar");
    };
    applyMode(currentMode());
    button.addEventListener("click", async () => {
      const mode = modes[(modes.indexOf(currentMode()) + 1) % modes.length];
      applyMode(mode);
      const token = document.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
      try {
        await fetch(document.body.dataset.sidebarPreferenceUrl, {
          method: "POST",
          headers: {"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/x-www-form-urlencoded"},
          body: new URLSearchParams({mode})
        });
      } catch (_) { /* The profile form remains a fallback for saving this preference. */ }
    });
  };

  const insertImage = (editor, file) => {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      editor.focus();
      document.execCommand("insertImage", false, reader.result);
      editor.dispatchEvent(new Event("input", {bubbles: true}));
    };
    reader.readAsDataURL(file);
  };
  const setupRichText = (scope = document) => {
    scope.querySelectorAll("textarea.richtext-source:not([data-editor-ready])").forEach((source) => {
      source.dataset.editorReady = "true";
      source.hidden = true;
      const wrapper = document.createElement("div");
      wrapper.className = "richtext-editor";
      wrapper.innerHTML = '<div class="richtext-toolbar"><button type="button" data-cmd="bold" title="Bold"><i class="bi bi-type-bold"></i></button><button type="button" data-cmd="italic" title="Italic"><i class="bi bi-type-italic"></i></button><button type="button" data-cmd="underline" title="Underline"><i class="bi bi-type-underline"></i></button><button type="button" data-cmd="insertUnorderedList" title="Bullets"><i class="bi bi-list-ul"></i></button><button type="button" data-cmd="insertOrderedList" title="Numbered list"><i class="bi bi-list-ol"></i></button><button type="button" data-cmd="createLink" title="Link"><i class="bi bi-link-45deg"></i></button><button type="button" data-image-button title="Upload image"><i class="bi bi-image"></i></button><input type="file" hidden data-image-input accept="image/png,image/jpeg,image/gif,image/webp"><span>Paste or upload images</span></div><div class="richtext-canvas" contenteditable="true"></div>';
      source.insertAdjacentElement("afterend", wrapper);
      const editor = wrapper.querySelector(".richtext-canvas");
      editor.innerHTML = source.value || "";
      const sync = () => { source.value = editor.innerHTML; source.dispatchEvent(new Event("change", {bubbles: true})); };
      editor.addEventListener("input", sync);
      editor.addEventListener("blur", sync);
      editor.addEventListener("paste", (event) => {
        const image = Array.from(event.clipboardData.files || []).find(file => file.type.startsWith("image/"));
        if (image) { event.preventDefault(); insertImage(editor, image); }
      });
      editor.addEventListener("dragover", (event) => event.preventDefault());
      editor.addEventListener("drop", (event) => {
        const image = Array.from(event.dataTransfer.files || []).find(file => file.type.startsWith("image/"));
        if (image) { event.preventDefault(); insertImage(editor, image); }
      });
      wrapper.querySelectorAll("[data-cmd]").forEach((button) => button.addEventListener("click", () => {
        let value = null;
        if (button.dataset.cmd === "createLink") value = window.prompt("Link URL");
        editor.focus(); document.execCommand(button.dataset.cmd, false, value); sync();
      }));
      const imageInput = wrapper.querySelector("[data-image-input]");
      wrapper.querySelector("[data-image-button]").addEventListener("click", () => imageInput.click());
      imageInput.addEventListener("change", () => { if (imageInput.files[0]) insertImage(editor, imageInput.files[0]); imageInput.value = ""; });
      source.form?.addEventListener("submit", sync);
    });
  };

  const setupDropzones = (scope = document) => {
    scope.querySelectorAll("[data-dropzone]:not([data-ready]), .upload-item:not([data-ready])").forEach((zone) => {
      zone.dataset.ready = "true";
      const input = zone.querySelector('input[type="file"]');
      zone.addEventListener("click", (event) => { if (zone.matches("[data-dropzone]") && !event.target.closest("button")) input.click(); });
      ["dragenter", "dragover"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.add("is-dragging"); }));
      ["dragleave", "drop"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.remove("is-dragging"); }));
      zone.addEventListener("drop", event => {
        const transfer = new DataTransfer();
        Array.from(event.dataTransfer.files).forEach(file => transfer.items.add(file));
        input.files = transfer.files;
        zone.querySelector("strong").textContent = transfer.files.length + " file(s) selected";
      });
      input.addEventListener("change", () => { if (input.files.length) zone.querySelector("strong").textContent = input.files.length + " file(s) selected"; });
    });
  };

  const setupVanna = () => {
    const form = document.getElementById("vanna-form");
    if (!form) return;
    const workbench = document.getElementById("vanna-workbench");
    const question = document.getElementById("vanna-question");
    const sessionInput = document.getElementById("vanna-session");
    const conversation = document.getElementById("vanna-conversation");
    const welcome = document.getElementById("vanna-welcome");
    const historyLoading = document.getElementById("vanna-history-loading");
    const error = document.getElementById("vanna-error");
    const send = document.getElementById("vanna-send");
    const sessionList = document.getElementById("vanna-session-list");
    const diagnostics = document.getElementById("vanna-diagnostic-log");
    let chartSequence = 0;

    const bindPrompt = (button) => button.addEventListener("click", () => { question.value = button.dataset.vannaPrompt || button.textContent; question.focus(); });
    document.querySelectorAll("[data-vanna-prompt]").forEach(bindPrompt);
    document.querySelectorAll("[data-auto-submit]").forEach(select => select.addEventListener("change", () => select.form.submit()));

    const scrollToLatest = () => { conversation.scrollTop = conversation.scrollHeight; };
    const formatTime = value => {
      const date = value ? new Date(value) : new Date();
      return Number.isNaN(date.getTime()) ? "" : date.toLocaleString([], {dateStyle: "medium", timeStyle: "short"});
    };
    const addQuestion = (text, createdAt = null) => {
      const article = document.createElement("article");
      article.className = "ai-message ai-message-user";
      const bubble = document.createElement("div");
      bubble.className = "ai-message-bubble";
      bubble.textContent = text;
      const time = document.createElement("time");
      time.textContent = formatTime(createdAt);
      article.append(bubble, time);
      conversation.appendChild(article);
      scrollToLatest();
    };
    const buildTable = rows => {
      const wrapper = document.createElement("div");
      wrapper.className = "table-responsive ai-result-table";
      const table = document.createElement("table");
      table.className = "table portal-table";
      wrapper.appendChild(table);
      if (!rows.length) return wrapper;
      const keys = Object.keys(rows[0]);
      const head = table.createTHead().insertRow();
      keys.forEach(key => { const th = document.createElement("th"); th.textContent = key; head.appendChild(th); });
      const body = table.createTBody();
      rows.forEach(row => { const tr = body.insertRow(); keys.forEach(key => { const td = tr.insertCell(); td.textContent = row[key] ?? ""; }); });
      return wrapper;
    };
    const drawQueryChart = (id, rows, spec) => {
      if (!rows.length || !window.Plotly) return;
      const keys = Object.keys(rows[0]), x = spec.x || keys[0], y = spec.y || keys[1];
      let trace;
      if (spec.type === "pie") trace = {type: "pie", labels: rows.map(row => row[x]), values: rows.map(row => row[y]), hole: .45, textinfo: "label+percent"};
      else if (spec.type === "line") trace = {type: "scatter", mode: "lines+markers", x: rows.map(row => row[x]), y: rows.map(row => row[y]), line: {color: "#147A50", width: 3}, marker: {color: "#147A50", size: 7}};
      else trace = {type: "bar", x: rows.map(row => row[x]), y: rows.map(row => row[y]), marker: {color: "#147A50", cornerradius: 4}};
      plot(id, [trace], {title: {text: spec.title || "", font: {size: 14}}, margin: {l: 44, r: 16, t: spec.title ? 46 : 18, b: 48}});
    };
    const setDiagnostics = queryData => {
      diagnostics.innerHTML = "";
      const timestamp = new Date().toLocaleTimeString([], {hour12: false});
      const events = [
        ["bi-inbox", "Received query request"],
        ["bi-shield-check", "Applied domain and row-access policies"],
        ["bi-database-check", queryData.chroma_memories ? `Retrieved ${queryData.chroma_memories} ChromaDB memories` : "Loaded governed business context"],
      ];
      if (queryData.execution_mode) events.push(["bi-cpu", queryData.execution_mode.replaceAll("_", " ")]);
      if (queryData.status === "completed") {
        events.push(["bi-code-square", "Executed read-only SQL through Vanna RunSqlTool"]);
        events.push(["bi-check2-circle", `Returned ${queryData.row_count || 0} rows in ${queryData.duration_ms || 0}ms`]);
      } else events.push(["bi-exclamation-octagon", queryData.summary || queryData.error_code || "Query failed"]);
      events.forEach(([icon, label]) => {
        const row = document.createElement("div"), time = document.createElement("time"), marker = document.createElement("i"), text = document.createElement("span");
        time.textContent = timestamp; marker.className = "bi " + icon; text.textContent = label; row.append(time, marker, text); diagnostics.appendChild(row);
      });
      document.getElementById("vanna-diagnostic-count").textContent = `${events.length} events`;
    };
    const addAnswer = queryData => {
      const article = document.createElement("article");
      article.className = "ai-message ai-message-assistant" + (queryData.status !== "completed" ? " ai-message-error" : "");
      const card = document.createElement("div");
      card.className = "ai-answer-card";
      const header = document.createElement("header");
      const label = document.createElement("span");
      label.innerHTML = '<i class="bi bi-stars"></i> Vanna';
      const meta = document.createElement("small");
      meta.textContent = queryData.status === "completed" ? `${queryData.row_count || 0} rows · ${queryData.duration_ms || 0} ms` : (queryData.error_code || "Failed");
      header.append(label, meta); card.appendChild(header);
      const summary = document.createElement("p");
      summary.className = "ai-answer-summary";
      summary.textContent = queryData.summary || (queryData.status === "completed" ? "The query completed successfully." : "The query could not be completed.");
      card.appendChild(summary);
      if (queryData.sql) {
        const details = document.createElement("details");
        details.className = "sql-preview";
        const detailsLabel = document.createElement("summary");
        detailsLabel.textContent = "Generated SQL";
        const pre = document.createElement("pre"), code = document.createElement("code");
        code.textContent = queryData.sql; pre.appendChild(code); details.append(detailsLabel, pre); card.appendChild(details);
      }
      const rows = queryData.data || [], spec = queryData.chart || {};
      let chartId = "";
      if (rows.length && spec.type) {
        chartId = `vanna-chart-${queryData.id || ++chartSequence}-${++chartSequence}`;
        const chart = document.createElement("div"); chart.id = chartId; chart.className = "ai-result-chart"; card.appendChild(chart);
      }
      if (rows.length) card.appendChild(buildTable(rows));
      const footer = document.createElement("footer");
      const followups = document.createElement("div"); followups.className = "prompt-chips ai-followups";
      (queryData.followups || []).forEach(text => { const button = document.createElement("button"); button.type = "button"; button.textContent = text; button.dataset.vannaPrompt = text; bindPrompt(button); followups.appendChild(button); });
      footer.appendChild(followups);
      if (queryData.export_url) {
        const link = document.createElement("a"); link.className = "btn btn-sm btn-outline-primary"; link.href = queryData.export_url; link.innerHTML = '<i class="bi bi-download me-1"></i> Export CSV'; footer.appendChild(link);
      }
      if (footer.childElementCount) card.appendChild(footer);
      article.appendChild(card);
      const time = document.createElement("time"); time.textContent = formatTime(queryData.created_at); article.appendChild(time);
      conversation.appendChild(article);
      if (chartId) setTimeout(() => drawQueryChart(chartId, rows, spec), 10);
      setDiagnostics(queryData);
      scrollToLatest();
    };
    const showWelcome = () => {
      conversation.querySelectorAll(".ai-message").forEach(item => item.remove());
      historyLoading.classList.add("d-none"); welcome.classList.remove("d-none");
    };
    const renderHistory = queries => {
      conversation.querySelectorAll(".ai-message").forEach(item => item.remove());
      historyLoading.classList.add("d-none"); welcome.classList.toggle("d-none", Boolean(queries.length));
      queries.forEach(item => { addQuestion(item.question, item.created_at); addAnswer(item); });
      if (queries.length) setDiagnostics(queries[queries.length - 1]);
    };
    const setActiveSession = id => {
      sessionInput.value = id || "";
      sessionList.querySelectorAll("[data-session-id]").forEach(item => item.classList.toggle("active", item.dataset.sessionId === id));
      const url = new URL(window.location.href);
      if (id) url.searchParams.set("session", id); else url.searchParams.delete("session");
      history.replaceState({}, "", url);
    };
    const loadSession = async id => {
      if (!id) { setActiveSession(""); showWelcome(); return; }
      historyLoading.classList.remove("d-none"); welcome.classList.add("d-none"); error.classList.add("d-none");
      try {
        const endpoint = workbench.dataset.sessionDetailTemplate.replace("00000000-0000-0000-0000-000000000000", id);
        const response = await fetch(endpoint, {headers: {"X-Requested-With": "XMLHttpRequest"}});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Conversation could not be loaded.");
        setActiveSession(id); renderHistory(payload.queries || []);
      } catch (exception) {
        historyLoading.classList.add("d-none"); error.textContent = exception.message; error.classList.remove("d-none");
      }
    };
    const upsertSession = session => {
      if (!session) return;
      document.getElementById("vanna-session-empty")?.remove();
      let item = sessionList.querySelector(`[data-session-id="${session.id}"]`);
      if (!item) {
        item = document.createElement("button"); item.type = "button"; item.className = "ai-session-item"; item.dataset.sessionId = session.id;
        item.innerHTML = '<i class="bi bi-chat-left-text"></i><span><strong></strong><small></small></span>';
        sessionList.prepend(item);
      }
      item.querySelector("strong").textContent = session.title;
      item.querySelector("small").textContent = `${session.question_count} questions · just now`;
      setActiveSession(session.id);
    };
    sessionList.addEventListener("click", event => { const item = event.target.closest("[data-session-id]"); if (item) loadSession(item.dataset.sessionId); });
    document.getElementById("vanna-new-session")?.addEventListener("click", () => { setActiveSession(""); showWelcome(); question.focus(); });
    question.addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); } });


    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const text = question.value.trim();
      if (!text || send.disabled) return;

      const formData = new FormData(form);
      formData.set("question", text);

      welcome.classList.add("d-none");
      historyLoading.classList.add("d-none");
      error.classList.add("d-none");
      send.disabled = true;

      addQuestion(text);
      question.value = "";

      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: formData,
          headers: {
            "X-Requested-With": "XMLHttpRequest"
          }
        });

        const payload = await response.json();

        if (payload.session_id) setActiveSession(payload.session_id);
        if (payload.session) upsertSession(payload.session);
        if (payload.query) addAnswer(payload.query);

        if (!response.ok) {
          throw new Error(payload.error || "Analysis failed");
        }
      } catch (exception) {
        error.textContent = exception.message;
        error.classList.remove("d-none");
      } finally {
        send.disabled = false;
        question.focus();
      }
    });    

    if (sessionInput.value) loadSession(sessionInput.value); else showWelcome();
  };

  const setupNotifications = () => {
    const button = document.getElementById("notification-button"), count = document.getElementById("notification-count");
    if (!button || !count) return;
    const browserEnabled = document.body.dataset.browserNotifications === "true";
    button.addEventListener("click", () => {
      if (browserEnabled && "Notification" in window && Notification.permission === "default") Notification.requestPermission();
    });
    const poll = async () => {
      try {
        const response = await fetch("/portal/notifications/feed/", {headers: {"X-Requested-With": "XMLHttpRequest"}});
        if (!response.ok) return;
        const data = await response.json(), previous = Number(count.textContent || 0);
        count.textContent = data.unread; count.classList.toggle("d-none", !data.unread);
        if (browserEnabled && data.unread > previous && "Notification" in window && Notification.permission === "granted" && data.items.length) new Notification(data.items[0].title, {body: data.items[0].body});
      } catch (_) { /* Network interruptions should not affect portal use. */ }
    };
    window.setInterval(poll, 30000);
  };

  const init = (scope = document) => { reveal(); setupRichText(scope); setupDropzones(scope); };
  document.addEventListener("DOMContentLoaded", () => {
    init(); setupSidebar(); setupVanna(); setupNotifications(); setTimeout(renderCharts, 120);
  });
  document.addEventListener("glis:theme", () => setTimeout(renderCharts, 30));
  document.body.addEventListener("htmx:afterSwap", (event) => init(event.detail.target));
  document.body.addEventListener("htmx:afterRequest", (event) => {
    const form = event.detail.elt;
    if (event.detail.successful && form instanceof HTMLFormElement && form.dataset.resetOnSuccess === "true") form.reset();
  });
})();
