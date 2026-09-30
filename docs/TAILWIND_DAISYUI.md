# Tailwind CSS + daisyUI in GLIS

The authenticated GLIS portal now follows the standard daisyUI Django installation model and uses **normal Tailwind/daisyUI classes without a prefix**.

Examples:

```html
<div class="flex gap-4">
  <section class="card bg-base-100">
    <div class="card-body">
      <button class="btn btn-primary">Save</button>
    </div>
  </section>
</div>
```

The old portal syntax such as `tw:flex`, `tw:d-btn`, `tw:d-card`, etc. is no longer used.

## Portal runtime

The authenticated portal loads:

```
static/css/output.css
```

from Django static files:

```django
<link href="{% static 'css/output.css' %}" rel="stylesheet" type="text/css">
```

The compiled file is committed, so normal Django development and deployment still do not require Node.js, npm, npx, Vite or a Tailwind runtime process.

Run GLIS normally:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver
```

For local DEBUG development, `collectstatic` is generally unnecessary.

## Source CSS

The portal source file is:

```
static/css/input.css
```

It uses the daisyUI Django standalone setup:

```css
@import "tailwindcss";
@plugin "./daisyui.mjs";
```

and explicit `@source` entries for authenticated portal templates and Django form/widget code.

The public/CMS site currently remains on the older isolated bundle `static/css/glis-tailwind.css`. This prevents the portal migration from breaking unrelated public templates. The portal itself is fully unprefixed.

## Rebuild on Windows — no Node.js

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_portal_css.ps1
```

The script downloads the standalone Tailwind CSS executable and daisyUI plugin files when missing, then builds:

```
static/css/input.css -> static/css/output.css
```

The downloaded build tools are ignored by Git:

- `static/css/tailwindcss.exe`
- `static/css/daisyui.mjs`
- `static/css/daisyui-theme.mjs`

Only the generated `output.css` is committed.

## Manual build

The same process can be performed manually using the daisyUI Django guide:

1. Download Tailwind CSS standalone.
2. Download `daisyui.mjs` and `daisyui-theme.mjs`.
3. Run the executable against `static/css/input.css`.
4. Commit the resulting `static/css/output.css`.

Example on Windows:

```powershell
static\css\tailwindcss.exe -i static/css/input.css -o static/css/output.css
```

For continuous frontend editing:

```powershell
static\css\tailwindcss.exe -i static/css/input.css -o static/css/output.css --watch
```

## daisyUI themes

The portal build includes the standard daisyUI themes exposed in the user profile. The application still resolves the normal light/dark toggle through `data-theme`.

## Portal JavaScript

The authenticated portal loads:

```
static/js/portal.js
```

This is the unprefixed portal runtime. The public site retains `static/js/app.js` until that separate frontend is migrated.

## Development rule

For authenticated portal code, write standard Tailwind/daisyUI classes only:

```html
card
card-body
btn
btn-primary
badge
badge-success
alert
table
input
select
textarea
fieldset
grid
flex
gap-4
p-4
bg-base-100
```

Do not introduce `tw:` or `d-` component prefixes into portal templates or portal Django form widgets.
# Shared public and portal CSS

Both layouts now load the committed `static/css/output.css`, with standard Tailwind utilities and daisyUI component names. The build scans all templates, Python form widgets and JavaScript-generated classes. Public Bootstrap CMS plugins are kept in a lower CSS layer through `bootstrap-compat.css` (or its RTL counterpart), so they do not override application components. `ui.css` corrects shared forms, tables, dialogs and compact timelines. Theme preferences are applied by `theme.js` before CSS paints, then persisted by the existing profile endpoint.

The compiled CSS is committed, so pulling these changes does not require Node/npm. Use the existing `scripts/build_portal_css.ps1` only when adding new utility classes.
