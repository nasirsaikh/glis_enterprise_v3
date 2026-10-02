/* Live updates preserve drafts; revision checks also run on the server. */
(() => {
  const watches = new Map();
  const baseline = new WeakMap();
  const requestOwners = new WeakMap();
  const serialize = form => JSON.stringify([...new FormData(form)].filter(([key]) => !['csrfmiddlewaretoken', 'ticket_revision'].includes(key)).map(([key, value]) => [key, value instanceof File ? (value.name ? `${value.name}:${value.size}:${value.lastModified}` : '') : value]));
  const forms = watch => [...watch.root.querySelectorAll('form')].filter(form => form.method.toLowerCase() === 'post'
    && (watch.root !== document.body || form.closest('#portal-main') || form.matches('[data-ticket-action],[data-tpa-hx-form]')));
  function stamp(watch) {
    forms(watch).forEach(form => {
      let field = form.querySelector('[name="ticket_revision"]');
      if (!field) {field = document.createElement('input'); field.type = 'hidden'; field.name = 'ticket_revision'; form.append(field);}
      field.value = watch.revision;
      if (!baseline.has(form)) baseline.set(form, serialize(form));
    });
  }
  function stale(watch, message) {
    watch.stale = true;
    if (!watch.notice) {
      watch.notice = document.createElement('div'); watch.notice.className = 'alert alert-warning sticky-top d-flex flex-wrap align-items-center gap-2'; watch.notice.setAttribute('role', 'alert');
      const text = document.createElement('span'); text.className = 'flex-grow-1'; text.textContent = message;
      const reload = document.createElement('button'); reload.type = 'button'; reload.className = 'btn btn-primary btn-sm'; reload.textContent = document.documentElement.lang === 'ar' ? 'إعادة تحميل' : 'Reload latest record';
      reload.addEventListener('click', () => location.reload()); watch.notice.append(text, reload);
      (watch.root === document.body ? document.getElementById('portal-main') : watch.root)?.prepend(watch.notice);
    }
    forms(watch).forEach(form => form.querySelectorAll('[type="submit"],button:not([type])').forEach(button => {button.disabled = true;}));
  }
  async function poll(watch) {
    if (document.hidden || watch.pending.size || watch.stale || !watch.root.isConnected) return;
    try {
      const response = await fetch(watch.root.dataset.ticketUpdatesUrl, {headers: {'X-Requested-With':'XMLHttpRequest'}, cache:'no-store'});
      if ([403,404].includes(response.status)) {stale(watch, 'Access to this request has changed. Reload to continue.'); return;}
      if (!response.ok) return;
      const data = await response.json();
      if (String(data.revision) === watch.revision || watch.pending.size) return;
      const dirty = forms(watch).some(form => baseline.get(form) !== serialize(form));
      const expanded = watch.root.querySelector('.modal.show');
      if (dirty || expanded) stale(watch, 'Another user updated this request. Your draft is preserved on this page. Reload the latest record before submitting.');
      else location.reload();
    } catch (_) { /* A transient connection loss does not discard the draft. */ }
  }
  function init() {
    for (const [root, watch] of watches) if (!root.isConnected) {clearInterval(watch.timer); watches.delete(root);}
    document.querySelectorAll('[data-ticket-live]').forEach(root => {
      if (root !== document.body && document.body.hasAttribute('data-ticket-live')) return;
      let watch = watches.get(root);
      if (!watch) {watch = {root, revision:root.dataset.ticketRevision, pending:new Set()}; watch.timer=setInterval(()=>poll(watch),2000); watches.set(root,watch);}
      stamp(watch);
    });
  }
  const owner = element => [...watches.values()].find(watch => watch.root.contains(element));
  function release(event) {
    const {xhr, elt} = event.detail;
    const watch = requestOwners.get(xhr) || requestOwners.get(elt) || owner(elt);
    if (watch) {watch.pending.delete(xhr); watch.pending.delete(elt);}
    if (xhr) requestOwners.delete(xhr);
    if (elt) requestOwners.delete(elt);
    return watch;
  }
  document.addEventListener('submit', event => {const watch=owner(event.target); if (watch && forms(watch).includes(event.target)) {if(watch.stale) event.preventDefault(); else stamp(watch);}},true);
  document.addEventListener('htmx:configRequest', event => {
    const watch=owner(event.detail.elt); if(!watch || event.detail.verb!=='post') return;
    const form=event.detail.elt.closest('form'); if(!form || !forms(watch).includes(form)) return;
    if(watch.stale){event.preventDefault();return;}
    event.detail.parameters.ticket_revision=watch.revision;
  });
  document.addEventListener('htmx:beforeRequest', event => {
    if (event.defaultPrevented) return;
    const watch=owner(event.detail.elt), key=event.detail.xhr || event.detail.elt;
    if(watch && key) {watch.pending.add(key); requestOwners.set(key,watch);}
  });
  ['htmx:sendAbort','htmx:sendError','htmx:timeout'].forEach(name=>document.addEventListener(name,release));
  document.addEventListener('htmx:afterRequest', event => {
    const watch=release(event); if(!watch) return;
    const xhr=event.detail.xhr;
    if(xhr.getResponseHeader('X-Ticket-Stale')) {stale(watch, xhr.responseText); return;}
    const revision=xhr.getResponseHeader('X-Ticket-Revision');
    if(revision && event.detail.successful) {watch.revision=revision; if(event.detail.elt instanceof HTMLFormElement) baseline.set(event.detail.elt,serialize(event.detail.elt)); stamp(watch);}
  });
  document.addEventListener('DOMContentLoaded',init);document.addEventListener('htmx:afterSwap',init);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)watches.forEach(poll);});
  if(document.readyState!=='loading')init();
})();
