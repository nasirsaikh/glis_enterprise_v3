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
    const applyFilters = (targetId) => {
      const target = document.getElementById(targetId || "");
      if (!target) return;
      const searchControls = Array.from(document.querySelectorAll("[data-multiselect-search]"))
        .filter((control) => control.dataset.multiselectSearch === targetId);
      const valueFilters = Array.from(document.querySelectorAll("[data-multiselect-filter]"))
        .filter((control) => control.dataset.multiselectFilter === targetId);

      target.querySelectorAll("[data-multiselect-option]").forEach((option) => {
        const haystack = (option.dataset.searchText || option.textContent || "").toLowerCase();
        const optionValues = new Set(
          (option.dataset.filterValues || "")
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean)
        );
        const matchesSearch = searchControls.every((control) => {
          const query = control.value.trim().toLowerCase();
          return !query || haystack.includes(query);
        });
        const matchesValues = valueFilters.every((control) => {
          const selected = control.value.trim();
          return !selected || optionValues.has(selected);
        });
        option.classList.toggle("d-none", !(matchesSearch && matchesValues));
      });
    };

    scope.querySelectorAll("[data-multiselect-search]:not([data-multiselect-ready])").forEach((input) => {
      input.dataset.multiselectReady = "true";
      const targetId = input.dataset.multiselectSearch || "";
      input.addEventListener("input", () => applyFilters(targetId));
      applyFilters(targetId);
    });

    scope.querySelectorAll("[data-multiselect-filter]:not([data-multiselect-ready])").forEach((select) => {
      select.dataset.multiselectReady = "true";
      const targetId = select.dataset.multiselectFilter || "";
      select.addEventListener("change", () => applyFilters(targetId));
      applyFilters(targetId);
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
    document.querySelectorAll("[data-mobile-nav-open]").forEach((button) => button.addEventListener("click", () => window.glisUI.openModal(dialog)));
    dialog.querySelectorAll("[data-mobile-nav-close]").forEach((button) => button.addEventListener("click", () => window.glisUI.closeModal(dialog)));
    dialog.addEventListener("click", (event) => { if (event.target === dialog) window.glisUI.closeModal(dialog); });
  };

  const chartInstances = new Map();
  const cssColor = (name, fallback) => {
    const value = getComputedStyle(root).getPropertyValue(name).trim();
    return value || fallback;
  };
  const chartTheme = () => root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  const chartColors = () => [
    cssColor("--bs-primary", "#147A50"),
    cssColor("--bs-info", "#2563EB"),
    cssColor("--bs-warning", "#D99400"),
    cssColor("--bs-danger", "#C2413B"),
    cssColor("--bs-secondary", "#7357C7"),
    cssColor("--bs-success", "#3CA37A"),
    cssColor("--bs-secondary", "#6B7280")
  ];
  const baseChartOptions = (type, height = 300) => ({
    chart: {
      type,
      height,
      background: "transparent",
      foreColor: cssColor("--bs-body-color", "#4c5c54"),
      fontFamily: "Inter, Cairo, sans-serif",
      toolbar: {show: false},
      zoom: {enabled: false},
      animations: {enabled: true, speed: 260}
    },
    theme: {mode: chartTheme()},
    grid: {
      borderColor: cssColor("--bs-border-color", "#edf1ef"),
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
  const renderPolicyCharts = () => {
    const source = document.getElementById("policy-dashboard-data");
    if (!source || !window.ApexCharts) return;
    const data = JSON.parse(source.textContent);
    const colors = chartColors();
    const activeColors = [cssColor("--bs-success", "#16a34a"), cssColor("--bs-warning", "#d97706")];
    const countAxis = (values, categories) => {
      const largest = Math.max(0, ...values.map(Number));
      const step = Math.max(1, Math.ceil(largest / 5));
      const maximum = Math.max(1, Math.ceil(largest / step)) * step;
      return {categories, min: 0, max: maximum, tickAmount: maximum / step, decimalsInFloat: 0};
    };
    [["policy-active-chart", data.active_chart, activeColors],
     ["policy-status-chart", data.status_chart, colors],
     ["policy-relationship-chart", data.relationship_chart, colors]].forEach(([id, rows, palette]) => {
      const nonempty = (rows || []).filter(row => Number(row.total) > 0);
      apex(id, {...baseChartOptions("donut", 280), series: nonempty.map(row => Number(row.total)),
        labels: labels(nonempty), colors: (rows || []).map((row, i) => [row, palette[i % palette.length]]).filter(([row]) => Number(row.total) > 0).map(([, color]) => color),
        stroke: {width: 2, colors: [cssColor("--bs-body-bg", "#fff")]},
        legend: {position: "bottom", fontSize: "12px"},
        plotOptions: {pie: {donut: {size: "68%", labels: {show: true, total: {show: true, label: "Members"}}}}}
      });
    });
    const plans = data.plan_rows || [];
    apex("policy-plan-chart", {...baseChartOptions("bar", 280),
      chart: {...baseChartOptions("bar", 280).chart, stacked: true},
      series: plans.length ? [{name: "Active", data: plans.map(row => row.active)}, {name: "Inactive", data: plans.map(row => row.inactive)}] : [],
      colors: activeColors, plotOptions: {bar: {horizontal: true, borderRadius: 4, barHeight: "55%"}},
      xaxis: countAxis(plans.map(row => row.total), plans.map(row => row.benefit_plan__code)),
      legend: {position: "bottom"}
    });
    const types = data.endorsement_chart || [];
    apex("policy-endorsement-chart", {...baseChartOptions("bar", 260),
      series: types.length ? [{name: "Endorsements", data: types.map(row => row.total)}] : [],
      colors: [colors[0]], plotOptions: {bar: {horizontal: true, borderRadius: 4, barHeight: "55%"}},
      xaxis: countAxis(types.map(row => row.total), labels(types))
    });
  };
  const renderCharts = () => {
    renderPolicyCharts();
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
        stroke: {width: 2, colors: [cssColor("--bs-body-bg", "#ffffff")]},
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
      cssColor("--bs-success", "#7ACFA5"),
      cssColor("--bs-info", "#2563EB"),
      cssColor("--bs-warning", "#D99400"),
      cssColor("--bs-danger", "#C2413B")
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
    if (!sidebar) return;

    const nav = sidebar.querySelector("nav");
    if (nav && nav.dataset.scrollWatchReady !== "true") {
      nav.dataset.scrollWatchReady = "true";
      const syncNavOverflow = () => {
        const state = nav.scrollHeight > nav.clientHeight ? "true" : "false";
        if (nav.dataset.scrollable !== state) nav.dataset.scrollable = state;
      };
      const mutationObserver = new MutationObserver(() => window.requestAnimationFrame(syncNavOverflow));
      mutationObserver.observe(nav, {
        attributes: true,
        childList: true,
        subtree: true,
        attributeFilter: ["class", "hidden"],
      });
      if ("ResizeObserver" in window) {
        const resizeObserver = new ResizeObserver(syncNavOverflow);
        resizeObserver.observe(nav);
        resizeObserver.observe(sidebar);
      }
      window.addEventListener("resize", syncNavOverflow, {passive: true});
      document.getElementById("portal-drawer")?.addEventListener("change", () => window.requestAnimationFrame(syncNavOverflow));
      window.requestAnimationFrame(syncNavOverflow);
    }
    if (!button) return;

    const normalize = (value) => value === "full" ? "full" : "mini";
    let desktopMode = normalize(
      localStorage.getItem("glis-sidebar-mode")
      || document.body?.dataset.sidebarMode
      || "mini"
    );

    const csrfToken = () => {
      const fromForm = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;
      if (fromForm) return fromForm;
      const cookie = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
      return cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : "";
    };

    const save = async (mode) => {
      localStorage.setItem("glis-sidebar-mode", mode);
      const endpoint = document.body?.dataset.sidebarPreferenceUrl;
      if (!endpoint) return;
      try {
        await fetch(endpoint, {
          method: "POST",
          headers: {
            "X-CSRFToken": csrfToken(),
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded"
          },
          body: new URLSearchParams({mode})
        });
      } catch (_) { /* Local preference remains available offline. */ }
    };

    const render = (mode) => {
      const expanded = mode === "full";
      sidebar.dataset.sidebarState = expanded ? "expanded" : "collapsed";



      sidebar.querySelectorAll("[data-sidebar-label]").forEach((element) => {
        element.classList.toggle("d-none", !expanded);
      });
      sidebar.querySelectorAll("[data-sidebar-link]").forEach((link) => {
        link.classList.toggle("justify-content-center", !expanded);
      });

      button.setAttribute("aria-expanded", String(expanded));
      button.setAttribute("aria-label", expanded ? "Collapse navigation" : "Expand navigation");
      button.setAttribute("title", expanded ? "Collapse navigation" : "Expand navigation");
      const icon = button.querySelector("i");
      if (icon) {
        icon.className = "bi " + (
          expanded ? "bi-layout-sidebar-inset-reverse" : "bi-layout-sidebar-inset"
        );
      }
    };

    const syncViewport = () => {
      if (window.matchMedia("(min-width: 992px)").matches) {
        render(desktopMode);
      } else {
        render("full");
      }
    };

    syncViewport();

    button.addEventListener("click", async () => {
      desktopMode = desktopMode === "full" ? "mini" : "full";
      render(desktopMode);
      await save(desktopMode);
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
      wrapper.className = "card richtext-editor overflow-hidden border border-body bg-body shadow-sm";
      wrapper.innerHTML = '<div class="d-flex flex-wrap align-items-center gap-1 border-bottom border-body bg-body-tertiary p-2"><button class="btn btn-light btn-sm glis-btn-icon" type="button" data-cmd="bold" title="Bold" aria-label="Bold"><i class="bi bi-type-bold"></i></button><button class="btn btn-light btn-sm glis-btn-icon" type="button" data-cmd="italic" title="Italic" aria-label="Italic"><i class="bi bi-type-italic"></i></button><button class="btn btn-light btn-sm glis-btn-icon" type="button" data-cmd="underline" title="Underline" aria-label="Underline"><i class="bi bi-type-underline"></i></button><button class="btn btn-light btn-sm glis-btn-icon" type="button" data-cmd="insertUnorderedList" title="Bullets" aria-label="Bullets"><i class="bi bi-list-ul"></i></button><button class="btn btn-light btn-sm glis-btn-icon" type="button" data-cmd="insertOrderedList" title="Numbered list" aria-label="Numbered list"><i class="bi bi-list-ol"></i></button><button class="btn btn-light btn-sm glis-btn-icon" type="button" data-cmd="createLink" title="Link" aria-label="Insert link"><i class="bi bi-link-45deg"></i></button><button class="btn btn-light btn-sm glis-btn-icon" type="button" data-image-button title="Upload image" aria-label="Upload image"><i class="bi bi-image"></i></button><input type="file" hidden data-image-input accept="image/png,image/jpeg,image/gif,image/webp"><span class="badge bg-body-secondary text-body-secondary glis-badge-small ms-2">Paste or upload images</span><button type="button" class="btn btn-light btn-sm ms-auto" data-expand-editor aria-expanded="false">Expand editor</button></div><div class="richtext-canvas form-control w-100 rounded-0 border-0 bg-body p-3" style="overflow:auto" contenteditable="true" role="textbox" aria-multiline="true"></div>';
      source.insertAdjacentElement("afterend", wrapper);
      const editor = wrapper.querySelector(".richtext-canvas");
      editor.innerHTML = source.value || "";
      editor.id = `${source.id || "richtext"}-editor`;
      const sourceLabel = source.id && document.querySelector(`label[for="${source.id}"]`);
      if (sourceLabel) sourceLabel.htmlFor = editor.id;
      editor.setAttribute("aria-label", sourceLabel?.textContent?.trim() || "Message");
      const expandButton = wrapper.querySelector("[data-expand-editor]");
      expandButton.textContent = root.lang === "ar" ? "توسيع المحرر" : "Expand editor";
      expandButton.setAttribute("aria-controls", editor.id);
      expandButton.addEventListener("click", () => {
        const expanded = wrapper.classList.toggle("is-expanded");
        editor.style.height = "";
        expandButton.setAttribute("aria-expanded", String(expanded));
        expandButton.textContent = root.lang === "ar" ? (expanded ? "تصغير المحرر" : "توسيع المحرر") : (expanded ? "Collapse editor" : "Expand editor");
      });
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
      image.className = "glis-message-avatar glis-avatar";
      const circle = document.createElement("div");
      circle.className = "glis-w-10 rounded-pill bg-primary text-white";
      const initial = document.createElement("span");
      initial.className = "small fw-bold";
      initial.textContent = currentUserInitial;
      const avatarURL = document.body.dataset.userAvatar;
      if (avatarURL) {
        const photo = document.createElement("img"); photo.src = avatarURL; photo.alt = currentUserName;
        circle.appendChild(photo);
      } else circle.appendChild(initial);
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
      article.className = "glis-message glis-message-end ai-message";
      const header = document.createElement("div");
      header.className = "glis-message-header";
      header.textContent = currentUserName;
      const bubble = document.createElement("div");
      bubble.className = "glis-message-bubble glis-message-primary glis-max-3xl";
      bubble.textContent = text;
      const footer = document.createElement("div");
      footer.className = "glis-message-footer opacity-50";
      footer.textContent = formatTime(createdAt);
      article.append(userAvatar(), header, bubble, footer);
      conversation.appendChild(article);
      scrollToLatest();
    };
    const buildTable = rows => {
      const wrapper = document.createElement("div");
      wrapper.className = "mt-2 overflow-x-auto rounded-3 bg-body text-body";
      const table = document.createElement("table");
      table.className = "table table-striped";
      wrapper.appendChild(table);
      if (!rows.length) return wrapper;
      const keys = Object.keys(rows[0]);
      const head = table.createTHead().insertRow();
      keys.forEach(key => { const th = document.createElement("th"); th.textContent = key; head.appendChild(th); });
      const body = table.createTBody();
      rows.forEach(row => { const tr = body.insertRow(); keys.forEach(key => { const td = tr.insertCell(); td.textContent = row[key] ?? ""; }); });
      return wrapper;
    };
    const vannaCharts = new Map();
    const drawQueryChart = (id, rows, spec) => {
      if (!rows.length || !window.ApexCharts) return;
      const keys = Object.keys(rows[0]), x = spec.x || keys[0], y = spec.y || keys[1];
      const values = rows.map(row => {
        const value = row[y];
        if (value === null || value === undefined || value === "") return null;
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
      });
      const categories = rows.map(row => String(row[x] ?? "—"));
      const type = spec.type === "pie" ? "donut" : spec.type === "line" ? "line" : "bar";
      const options = {...baseChartOptions(type, 300), colors: chartColors(),
        title: {text: spec.title || "", style: {fontSize: "13px"}},
        series: type === "donut" ? values.map(value => value ?? 0) : [{name: y, data: values}],
        ...(type === "donut" ? {labels: categories, legend: {position: "bottom"}}
          : {xaxis: {categories}, stroke: {width: type === "line" ? 3 : 0, curve: "smooth"},
             markers: {size: type === "line" ? 4 : 0}, plotOptions: {bar: {borderRadius: 4}},
             yaxis: {labels: {formatter: value => value == null ? "" : Number(value).toLocaleString()}}}),
      };
      apex(id, options);
      vannaCharts.set(id, {rows, spec});
    };
    const clearConversation = () => {
      vannaCharts.forEach((_, id) => { chartInstances.get(id)?.destroy(); chartInstances.delete(id); });
      vannaCharts.clear();
      conversation.querySelectorAll(".ai-message").forEach(item => item.remove());
    };
    document.addEventListener("glis:theme", () => vannaCharts.forEach((data, id) => drawQueryChart(id, data.rows, data.spec)));
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
      article.className = "ai-message ai-answer";
      const header = document.createElement("div");
      header.className = "glis-message-header d-flex align-items-center gap-2";
      const label = document.createElement("strong");
      label.innerHTML = '<i class="bi bi-stars"></i> Vanna';
      const meta = document.createElement("small");
      meta.className = "opacity-50";
      meta.textContent = queryData.status === "completed" ? `${queryData.row_count || 0} rows · ${queryData.duration_ms || 0} ms` : (queryData.error_code || "Failed");
      header.append(label, meta);

      const bubble = document.createElement("div");
      bubble.className = "card vanna-answer-card";
      if (queryData.status !== "completed") bubble.classList.add("vanna-answer-card-error");

      const summary = document.createElement("p");
      summary.className = "lh-base";
      summary.textContent = queryData.summary || (queryData.status === "completed" ? "The query completed successfully." : "The query could not be completed.");
      bubble.appendChild(summary);

      if (queryData.sql) {
        const details = document.createElement("details");
        details.className = "mt-2 rounded-3 bg-body-tertiary p-2 text-body";
        const detailsLabel = document.createElement("summary");
        detailsLabel.className = "glis-cursor-pointer fw-semibold";
        detailsLabel.textContent = "Generated SQL";
        const pre = document.createElement("pre"), code = document.createElement("code");
        pre.className = "mt-2 overflow-x-auto glis-text-xs";
        code.textContent = queryData.sql;
        pre.appendChild(code); details.append(detailsLabel, pre); bubble.appendChild(details);
      }

      const rows = queryData.data || [], spec = queryData.chart || {};
      let chartId = "";
      if (rows.length && spec.type) {
        chartId = `vanna-chart-${queryData.id || ++chartSequence}-${++chartSequence}`;
        const chart = document.createElement("div");
        chart.id = chartId;
        chart.className = "vanna-chart rounded-3 bg-body";
        bubble.appendChild(chart);
      }
      if (rows.length) bubble.appendChild(buildTable(rows));

      const actions = document.createElement("div");
      actions.className = "mt-2 d-flex flex-wrap gap-2";
      (queryData.followups || []).forEach(text => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-light btn-sm glis-btn-xs";
        button.textContent = text;
        button.dataset.vannaPrompt = text;
        bindPrompt(button);
        actions.appendChild(button);
      });
      if (queryData.export_url) {
        const link = document.createElement("a");
        link.className = "btn btn-outline-secondary btn-sm";
        link.href = queryData.export_url;
        link.innerHTML = '<i class="bi bi-download"></i> Export CSV';
        actions.appendChild(link);
      }
      if (actions.childElementCount) bubble.appendChild(actions);

      const footer = document.createElement("div");
      footer.className = "glis-message-footer opacity-50";
      footer.textContent = formatTime(queryData.created_at);
      article.append(header, bubble, footer);
      conversation.appendChild(article);
      document.dispatchEvent(new CustomEvent("glis:tables"));
      if (chartId) setTimeout(() => drawQueryChart(chartId, rows, spec), 10);
      setDiagnostics(queryData);
      scrollToLatest();
    };
    const showWelcome = () => {
      clearConversation();
      historyLoading.classList.add("d-none"); welcome.classList.remove("d-none");
    };
    const renderHistory = queries => {
      clearConversation();
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
        item = document.createElement("button"); item.type = "button"; item.className = "btn btn-light glis-h-auto w-100 justify-content-start gap-2 py-2 text-start"; item.dataset.sessionId = session.id;
        item.innerHTML = '<i class="bi bi-chat-left-text text-primary"></i><span class="glis-min-width-0 glis-flex-fill"><strong class="d-block text-truncate"></strong><small class="d-block text-truncate fw-normal opacity-50"></small></span>';
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

  // All HTMX POST forms share one busy state, including associated row buttons.
  const busyForms = new WeakMap();
  const eventForm = (event) => {
    const element = event.detail?.elt || event.target;
    return element?.matches?.("form") ? element : element?.form || element?.closest?.("form");
  };
  const processingForm = (form) => form && (
    form.hasAttribute("hx-post") || form.hasAttribute("data-processing-form")
    || form.hasAttribute("data-tpa-hx-form")
  );
  const setFormBusy = (form, busy) => {
    if (!processingForm(form)) return;
    if (busy) {
      if (busyForms.has(form)) return;
      const controls = Array.from(form.elements).filter(control =>
        control.matches?.('button[type="submit"], button:not([type]), input[type="submit"]')
      ).map(control => {
        const state = {control, disabled: control.disabled};
        control.disabled = true;
        if (control.tagName === "BUTTON") {
          let spinner = control.querySelector(".loading");
          if (!spinner) {
            spinner = document.createElement("span");
            spinner.className = "spinner-border spinner-border-sm";
            spinner.dataset.processingSpinner = "";
            spinner.setAttribute("aria-hidden", "true");
            spinner.hidden = true;
            control.appendChild(spinner);
          }
          state.spinner = spinner;
          state.hidden = spinner.hidden;
          spinner.hidden = false;
        }
        return state;
      });
      let status = form.querySelector("[data-processing-status]");
      if (!status) {
        status = document.createElement("span");
        status.dataset.processingStatus = "";
        status.className = "processing-status";
        status.setAttribute("role", "status");
        form.appendChild(status);
      }
      status.textContent = form.dataset.processingLabel || "Processing…";
      status.hidden = false;
      busyForms.set(form, {controls, status, ariaBusy: form.getAttribute("aria-busy")});
      form.classList.add("processing-form");
      form.setAttribute("aria-busy", "true");
    } else {
      const state = busyForms.get(form);
      if (!state) return;
      state.controls.forEach(item => {
        item.control.disabled = item.disabled;
        if (item.spinner) item.spinner.hidden = item.hidden ?? true;
      });
      state.status.hidden = true;
      form.classList.remove("processing-form");
      if (state.ariaBusy === null) form.removeAttribute("aria-busy");
      else form.setAttribute("aria-busy", state.ariaBusy);
      busyForms.delete(form);
    }
  };
  const centerWorkflowStep = (workspace) => {
    const scroller = workspace.querySelector(".workflow-step-scroll");
    const current = workspace.querySelector('[aria-current="step"]');
    if (scroller && current) {
      scroller.scrollLeft += current.getBoundingClientRect().left
        - scroller.getBoundingClientRect().left - (scroller.clientWidth - current.offsetWidth) / 2;
    }
  };
  const setupWorkflowWorkspace = (scope = document) => {
    const workspace = scope.matches?.("[data-workflow-workspace]") ? scope
      : scope.querySelector?.("[data-workflow-workspace]");
    if (!workspace) return;
    const key = workspace.querySelector("[data-current-step]")?.dataset.currentStep;
    workspace.querySelectorAll("form[hx-post]").forEach(form => {
      if (form.elements.namedItem("wizard_step")) return;
      const input = document.createElement("input");
      input.type = "hidden"; input.name = "wizard_step"; input.value = key;
      form.appendChild(input);
    });
    const modal = document.getElementById(workspace.dataset.reopenModal);
    if (modal && !modal.classList.contains("show")) window.glisUI.openModal(modal);
    centerWorkflowStep(workspace);
  };
  const focusWorkflow = (workspace) => {
    if (!workspace?.matches?.("[data-workflow-workspace]")) return;
    const modal = workspace.querySelector(".modal.show");
    const destination = (modal || workspace).querySelector("[data-form-errors], [data-workflow-feedback].alert-danger")
      || workspace.querySelector("[data-current-step]");
    destination?.focus({preventScroll: true});
    centerWorkflowStep(workspace);
  };

  document.body.addEventListener("click", event => {
    const button = event.target.closest("[data-open-dialog]");
    if (button) window.glisUI.openModal(document.getElementById(button.dataset.openDialog));
  });
  document.body.addEventListener("htmx:beforeRequest", event => {
    if (event.detail.requestConfig?.verb?.toLowerCase() === "post") {
      const form = eventForm(event);
      if (busyForms.has(form)) { event.preventDefault(); return; }
      form?.querySelector("[data-processing-error]")?.remove();
      setFormBusy(form, true);
    }
    const workspace = event.detail?.elt?.closest?.("[data-workflow-workspace]");
    workspace?.setAttribute("aria-busy", "true");
  });
  document.body.addEventListener("htmx:beforeSwap", event => {
    const xhr = event.detail.xhr;
    if (xhr.status >= 400 && xhr.getResponseHeader("HX-Retarget") === "#transaction-request-error") {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });
  ["htmx:afterRequest", "htmx:sendError", "htmx:responseError", "htmx:timeout", "htmx:abort"].forEach(name => {
    document.body.addEventListener(name, event => {
      if (event.detail?.requestConfig?.verb?.toLowerCase() === "post" || name === "htmx:abort") {
        setFormBusy(eventForm(event), false);
      }
      document.querySelector("[data-workflow-workspace]")?.removeAttribute("aria-busy");
      if (name === "htmx:afterRequest" || name === "htmx:abort") return;
      if (event.detail?.xhr?.getResponseHeader("HX-Retarget")) return;
      const form = eventForm(event);
      const modal = form?.closest(".modal.show");
      let target = document.querySelector("[data-workflow-request-error]");
      if (modal) {
        target = document.createElement("div");
        target.dataset.processingError = "";
        target.className = "glis-span-full";
        target.setAttribute("role", "alert");
        target.tabIndex = -1;
        form.prepend(target);
      }
      if (target) {
        target.replaceChildren();
        const alert = document.createElement("div");
        alert.className = "alert alert-danger";
        alert.textContent = "The request could not be completed. Check your connection and try again.";
        target.appendChild(alert); target.focus({preventScroll: true});
      }
    });
  });

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
    setupWorkflowWorkspace(scope);
  };
  document.addEventListener("DOMContentLoaded", () => {
    init(); setupSidebar(); setupMobileNav(); setupVanna(); setupNotifications(); setTimeout(renderCharts, 120);
    const workspace = document.querySelector("[data-workflow-workspace]");
    if (workspace) history.replaceState(history.state, "", workspace.dataset.stepUrl);
    const media = matchMedia("(prefers-color-scheme: dark)");
    const syncSystemTheme = () => { if (preferredTheme() === "system") applyTheme("system"); };
    if (media.addEventListener) media.addEventListener("change", syncSystemTheme);
  });
  document.addEventListener("glis:theme", () => setTimeout(renderCharts, 30));
  document.addEventListener("click", event => {
    document.querySelectorAll("details.dropdown[open]").forEach(item => {
      if (!item.contains(event.target)) item.open = false;
    });
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") document.querySelectorAll("details.dropdown[open]").forEach(item => { item.open = false; });
  });
  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = document.getElementById(event.detail.target?.id) || event.target;
    init(target);
    focusWorkflow(target);
  });
  document.body.addEventListener("htmx:historyRestore", () => init());
  document.body.addEventListener("htmx:afterRequest", (event) => {
    const form = event.detail.elt;
    if (event.detail.successful && form instanceof HTMLFormElement && form.dataset.resetOnSuccess === "true") form.reset();
  });
})();
