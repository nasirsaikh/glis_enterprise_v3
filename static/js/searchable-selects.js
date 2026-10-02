/* Progressive enhancement: native select values and HTMX change events remain authoritative. */
(() => {
  "use strict";
  const widgets = new Map();
  const words = (en, ar) => document.documentElement.lang === "ar" ? ar : en;
  let sequence = 0;
  let active = null;

  function enhance(select) {
    if (widgets.has(select) || select.matches('[data-no-search], .admin-autocomplete, .selectfilter, .selectfilterstacked') || select.closest('.selector, #empty-form, .empty-form') || select.id.includes('__prefix__')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'glis-searchable-select';
    const control = document.createElement('button');
    control.type = 'button';
    control.className = 'form-select glis-select-control';
    control.setAttribute('aria-haspopup', 'listbox');
    control.setAttribute('aria-expanded', 'false');
    select.before(wrapper); wrapper.append(select, control);
    select.classList.add('glis-select-native');
    const oldTabIndex = select.getAttribute('tabindex');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');

    const menu = document.createElement('div');
    menu.className = 'glis-select-menu'; menu.hidden = true;
    const search = document.createElement('input');
    search.type = 'search'; search.className = 'form-control form-control-sm glis-select-search';
    search.placeholder = words('Search options…', 'البحث في الخيارات…');
    search.setAttribute('aria-label', words('Search options', 'البحث في الخيارات'));
    search.setAttribute('role', 'combobox'); search.setAttribute('aria-autocomplete', 'list');
    const list = document.createElement('div');
    list.id = `glis-select-options-${++sequence}`; list.className = 'glis-select-options'; list.setAttribute('role', 'listbox');
    search.setAttribute('aria-controls', list.id); control.setAttribute('aria-controls', list.id);
    if (select.multiple) list.setAttribute('aria-multiselectable', 'true');
    menu.append(search, list);
    let focused = -1;
    let options = [];
    const labelText = () => [...select.labels].map(label => {
      const copy = label.cloneNode(true);
      copy.querySelectorAll('select, .glis-searchable-select, input, button').forEach(node => node.remove());
      return copy.textContent.trim();
    }).join(' ') || select.getAttribute('aria-label') || select.name || words('Select', 'اختر');

    function refresh() {
      const values = [...select.selectedOptions].map(option => option.textContent.trim());
      control.textContent = values.join(', ') || select.options[0]?.textContent || words('Select', 'اختر');
      control.disabled = select.disabled;
      control.setAttribute('aria-label', `${labelText()}: ${control.textContent}`);
      control.setAttribute('aria-required', String(select.required));
      wrapper.hidden = select.hidden;
      if (select.disabled) close();
    }
    function position() {
      if (menu.hidden) return;
      const rect = control.getBoundingClientRect();
      const maxHeight = Math.min(340, Math.max(120, innerHeight - 20));
      menu.style.width = `${Math.min(rect.width, innerWidth - 16)}px`;
      menu.style.maxHeight = `${maxHeight}px`;
      menu.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - rect.width - 8))}px`;
      const height = Math.min(menu.scrollHeight, maxHeight);
      const below = rect.bottom + height + 8 <= innerHeight;
      menu.style.top = `${below ? rect.bottom + 4 : Math.max(8, rect.top - height - 4)}px`;
      menu.style.zIndex = select.closest('.modal') ? '1065' : '1035';
    }
    function focusOption(index) {
      if (!options.length) { focused = -1; search.removeAttribute('aria-activedescendant'); return; }
      focused = Math.max(0, Math.min(index, options.length - 1));
      options.forEach((option, i) => option.classList.toggle('is-focused', i === focused));
      search.setAttribute('aria-activedescendant', options[focused].id);
      options[focused].scrollIntoView({block: 'nearest'});
    }
    function choose(index) {
      const option = select.options[index];
      if (!option || option.disabled || option.parentElement?.disabled) return;
      if (select.multiple) option.selected = !option.selected;
      else select.selectedIndex = index;
      control.removeAttribute('aria-invalid');
      select.dispatchEvent(new Event('input', {bubbles: true}));
      select.dispatchEvent(new Event('change', {bubbles: true}));
      refresh();
      if (select.multiple) render();
      else { close(); control.focus(); }
    }
    function render() {
      const term = search.value.trim().toLocaleLowerCase();
      const groupLabels = new Set(); list.replaceChildren(); options = [];
      for (const option of select.options) {
        const group = option.parentElement.tagName === 'OPTGROUP' ? option.parentElement : null;
        if (option.hidden || !`${option.textContent} ${group?.label || ''}`.toLocaleLowerCase().includes(term)) continue;
        if (group && !groupLabels.has(group)) {
          const heading = document.createElement('div'); heading.className = 'glis-select-group'; heading.textContent = group.label;
          list.append(heading); groupLabels.add(group);
        }
        const row = document.createElement('button');
        row.type = 'button'; row.className = 'glis-select-option'; row.id = `${list.id}-${option.index}`;
        row.setAttribute('role', 'option'); row.setAttribute('aria-selected', String(option.selected));
        row.disabled = option.disabled || Boolean(group?.disabled); row.tabIndex = -1;
        row.textContent = `${select.multiple && option.selected ? '✓ ' : ''}${option.textContent}`;
        row.addEventListener('mousedown', event => event.preventDefault());
        row.addEventListener('click', () => choose(option.index));
        list.append(row); if (!row.disabled) options.push(row);
      }
      if (!list.children.length) {
        const empty = document.createElement('div'); empty.className = 'glis-select-empty'; empty.textContent = words('No matching options', 'لا توجد خيارات مطابقة'); list.append(empty);
      }
      focused = -1; search.removeAttribute('aria-activedescendant'); position();
    }
    function open() {
      if (select.disabled) return;
      active?.close(); active = widget;
      (select.closest('.modal') || document.body).append(menu);
      menu.hidden = false; control.setAttribute('aria-expanded', 'true'); search.setAttribute('aria-expanded', 'true');
      search.value = ''; refresh(); render(); search.focus();
    }
    function close() {
      menu.hidden = true; control.setAttribute('aria-expanded', 'false'); search.setAttribute('aria-expanded', 'false');
      if (active === widget) active = null;
    }
    const widget = {select, wrapper, menu, control, refresh, position, close, destroy() {
      close(); observer.disconnect(); menu.remove(); widgets.delete(select);
      select.classList.remove('glis-select-native'); select.removeAttribute('aria-hidden');
      if (oldTabIndex === null) select.removeAttribute('tabindex'); else select.setAttribute('tabindex', oldTabIndex);
    }};
    widgets.set(select, widget);
    control.addEventListener('click', () => menu.hidden ? open() : close());
    control.addEventListener('keydown', event => {
      if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); open(); focusOption(0); }
    });
    search.addEventListener('input', render);
    menu.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); control.focus(); }
      if (event.key === 'Tab') close();
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); focusOption(focused + (event.key === 'ArrowDown' ? 1 : -1)); }
      if (event.key === 'Enter') {
        event.preventDefault();
        if (options.length) options[focused < 0 ? 0 : focused].click();
      }
    });
    select.addEventListener('change', refresh);
    select.addEventListener('invalid', event => { event.preventDefault(); control.setAttribute('aria-invalid', 'true'); open(); });
    select.form?.addEventListener('reset', () => setTimeout(refresh));
    for (const label of select.labels) label.addEventListener('click', event => {
      if (event.target.closest('button, input, a, .glis-select-menu')) return;
      event.preventDefault(); control.focus();
    });
    const observer = new MutationObserver(() => { refresh(); if (!menu.hidden) render(); });
    observer.observe(select, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['disabled', 'hidden', 'selected', 'label', 'required']});
    refresh();
  }
  function init(scope = document) {
    for (const [select, widget] of widgets) if (!select.isConnected) widget.destroy();
    if (scope.matches?.('select')) enhance(scope);
    scope.querySelectorAll?.('select').forEach(enhance);
    for (const widget of widgets.values()) widget.refresh();
  }
  document.addEventListener('pointerdown', event => {
    if (active && !active.wrapper.contains(event.target) && !active.menu.contains(event.target)) active.close();
  });
  window.addEventListener('resize', () => active?.position());
  document.addEventListener('scroll', () => active?.position(), true);
  document.addEventListener('htmx:beforeSwap', () => active?.close());
  for (const event of ['htmx:afterSwap', 'htmx:load', 'glis:theme', 'formset:added']) document.addEventListener(event, () => init());
  document.addEventListener('hide.bs.modal', () => active?.close());
  document.addEventListener('DOMContentLoaded', () => init());
  if (document.readyState !== 'loading') init();
  // Dynamic formsets may be inserted without HTMX.
  new MutationObserver(records => {
    if (records.some(record => [...record.addedNodes].some(node => node.nodeType === 1 && (node.matches?.('select') || node.querySelector?.('select'))))) init();
  }).observe(document.documentElement, {childList: true, subtree: true});
})();
