(function () {
  "use strict";

  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-open-dialog]");
    const dialog = opener && document.getElementById(opener.dataset.openDialog);
    if (dialog?.matches("[data-tpa-notes-dialog]")) {
      dialog.querySelectorAll("textarea").forEach(field => { field.dataset.notesOriginal = field.value; });
    }
    const cancel = event.target.closest("[data-cancel-tpa-notes]");
    if (cancel) {
      const notes = cancel.closest(".modal");
      notes.querySelectorAll("textarea").forEach(field => { field.value = field.dataset.notesOriginal ?? field.defaultValue; });
      window.glisUI.closeModal(notes);
    }
  });
  document.addEventListener("show.bs.modal", (event) => {
    if (event.target.matches?.("[data-tpa-notes-dialog]")) {
      event.target.querySelectorAll("textarea").forEach(field => { field.dataset.notesOriginal = field.value; });
    }
  });
  document.addEventListener("hidden.bs.modal", (event) => {
    if (event.target.matches?.("[data-tpa-notes-dialog]")) {
      event.target.querySelectorAll("textarea").forEach(field => {
        field.value = field.dataset.notesOriginal ?? field.defaultValue;
      });
    }
  }, true);

  const root = document.documentElement;
  const charts = new Map();

  const cssVar = (name, fallback) => {
    const value = getComputedStyle(root).getPropertyValue(name).trim();
    return value || fallback;
  };
  const isDark = () => root.getAttribute("data-theme") === "dark";
  const palette = () => [
    cssVar("--bs-primary", "#167a52"),
    cssVar("--bs-info", "#0284c7"),
    cssVar("--bs-success", "#16a34a"),
    cssVar("--bs-warning", "#d97706"),
    cssVar("--bs-danger", "#dc2626"),
    cssVar("--bs-secondary", "#7c3aed"),
    cssVar("--bs-info", "#0891b2"),
  ];

  const destroyChart = (id) => {
    const chart = charts.get(id);
    if (chart) {
      chart.destroy();
      charts.delete(id);
    }
  };

  const renderChart = (id, options) => {
    const element = document.getElementById(id);
    if (!element || !window.ApexCharts) return;
    destroyChart(id);
    const chart = new ApexCharts(element, options);
    charts.set(id, chart);
    chart.render();
  };

  const commonChart = (type, height = 235) => ({
    chart: {
      type,
      height,
      background: "transparent",
      foreColor: cssVar("--bs-body-color", "#475569"),
      fontFamily: "Inter, Cairo, sans-serif",
      toolbar: { show: false },
      zoom: { enabled: false },
      animations: { enabled: true, easing: "easeinout", speed: 280 },
      redrawOnParentResize: true,
      redrawOnWindowResize: true,
    },
    theme: { mode: isDark() ? "dark" : "light" },
    grid: {
      borderColor: cssVar("--bs-border-color", "#e5e7eb"),
      strokeDashArray: 3,
      padding: { left: 6, right: 8, top: 0, bottom: 0 },
    },
    dataLabels: { enabled: false },
    legend: {
      fontSize: "10px",
      fontWeight: 600,
      labels: { colors: cssVar("--bs-body-color", "#475569") },
      markers: { size: 5 },
      itemMargin: { horizontal: 8, vertical: 3 },
    },
    tooltip: {
      theme: isDark() ? "dark" : "light",
      style: { fontSize: "11px" },
    },
    states: {
      hover: { filter: { type: "lighten", value: 0.04 } },
      active: { filter: { type: "darken", value: 0.04 } },
    },
    responsive: [
      {
        breakpoint: 640,
        options: {
          chart: { height: 220 },
          legend: { fontSize: "9px" },
        },
      },
    ],
  });

  const readJSON = (id) => {
    const source = document.getElementById(id);
    if (!source) return null;
    try {
      return JSON.parse(source.textContent || "[]");
    } catch (_) {
      return [];
    }
  };

  const renderTPACharts = () => {
    const quality = readJSON("tpa-quality-data");
    const errors = readJSON("tpa-error-data");
    if (quality === null || errors === null || !window.ApexCharts) return;

    const qualityOptions = commonChart("donut");
    Object.assign(qualityOptions, {
      series: quality.map((item) => Number(item.value || 0)),
      labels: quality.map((item) => item.label),
      colors: [
        cssVar("--bs-success", "#16a34a"),
        cssVar("--bs-warning", "#d97706"),
        cssVar("--bs-danger", "#dc2626"),
      ],
      stroke: {
        width: 2,
        colors: [cssVar("--bs-body-bg", "#fff")],
      },
      plotOptions: {
        pie: {
          expandOnClick: false,
          donut: {
            size: "72%",
            labels: {
              show: true,
              name: { fontSize: "10px" },
              value: { fontSize: "18px", fontWeight: 700 },
              total: { show: true, label: "ROWS", fontSize: "9px" },
            },
          },
        },
      },
      legend: { ...qualityOptions.legend, position: "bottom" },
      noData: { text: "No member rows" },
    });
    renderChart("tpa-quality-chart", qualityOptions);

    const errorOptions = commonChart("bar");
    Object.assign(errorOptions, {
      series: [{ name: "Rows", data: errors.map((item) => Number(item.value || 0)) }],
      colors: [cssVar("--bs-danger", "#dc2626")],
      plotOptions: {
        bar: {
          horizontal: true,
          borderRadius: 4,
          borderRadiusApplication: "end",
          barHeight: "44%",
        },
      },
      xaxis: {
        categories: errors.map((item) => item.label),
        min: 0,
        tickAmount: Math.max(1, Math.min(5, errors.length || 1)),
      },
      legend: { show: false },
      noData: { text: "No validation errors" },
    });
    renderChart("tpa-error-chart", errorOptions);
  };

  const renderDashboardCharts = () => {
    const statusRows = readJSON("tpa-dashboard-status-data");
    const sourceRows = readJSON("tpa-dashboard-source-data");
    if (statusRows === null || sourceRows === null || !window.ApexCharts) return;

    const statusOptions = commonChart("donut", 245);
    Object.assign(statusOptions, {
      series: statusRows.map((item) => Number(item.value || 0)),
      labels: statusRows.map((item) => item.label),
      colors: palette(),
      stroke: {
        width: 2,
        colors: [cssVar("--bs-body-bg", "#fff")],
      },
      plotOptions: {
        pie: {
          expandOnClick: false,
          donut: {
            size: "73%",
            labels: {
              show: true,
              name: { fontSize: "10px" },
              value: { fontSize: "18px", fontWeight: 700 },
              total: { show: true, label: "CASES", fontSize: "9px" },
            },
          },
        },
      },
      legend: { ...statusOptions.legend, position: "bottom" },
      noData: { text: "No transactions" },
    });
    renderChart("tpa-status-chart", statusOptions);

    const sourceOptions = commonChart("bar", 245);
    Object.assign(sourceOptions, {
      series: [{
        name: "Transactions",
        data: sourceRows.map((item) => Number(item.value || 0)),
      }],
      colors: [cssVar("--bs-primary", "#167a52")],
      plotOptions: {
        bar: {
          horizontal: true,
          borderRadius: 5,
          borderRadiusApplication: "end",
          barHeight: "42%",
        },
      },
      xaxis: {
        categories: sourceRows.map((item) => item.label),
        min: 0,
        forceNiceScale: true,
      },
      legend: { show: false },
      noData: { text: "No source activity" },
    });
    renderChart("tpa-source-chart", sourceOptions);
  };

  const setupPrincipal = (scope = document) => {
    scope.querySelectorAll('[name="relationship"]').forEach(relationship => {
      const principalSelect = relationship.form?.querySelector('[name="principal_reference"]');
      const principalField = principalSelect?.closest("fieldset");
      if (!principalField) return;
      const sync = () => {
        const needed = relationship.value && !["PRINCIPAL", "PARENT"].includes(relationship.value);
        principalField.hidden = !needed;
        principalSelect.required = Boolean(needed);
        if (!needed && principalSelect.value) { principalSelect.value = ""; principalSelect.dispatchEvent(new Event('change', {bubbles:true})); }
      };
      if (relationship.dataset.tpaPrincipalReady !== "true") {
        relationship.dataset.tpaPrincipalReady = "true";
        relationship.addEventListener("change", sync);
      }
      sync();
    });
  };

  const setupDropzones = (scope = document) => {
    scope
      .querySelectorAll("[data-tpa-dropzone]:not([data-tpa-ready])")
      .forEach((zone) => {
        zone.dataset.tpaReady = "true";
        const input = zone.querySelector('input[type="file"]');
        const count = zone.querySelector("[data-tpa-file-count]");
        const list = zone.querySelector("[data-tpa-file-list]");
        if (!input) return;
        let selected = Array.from(input.files || []);

        const update = () => {
          const transfer = new DataTransfer();
          selected.forEach(file => transfer.items.add(file));
          input.files = transfer.files;
          const files = selected;
          if (count) {
            count.textContent = files.length
              ? `${files.length} file(s) selected`
              : "No files selected";
          }
          list?.replaceChildren();
          files.forEach((file, index) => {
            const row = document.createElement('div'); row.className = 'd-flex align-items-center gap-2 rounded-3 border p-2 bg-body';
            const name = document.createElement('span'); name.className = 'text-break flex-grow-1 small'; name.textContent = `${file.name} (${Math.ceil(file.size / 1024)} KB)`;
            const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn btn-outline-danger btn-sm'; remove.textContent = document.documentElement.lang === 'ar' ? 'إزالة' : 'Remove'; remove.setAttribute('aria-label', `${remove.textContent} ${file.name}`);
            remove.addEventListener('click', () => {selected.splice(index, 1); update();});
            row.append(name, remove); list?.append(row);
          });
        };
        const add = files => {
          for (const file of files) if (!selected.some(item => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) selected.push(file);
          update(); input.dispatchEvent(new Event('input', {bubbles:true}));
        };

        zone.addEventListener("click", (event) => {
          if (event.target.closest("button,a,input,label")) return;
          input.click();
        });

        ["dragenter", "dragover"].forEach((name) =>
          zone.addEventListener(name, (event) => {
            event.preventDefault();
            zone.classList.add("bg-primary-subtle");
          })
        );
        ["dragleave", "drop"].forEach((name) =>
          zone.addEventListener(name, (event) => {
            event.preventDefault();
            zone.classList.remove("bg-primary-subtle");
          })
        );

        zone.addEventListener("drop", (event) => {
          if (event.dataTransfer?.files?.length) {
            add(Array.from(event.dataTransfer.files));
          }
        });
        input.addEventListener("change", () => add(Array.from(input.files || [])));
        input.form?.addEventListener('reset', () => { selected = []; setTimeout(update); });
        update();
      });
  };

  document.body?.addEventListener("htmx:beforeSwap", event => {
    if (!event.detail.shouldSwap) return;
    const target = event.detail.target;
    charts.forEach((chart, id) => {
      const element = document.getElementById(id);
      if (element && (target === element || target?.contains(element))) destroyChart(id);
    });
  });

  const init = (scope = document) => {
    setupPrincipal(scope);
    setupDropzones(scope);
    window.requestAnimationFrame(() => {
      renderTPACharts();
      renderDashboardCharts();
    });
  };

  if (document.readyState === 'loading') document.addEventListener("DOMContentLoaded", () => init(), {once:true});
  else init();
  document.addEventListener("glis:theme", () =>
    setTimeout(() => {
      renderTPACharts();
      renderDashboardCharts();
    }, 50)
  );
  document.body?.addEventListener("htmx:afterSwap", (event) =>
    init(document.getElementById(event.detail.target?.id) || event.target)
  );
})();


