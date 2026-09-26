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

- Public base shell, navigation, footer and CMS homepage
- Public Knowledge Base list/detail
- Sign in, sign up and password reset
- Portal base shell/navigation and responsive mobile drawer
- Portal overview dashboard
- Ticket list, ticket detail/conversation, editor and 4-step creation wizard
- Task workspace, HTMX editor and tables
- Notifications
- Document Center
- Profile and security
- Vanna analytics workspace
- Django form widgets and dynamic form controls
- Shared motion layer: reveal, pointer aura, 3D tilt, native daisyUI Aura, Hover 3D, Hover Gallery, Text Rotate, Timeline, Stats and Lists
- Existing HTMX, Plotly, rich-text, document upload, notifications and sidebar preference behavior retained

Bootstrap remains loaded as a compatibility layer for any infrequently used legacy partials that have not yet been rewritten. Migrated screens use the collision-safe Tailwind/daisyUI component system and can coexist with those partials while the final cleanup is completed.
