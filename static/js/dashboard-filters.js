/* Modal mirrors share the real quick-filter values without duplicate form names. */
(() => {
  function init() {
    document.querySelectorAll('[data-filter-mirror]:not([data-ready])').forEach(holder => {
      const source = document.getElementById(holder.dataset.filterMirror);
      if (!source) return;
      holder.dataset.ready = 'true';
      const mirror = source.cloneNode(true);
      mirror.id = `${source.id}-advanced`;
      mirror.removeAttribute('name'); mirror.removeAttribute('form');
      mirror.removeAttribute('aria-hidden'); mirror.removeAttribute('tabindex');
      mirror.classList.remove('glis-select-native'); mirror.style.removeProperty('display');
      holder.append(mirror);
      let syncing = false;
      function copy(from, to) {
        if (syncing) return;
        syncing = true;
        const values = new Set([...from.selectedOptions].map(option => option.value));
        for (const option of to.options) option.selected = values.has(option.value);
        to.dispatchEvent(new Event('change', {bubbles: true}));
        syncing = false;
      }
      source.addEventListener('change', () => copy(source, mirror));
      mirror.addEventListener('change', () => copy(mirror, source));
      source.form?.addEventListener('reset', () => setTimeout(() => copy(source, mirror)));
      copy(source, mirror);
    });
  }
  document.addEventListener('DOMContentLoaded', init);
  document.addEventListener('htmx:afterSwap', init);
  if (document.readyState !== 'loading') init();
})();