(() => {
  const initializedWizards = new WeakSet();
  const setupTransactionWizard = (scope = document) => {
    const roots = [];
    if (scope.matches?.("[data-transaction-wizard]")) roots.push(scope);
    roots.push(...(scope.querySelectorAll?.("[data-transaction-wizard]") || []));
    roots.forEach((wizard) => {
      if (initializedWizards.has(wizard)) return;
      initializedWizards.add(wizard);
      wizard.dataset.wizardReady = "true";
      const form = wizard.querySelector("form");
      const steps = Array.from(wizard.querySelectorAll("[data-wizard-step]"));
      const indicators = Array.from(wizard.querySelectorAll("[data-wizard-indicator]"));
      const previous = wizard.querySelector("[data-wizard-prev]");
      const next = wizard.querySelector("[data-wizard-next]");
      const submit = wizard.querySelector("[data-wizard-submit]");
      const currentLabel = wizard.querySelector("[data-wizard-current]");
      if (!form || !steps.length) return;
      let activeStep = Math.max(0, Math.min(steps.length - 1, Number(wizard.dataset.initialStep || 1) - 1));

      const selectedLabel = (name) => {
        const control = form.elements.namedItem(name);
        if (!control) return "—";
        const selected = control.selectedOptions?.[0];
        return selected && selected.value ? selected.textContent.trim() : "—";
      };
      const syncConditionalFields = () => {
        const type = form.elements.namedItem("transaction_type")?.value || "";
        const needsRefund = ["MEMBER_DELETE", "POLICY_CANCEL"].includes(type);
        const isSuspension = type === "MEMBER_SUSPEND";
        const refundFieldset = wizard.querySelector("[data-refund-fieldset]");
        const reactivationFieldset = wizard.querySelector("[data-reactivation-fieldset]");
        const refundControl = form.elements.namedItem("refund_basis");
        const reactivationControl = form.elements.namedItem("expected_reactivation_date");
        const remarksControl = form.elements.namedItem("remarks");
        if (refundFieldset) refundFieldset.hidden = !needsRefund;
        if (reactivationFieldset) reactivationFieldset.hidden = !isSuspension;
        if (refundControl) {
          refundControl.required = needsRefund;
          if (!needsRefund && !refundControl.value) {
            const notApplicable = Array.from(refundControl.options || []).find((option) => option.value === "NONE");
            if (notApplicable) refundControl.value = "NONE";
          }
        }
        if (reactivationControl) reactivationControl.required = false;
        if (remarksControl) remarksControl.required = isSuspension;
      };
      const updateSummary = () => {
        const effectiveDate = form.elements.namedItem("effective_date");
        const policySummary = wizard.querySelector("[data-wizard-summary-policy]");
        const typeSummary = wizard.querySelector("[data-wizard-summary-type]");
        const dateSummary = wizard.querySelector("[data-wizard-summary-date]");
        if (policySummary) policySummary.textContent = selectedLabel("policy");
        if (typeSummary) typeSummary.textContent = selectedLabel("transaction_type");
        if (dateSummary) dateSummary.textContent = effectiveDate?.value || "—";
      };
      const showStep = (index) => {
        activeStep = Math.max(0, Math.min(steps.length - 1, index));
        wizard.dataset.initialStep = String(activeStep + 1);
        steps.forEach((step, stepIndex) => {
          step.hidden = stepIndex !== activeStep;
          step.setAttribute("aria-hidden", String(stepIndex !== activeStep));
        });
        indicators.forEach((indicator, stepIndex) => {
          const state = stepIndex < activeStep ? "complete" : stepIndex === activeStep ? "active" : "upcoming";
          indicator.dataset.state = state;
          indicator.classList.toggle("is-current", state === "active");
          indicator.classList.toggle("is-complete", state === "complete");
          if (state === "active") indicator.setAttribute("aria-current", "step");
          else indicator.removeAttribute("aria-current");
        });
        if (currentLabel) currentLabel.textContent = String(activeStep + 1);
        if (previous) previous.hidden = activeStep === 0;
        if (next) next.hidden = activeStep === steps.length - 1;
        if (submit) submit.hidden = activeStep !== steps.length - 1;
        updateSummary();
      };
      const firstInvalidField = (step) => Array.from(step.querySelectorAll("input, select, textarea")).find((field) => !field.closest('[data-plan-row][hidden]') && field.willValidate && !field.checkValidity());
      const validateStep = (index) => {
        const invalid = firstInvalidField(steps[index]);
        if (!invalid) return true;
        invalid.reportValidity();
        return false;
      };
      if (next) next.addEventListener("click", () => {
        syncConditionalFields();
        if (validateStep(activeStep)) showStep(activeStep + 1);
      });
      if (previous) previous.addEventListener("click", () => showStep(activeStep - 1));
      form.addEventListener("change", () => { syncConditionalFields(); updateSummary(); });
      form.addEventListener("input", updateSummary);
      form.addEventListener("submit", (event) => {
        syncConditionalFields();
        for (let index = 0; index < steps.length; index += 1) {
          const invalid = firstInvalidField(steps[index]);
          if (invalid) {
            event.preventDefault();
            showStep(index);
            invalid.reportValidity();
            return;
          }
        }
      }, true);
      syncConditionalFields();
      showStep(activeStep);
    });
  };

  document.addEventListener("DOMContentLoaded", () => setupTransactionWizard());
  setupTransactionWizard();
  document.body?.addEventListener("htmx:afterSwap", (event) => setupTransactionWizard(document.getElementById(event.detail.target?.id) || event.target));
  document.addEventListener("htmx:historyRestore", () => setupTransactionWizard());
})();


