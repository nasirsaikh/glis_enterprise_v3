# Tailwind CSS + daisyUI migration

This branch introduces a collision-safe Tailwind CSS 4 + daisyUI 5 layer alongside the existing Bootstrap templates.

## Why the prefixes

The existing application still has Bootstrap-based ticket, document, account and HTMX partial templates. To avoid class collisions during the migration:

- Tailwind utilities use the `tw:` prefix, for example `tw:flex` and `tw:p-6`.
- daisyUI uses the `d-` component prefix and is also namespaced by Tailwind, for example `tw:d-btn`, `tw:d-card`, `tw:d-stat`.
- The existing Bootstrap CSS remains loaded for screens that have not yet been migrated.

This lets migrated and legacy views run side-by-side safely.

## Commands

```bash
npm install
npm run build:css
```

For development:

```bash
npm run watch:css
```

The source file is `static/src/tailwind.css` and the generated production file is `static/css/glis-tailwind.css`.

## Themes

The UI ships with two custom daisyUI themes:

- `glis` — light
- `glis-dark` — dark

The existing theme toggle now updates both `data-theme` for daisyUI and `data-bs-theme` for remaining Bootstrap views.

## Migration scope in this branch

- Public base shell and navigation
- CMS public home loader
- Public homepage content
- Portal base shell/navigation
- Portal overview dashboard
- Shared motion layer: reveal, pointer aura, 3D tilt, rotating text, hover gallery, counters
- Existing HTMX, Plotly, rich-text, notifications and sidebar preference behavior retained

Remaining legacy screens continue to render with Bootstrap and can be migrated incrementally using the same prefixed component system.
