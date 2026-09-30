(function () {
  "use strict";
  const root = document.documentElement;
  const THEME_CHOICES = new Set(["system", "light", "dark"]);
  const normalizeTheme = (choice) => THEME_CHOICES.has(choice) ? choice : "system";
  const userTheme = () => normalizeTheme(document.body?.dataset.userTheme || "system");
  const preferredTheme = () => normalizeTheme(window.glisThemeStorage.get() || userTheme());
  const resolvedTheme = (choice) => normalizeTheme(choice) === "system"
    ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : normalizeTheme(choice);
  const applyTheme = (choice) => {
    const normalized = normalizeTheme(choice);
    const resolved = resolvedTheme(normalized);
    root.setAttribute("data-theme", resolved);
    root.setAttribute("data-bs-theme", resolved);
    document.querySelectorAll("[data-theme-select]").forEach((select) => { select.value = normalized; });
    document.querySelectorAll("[data-theme-icon]").forEach((icon) => {
      icon.classList.remove("bi-sun", "bi-moon-stars");
      icon.classList.add(resolved === "dark" ? "bi-sun" : "bi-moon-stars");
    });
    document.dispatchEvent(new CustomEvent("glis:theme", {detail: {theme: resolved}}));
  };
  const saveThemeChoice = async (choice) => {
    const endpoint = document.body?.dataset.themePreferenceUrl;
    if (!endpoint) return;
    const token = document.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
    try {
      await fetch(endpoint, {
        method: "POST",
        headers: {"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/x-www-form-urlencoded"},
        body: new URLSearchParams({theme: normalizeTheme(choice)})
      });
    } catch (_) { /* Local preference remains active if profile save is unavailable. */ }
  };
  applyTheme(preferredTheme());

  document.addEventListener("alpine:init", () => {
    Alpine.data("siteShell", () => ({
      theme: preferredTheme(),
      get themeIcon() { return resolvedTheme(this.theme) === "dark" ? "bi-sun" : "bi-moon-stars"; },
      toggleTheme() {
        this.theme = resolvedTheme(this.theme) === "dark" ? "light" : "dark";
        window.glisThemeStorage.set(this.theme);
        applyTheme(this.theme);
        saveThemeChoice(this.theme);
      }
    }));
  });

  const setupThemeSelects = (scope = document) => {
    scope.querySelectorAll("[data-theme-select]:not([data-theme-ready])").forEach((select) => {
      select.dataset.themeReady = "true";
      select.value = preferredTheme();
      select.addEventListener("change", async () => {
        const choice = select.value || "system";
        window.glisThemeStorage.set(choice);
        applyTheme(choice);
        await saveThemeChoice(choice);
      });
    });
  };

  const setupMultiSelectFilters = (scope = document) => {
    scope.querySelectorAll("[data-multiselect-search]:not([data-multiselect-ready])").forEach((input) => {
      input.dataset.multiselectReady = "true";
      const target = document.getElementById(input.dataset.multiselectSearch || "");
      if (!target) return;
      const filter = () => {
        const query = input.value.trim().toLowerCase();
        target.querySelectorAll("[data-multiselect-option]").forEach((option) => {
          const haystack = (option.dataset.searchText || option.textContent || "").toLowerCase();
          option.classList.toggle("hidden", Boolean(query) && !haystack.includes(query));
        });
      };
      input.addEventListener("input", filter);
    });
  };

  const setupParallaxScenes = (scope = document) => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    scope.querySelectorAll("[data-parallax-scene]:not([data-parallax-ready])").forEach((scene) => {
      scene.dataset.parallaxReady = "true";
      const layers = Array.from(scene.querySelectorAll("[data-depth]")).filter(layer => !layer.hasAttribute("data-tilt"));
      if (!layers.length) return;
      scene.addEventListener("pointermove", (event) => {
        if (window.innerWidth < 768) return;
        const rect = scene.getBoundingClientRect();
        const nx = ((event.clientX - rect.left) / Math.max(rect.width, 1)) - .5;
        const ny = ((event.clientY - rect.top) / Math.max(rect.height, 1)) - .5;
        layers.forEach((layer) => {
          const depth = Math.max(1, Number(layer.dataset.depth || 1));
          layer.style.setProperty("--glis-parallax-x", (nx * depth * 7).toFixed(2) + "px");
          layer.style.setProperty("--glis-parallax-y", (ny * depth * 6).toFixed(2) + "px");
        });
      });
      scene.addEventListener("pointerleave", () => layers.forEach((layer) => {
        layer.style.setProperty("--glis-parallax-x", "0px");
        layer.style.setProperty("--glis-parallax-y", "0px");
      }));
    });
  };

  const setupThemeToggles = (scope = document) => {
    scope.querySelectorAll("[data-theme-toggle]:not([data-theme-toggle-ready])").forEach((button) => {
      button.dataset.themeToggleReady = "true";
      button.addEventListener("click", async () => {
        const choice = resolvedTheme(preferredTheme()) === "dark" ? "light" : "dark";
        window.glisThemeStorage.set(choice);
        applyTheme(choice);
        await saveThemeChoice(choice);
      });
    });
  };

  const setupPublicDropdowns = (scope = document) => {
    const details = Array.from(scope.querySelectorAll(".glis-nav-dropdown"));
    details.forEach((item) => {
      if (item.dataset.dropdownReady === "true") return;
      item.dataset.dropdownReady = "true";
      item.addEventListener("toggle", () => {
        if (!item.open) return;
        details.forEach((other) => { if (other !== item) other.open = false; });
      });
      item.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => { item.open = false; }));
    });
  };

  const reveal = (scope = document) => {
    const items = scope.querySelectorAll("[data-reveal]:not(.is-visible)");
    if (!items.length) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) {
      items.forEach((item) => item.classList.add("is-visible")); return;
    }
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add("is-visible"); observer.unobserve(entry.target); }
    }), {threshold: .12, rootMargin: "0px 0px -6% 0px"});
    items.forEach((item) => observer.observe(item));
  };

  const setupAura = (scope = document) => {
    scope.querySelectorAll("[data-aura]:not([data-aura-ready])").forEach((element) => {
      element.dataset.auraReady = "true";
      element.addEventListener("pointermove", (event) => {
        const rect = element.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 100;
        const y = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * 100;
        element.style.setProperty("--aura-x", x.toFixed(1) + "%");
        element.style.setProperty("--aura-y", y.toFixed(1) + "%");
      });
    });
  };

  const setupTilt = (scope = document) => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    scope.querySelectorAll("[data-tilt]:not([data-tilt-ready])").forEach((card) => {
      card.dataset.tiltReady = "true";
      card.classList.add("glis-tilt");
      card.addEventListener("pointermove", (event) => {
        if (window.innerWidth < 768) return;
        const rect = card.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) - .5;
        const y = ((event.clientY - rect.top) / Math.max(rect.height, 1)) - .5;
        card.style.setProperty("--rx", (-y * 7).toFixed(2) + "deg");
        card.style.setProperty("--ry", (x * 9).toFixed(2) + "deg");
      });
      card.addEventListener("pointerleave", () => {
        card.style.setProperty("--rx", "0deg");
        card.style.setProperty("--ry", "0deg");
      });
    });
  };

  const setupRotatingText = (scope = document) => {
    scope.querySelectorAll("[data-rotate-text]:not([data-rotate-ready])").forEach((element) => {
      const words = (element.dataset.rotateText || "").split("|").map(value => value.trim()).filter(Boolean);
      if (!words.length) return;
      element.dataset.rotateReady = "true";
      let index = 0;
      const render = () => {
        element.textContent = words[index % words.length];
        element.classList.remove("glis-rotate-word");
        void element.offsetWidth;
        element.classList.add("glis-rotate-word");
        index += 1;
      };
      render();
      if (!matchMedia("(prefers-reduced-motion: reduce)").matches && words.length > 1) {
        window.setInterval(render, 2600);
      }
    });
  };

  const setupCounters = (scope = document) => {
    scope.querySelectorAll("[data-counter]:not([data-counter-ready])").forEach((element) => {
      element.dataset.counterReady = "true";
      const target = Number(String(element.dataset.counter || "").replace(/,/g, ""));
      if (!Number.isFinite(target) || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const suffix = element.dataset.suffix || "";
      const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        const start = performance.now();
        const duration = 1200;
        const frame = (now) => {
          const progress = Math.min((now - start) / duration, 1);
          const value = target * (1 - Math.pow(1 - progress, 3));
          element.textContent = (Math.abs(target) >= 1000 ? Math.round(value).toLocaleString() : Math.round(value * 10) / 10) + suffix;
          if (progress < 1) requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
      }), {threshold: .35});
      observer.observe(element);
    });
  };

  const setupMobileNav = () => {
    const publicToggle = document.querySelector("[data-public-nav-toggle]");
    const publicNav = document.getElementById("public-mobile-nav");
    if (publicToggle && publicNav) {
      publicToggle.addEventListener("click", () => {
        publicNav.hidden = !publicNav.hidden;
        publicToggle.setAttribute("aria-expanded", String(!publicNav.hidden));
      });
    }
    const dialog = document.getElementById("mobilePortalNav");
    if (!dialog || dialog.dataset.ready === "true") return;
    dialog.dataset.ready = "true";
    document.querySelectorAll("[data-mobile-nav-open]").forEach((button) => button.addEventListener("click", () => dialog.showModal()));
    dialog.querySelectorAll("[data-mobile-nav-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  };

  const chartInstances = new Map();
  const cssColor = (name, fallback) => {
    const value = getComputedStyle(root).getPropertyValue(name).trim();
    return value || fallback;
  };
  const chartTheme = () => root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  const chartColors = () => [
    cssColor("--color-primary", "#147A50"),
    cssColor("--color-info", "#2563EB"),
    cssColor("--color-warning", "#D99400"),
    cssColor("--color-error", "#C2413B"),
    cssColor("--color-secondary", "#7357C7"),
    cssColor("--color-success", "#3CA37A"),
    cssColor("--color-neutral", "#6B7280")
  ];
  const baseChartOptions = (type, height = 300) => ({
    chart: {
      type,
      height,
      background: "transparent",
      foreColor: cssColor("--color-base-content", "#4c5c54"),
      fontFamily: "Inter, Cairo, sans-serif",
      toolbar: {show: false},
      zoom: {enabled: false},
      animations: {enabled: true, speed: 260}
    },
    theme: {mode: chartTheme()},
    grid: {
      borderColor: cssColor("--color-base-300", "#edf1ef"),
      strokeDashArray: 3
    },
    dataLabels: {enabled: false},
    tooltip: {theme: chartTheme()},
    noData: {text: "No data"}
  });
  const apex = (id, options) => {
    const element = document.getElementById(id);
    if (!element || !window.ApexCharts) return;
    const previous = chartInstances.get(id);
    if (previous) previous.destroy();
    const chart = new ApexCharts(element, options);
    chartInstances.set(id, chart);
    chart.render();
  };
  const labels = (rows, key = "label") => rows.map((row) => String(row[key] || "Unassigned").replaceAll("_", " "));
  const renderCharts = () => {
    const source = document.getElementById("dashboard-data");
    if (!source || !window.ApexCharts) return;
    const data = JSON.parse(source.textContent);
    const colors = chartColors();

    const donut = (id, rows, key, donutSize = "62%", customColors = colors) => {
      const options = baseChartOptions("donut", 300);
      Object.assign(options, {
        series: rows.map(row => Number(row.total || 0)),
        labels: labels(rows, key),
        colors: customColors,
        stroke: {width: 2, colors: [cssColor("--color-base-100", "#ffffff")]},
        legend: {position: "bottom", fontSize: "11px"},
        plotOptions: {
          pie: {
            donut: {
              size: donutSize,
              labels: {
                show: true,
                total: {show: true, label: "TOTAL"}
              }
            }
          }
        }
      });
      apex(id, options);
    };

    donut("ticket-status-chart", data.status || [], "status");
    donut("ticket-priority-chart", data.priority || [], "priority", "62%", [
      cssColor("--color-success", "#7ACFA5"),
      cssColor("--color-info", "#2563EB"),
      cssColor("--color-warning", "#D99400"),
      cssColor("--color-error", "#C2413B")
    ]);
    donut("ticket-assignee-chart", data.assignee || [], "label", "55%");

    ["category", "product", "project"].forEach((name, index) => {
      const rows = data[name] || [];
      const options = baseChartOptions("bar", 280);
      Object.assign(options, {
        series: [{name: "Tickets", data: rows.map(row => Number(row.total || 0))}],
        colors: [colors[[0, 1, 4][index]]],
        plotOptions: {bar: {horizontal: true, borderRadius: 4, barHeight: "52%"}},
        xaxis: {categories: labels(rows), forceNiceScale: true},
        legend: {show: false}
      });
      apex("ticket-" + name + "-chart", options);
    });

    const daily = data.daily_open || [];
    const dailyOptions = baseChartOptions("area", 320);
    Object.assign(dailyOptions, {
      series: [{name: "Opened", data: daily.map(row => Number(row.total || 0))}],
      colors: [colors[0]],
      stroke: {curve: "smooth", width: 3},
      fill: {type: "gradient", gradient: {shadeIntensity: .2, opacityFrom: .28, opacityTo: .03}},
      markers: {size: 4, strokeWidth: 0},
      xaxis: {categories: daily.map(row => row.day), labels: {rotate: -35}},
      legend: {show: false}
    });
    apex("ticket-daily-chart", dailyOptions);
  };

  const setupSidebar = () => {
    const button = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("portal-sidebar");
    if (!button || !sidebar) return;

    let desktopMode = "collapsed";

    const render = (mode) => {
      const expanded = mode === "expanded";
      sidebar.dataset.sidebarState = mode;
      sidebar.classList.toggle("w-20", !expanded);
      sidebar.classList.toggle("w-72", expanded);

      sidebar.querySelectorAll("[data-sidebar-label]").forEach((element) => {
        element.classList.toggle("hidden", !expanded);
      });
      sidebar.querySelectorAll("[data-sidebar-link]").forEach((link) => {
        link.classList.toggle("justify-center", !expanded);
      });

      button.setAttribute("aria-expanded", String(expanded));
      button.setAttribute("aria-label", expanded ? "Collapse navigation" : "Expand navigation");
      button.setAttribute("title", expanded ? "Collapse navigation" : "Expand navigation");
      const icon = button.querySelector("i");
      if (icon) icon.className = "bi " + (expanded ? "bi-layout-sidebar-inset-reverse" : "bi-layout-sidebar-inset");
    };

    const syncViewport = () => {
      if (window.matchMedia("(min-width: 1024px)").matches) render(desktopMode);
      else render("expanded");
    };

    // Desktop always lands collapsed; the user can expand it for the current page.
    render("collapsed");
    syncViewport();

    button.addEventListener("click", () => {
      desktopMode = desktopMode === "collapsed" ? "expanded" : "collapsed";
      render(desktopMode);
    });

    window.addEventListener("resize", syncViewport);
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
      wrapper.className = "card overflow-hidden border border-base-300 bg-base-100 shadow-sm";
      wrapper.innerHTML = '<div class="flex flex-wrap items-center gap-1 border-b border-base-300 bg-base-200/55 p-2"><button class="btn btn-ghost btn-sm btn-square" type="button" data-cmd="bold" title="Bold" aria-label="Bold"><i class="bi bi-type-bold"></i></button><button class="btn btn-ghost btn-sm btn-square" type="button" data-cmd="italic" title="Italic" aria-label="Italic"><i class="bi bi-type-italic"></i></button><button class="btn btn-ghost btn-sm btn-square" type="button" data-cmd="underline" title="Underline" aria-label="Underline"><i class="bi bi-type-underline"></i></button><button class="btn btn-ghost btn-sm btn-square" type="button" data-cmd="insertUnorderedList" title="Bullets" aria-label="Bullets"><i class="bi bi-list-ul"></i></button><button class="btn btn-ghost btn-sm btn-square" type="button" data-cmd="insertOrderedList" title="Numbered list" aria-label="Numbered list"><i class="bi bi-list-ol"></i></button><button class="btn btn-ghost btn-sm btn-square" type="button" data-cmd="createLink" title="Link" aria-label="Insert link"><i class="bi bi-link-45deg"></i></button><button class="btn btn-ghost btn-sm btn-square" type="button" data-image-button title="Upload image" aria-label="Upload image"><i class="bi bi-image"></i></button><input type="file" hidden data-image-input accept="image/png,image/jpeg,image/gif,image/webp"><span class="badge badge-ghost badge-sm ms-2">Paste or upload images</span></div><div class="richtext-canvas textarea textarea-bordered w-full rounded-none border-0 bg-base-100 p-4" style="min-height:10rem;overflow:auto" contenteditable="true" role="textbox" aria-multiline="true"></div>';
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
    const currentUserName = document.body.dataset.userName || "You";
    const currentUserInitial = (document.body.dataset.userInitial || currentUserName || "U").trim().charAt(0).toUpperCase() || "U";

    const userAvatar = () => {
      const image = document.createElement("div");
      image.className = "chat-image avatar avatar-placeholder";
      const circle = document.createElement("div");
      circle.className = "w-10 rounded-full bg-primary text-primary-content";
      const initial = document.createElement("span");
      initial.className = "text-sm font-black";
      initial.textContent = currentUserInitial;
      circle.appendChild(initial);
      image.appendChild(circle);
      return image;
    };

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
      article.className = "chat chat-end ai-message";
      const header = document.createElement("div");
      header.className = "chat-header";
      header.textContent = currentUserName;
      const bubble = document.createElement("div");
      bubble.className = "chat-bubble chat-bubble-primary max-w-3xl";
      bubble.textContent = text;
      const footer = document.createElement("div");
      footer.className = "chat-footer opacity-50";
      footer.textContent = formatTime(createdAt);
      article.append(userAvatar(), header, bubble, footer);
      conversation.appendChild(article);
      scrollToLatest();
    };
    const buildTable = rows => {
      const wrapper = document.createElement("div");
      wrapper.className = "mt-3 overflow-x-auto rounded-box bg-base-100 text-base-content";
      const table = document.createElement("table");
      table.className = "table table-zebra ";
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
      article.className = "chat chat-start ai-message";
      const header = document.createElement("div");
      header.className = "chat-header flex items-center gap-2";
      const label = document.createElement("strong");
      label.innerHTML = '<i class="bi bi-stars"></i> Vanna';
      const meta = document.createElement("small");
      meta.className = "opacity-50";
      meta.textContent = queryData.status === "completed" ? `${queryData.row_count || 0} rows · ${queryData.duration_ms || 0} ms` : (queryData.error_code || "Failed");
      header.append(label, meta);

      const bubble = document.createElement("div");
      bubble.className = "chat-bubble max-w-5xl";
      if (queryData.status !== "completed") bubble.classList.add("chat-bubble-error");

      const summary = document.createElement("p");
      summary.className = "leading-6";
      summary.textContent = queryData.summary || (queryData.status === "completed" ? "The query completed successfully." : "The query could not be completed.");
      bubble.appendChild(summary);

      if (queryData.sql) {
        const details = document.createElement("details");
        details.className = "mt-3 rounded-box bg-base-200 p-3 text-base-content";
        const detailsLabel = document.createElement("summary");
        detailsLabel.className = "cursor-pointer font-semibold";
        detailsLabel.textContent = "Generated SQL";
        const pre = document.createElement("pre"), code = document.createElement("code");
        pre.className = "mt-2 overflow-x-auto text-xs";
        code.textContent = queryData.sql;
        pre.appendChild(code); details.append(detailsLabel, pre); bubble.appendChild(details);
      }

      const rows = queryData.data || [], spec = queryData.chart || {};
      let chartId = "";
      if (rows.length && spec.type) {
        chartId = `vanna-chart-${queryData.id || ++chartSequence}-${++chartSequence}`;
        const chart = document.createElement("div");
        chart.id = chartId;
        chart.className = "mt-3 min-h-64 rounded-box bg-base-100";
        bubble.appendChild(chart);
      }
      if (rows.length) bubble.appendChild(buildTable(rows));

      const actions = document.createElement("div");
      actions.className = "mt-3 flex flex-wrap gap-2";
      (queryData.followups || []).forEach(text => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-ghost btn-xs";
        button.textContent = text;
        button.dataset.vannaPrompt = text;
        bindPrompt(button);
        actions.appendChild(button);
      });
      if (queryData.export_url) {
        const link = document.createElement("a");
        link.className = "btn btn-outline btn-sm";
        link.href = queryData.export_url;
        link.innerHTML = '<i class="bi bi-download"></i> Export CSV';
        actions.appendChild(link);
      }
      if (actions.childElementCount) bubble.appendChild(actions);

      const footer = document.createElement("div");
      footer.className = "chat-footer opacity-50";
      footer.textContent = formatTime(queryData.created_at);
      article.append(header, bubble, footer);
      conversation.appendChild(article);
      if (chartId) setTimeout(() => drawQueryChart(chartId, rows, spec), 10);
      setDiagnostics(queryData);
      scrollToLatest();
    };
    const showWelcome = () => {
      conversation.querySelectorAll(".ai-message").forEach(item => item.remove());
      historyLoading.classList.add("hidden"); welcome.classList.remove("hidden");
    };
    const renderHistory = queries => {
      conversation.querySelectorAll(".ai-message").forEach(item => item.remove());
      historyLoading.classList.add("hidden"); welcome.classList.toggle("hidden", Boolean(queries.length));
      queries.forEach(item => { addQuestion(item.question, item.created_at); addAnswer(item); });
      if (queries.length) setDiagnostics(queries[queries.length - 1]);
    };
    const setActiveSession = id => {
      sessionInput.value = id || "";
      sessionList.querySelectorAll("[data-session-id]").forEach(item => item.classList.toggle("btn-active", item.dataset.sessionId === id));
      const url = new URL(window.location.href);
      if (id) url.searchParams.set("session", id); else url.searchParams.delete("session");
      history.replaceState({}, "", url);
    };
    const loadSession = async id => {
      if (!id) { setActiveSession(""); showWelcome(); return; }
      historyLoading.classList.remove("hidden"); welcome.classList.add("hidden"); error.classList.add("hidden");
      try {
        const endpoint = workbench.dataset.sessionDetailTemplate.replace("00000000-0000-0000-0000-000000000000", id);
        const response = await fetch(endpoint, {headers: {"X-Requested-With": "XMLHttpRequest"}});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Conversation could not be loaded.");
        setActiveSession(id); renderHistory(payload.queries || []);
      } catch (exception) {
        historyLoading.classList.add("hidden"); error.textContent = exception.message; error.classList.remove("hidden");
      }
    };
    const upsertSession = session => {
      if (!session) return;
      document.getElementById("vanna-session-empty")?.remove();
      let item = sessionList.querySelector(`[data-session-id="${session.id}"]`);
      if (!item) {
        item = document.createElement("button"); item.type = "button"; item.className = "btn btn-ghost h-auto w-full justify-start gap-3 py-3 text-start"; item.dataset.sessionId = session.id;
        item.innerHTML = '<i class="bi bi-chat-left-text text-primary"></i><span class="min-w-0 flex-1"><strong class="block truncate"></strong><small class="block truncate font-normal opacity-50"></small></span>';
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

      welcome.classList.add("hidden");
      historyLoading.classList.add("hidden");
      error.classList.add("hidden");
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
        error.classList.remove("hidden");
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
        count.textContent = data.unread; count.classList.toggle("hidden", !data.unread);
        if (browserEnabled && data.unread > previous && "Notification" in window && Notification.permission === "granted" && data.items.length) new Notification(data.items[0].title, {body: data.items[0].body});
      } catch (_) { /* Network interruptions should not affect portal use. */ }
    };
    window.setInterval(poll, 30000);
  };

  const init = (scope = document) => {
    reveal(scope);
    setupAura(scope);
    setupTilt(scope);
    setupRotatingText(scope);
    setupCounters(scope);
    setupRichText(scope);
    setupDropzones(scope);
    setupThemeSelects(scope);
    setupThemeToggles(scope);
    setupPublicDropdowns(scope);
    setupMultiSelectFilters(scope);
    setupParallaxScenes(scope);
  };
  document.addEventListener("DOMContentLoaded", () => {
    init(); setupSidebar(); setupMobileNav(); setupVanna(); setupNotifications(); setTimeout(renderCharts, 120);
    const media = matchMedia("(prefers-color-scheme: dark)");
    const syncSystemTheme = () => { if (preferredTheme() === "system") applyTheme("system"); };
    if (media.addEventListener) media.addEventListener("change", syncSystemTheme);
  });
  document.addEventListener("glis:theme", () => setTimeout(renderCharts, 30));
  document.body.addEventListener("htmx:afterSwap", (event) => init(event.detail.target));
  document.body.addEventListener("htmx:afterRequest", (event) => {
    const form = event.detail.elt;
    if (event.detail.successful && form instanceof HTMLFormElement && form.dataset.resetOnSuccess === "true") form.reset();
  });
})();