(() => {
  const initializedPlanFormsets = new WeakSet();
  const setupBenefitPlanFormsets = (scope = document) => {
    const roots = [];
    if (scope.matches?.("[data-benefit-plan-formset]")) roots.push(scope);
    roots.push(...(scope.querySelectorAll?.("[data-benefit-plan-formset]") || []));
    roots.forEach((root) => {
      if (initializedPlanFormsets.has(root)) return;
      initializedPlanFormsets.add(root);
      root.dataset.planReady = "true";
      const prefix = root.dataset.prefix || "plans";
      const list = root.querySelector("[data-plan-list]");
      const template = root.querySelector("template[data-plan-empty-form]");
      const total = root.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
      if (!list || !template || !total) return;

      const renumber = () => {
        let visible = 0;
        list.querySelectorAll("[data-plan-row]").forEach((row) => {
          if (row.hidden) return;
          visible += 1;
          const number = row.querySelector("[data-plan-number]");
          if (number) number.textContent = String(visible);
        });
      };
      const bindRemove = (row) => {
        row.querySelector("[data-remove-plan]")?.addEventListener("click", () => {
          const deleteInput = row.querySelector('input[name$="-DELETE"]');
          if (deleteInput) deleteInput.value = "on";
          row.hidden = true;
          row.querySelectorAll("input,select,textarea").forEach((control) => {
            if (!control.name.endsWith("-DELETE")) control.required = false;
          });
          renumber();
        });
      };
      list.querySelectorAll("[data-plan-row]").forEach(row => {
        if (row.hidden) row.querySelectorAll("input,select,textarea").forEach(control => {control.required = false;});
        bindRemove(row);
      });
      root.querySelector("[data-add-plan]")?.addEventListener("click", () => {
        const index = Number(total.value || 0);
        const holder = document.createElement("div");
        holder.innerHTML = template.innerHTML.replaceAll("__prefix__", String(index)).trim();
        const row = holder.firstElementChild;
        if (!row) return;
        list.appendChild(row);
        total.value = String(index + 1);
        bindRemove(row);
        renumber();
        row.querySelector("input,select,textarea")?.focus();
      });
      renumber();
    });
  };

  document.addEventListener("DOMContentLoaded", () => setupBenefitPlanFormsets());
  setupBenefitPlanFormsets();
  document.body?.addEventListener("htmx:afterSwap", (event) =>
    setupBenefitPlanFormsets(document.getElementById(event.detail.target?.id) || event.target)
  );
  document.addEventListener("htmx:historyRestore", () => setupBenefitPlanFormsets());
})();
