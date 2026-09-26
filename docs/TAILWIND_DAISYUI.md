# Tailwind CSS + daisyUI in GLIS

GLIS is a Django application and **does not require Node.js, npm, npx, Vite, or a Tailwind build command to run**.

## Runtime setup

The production Tailwind CSS 4 + daisyUI 5 bundle is already committed as a normal Django static asset:

```
static/css/glis-tailwind.css
```

Both main shells load it through Django static files:

```django
<link href="{% static 'css/glis-tailwind.css' %}" rel="stylesheet">
```

Run GLIS normally:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver
```

For local DEBUG development, `collectstatic` is usually not required because Django serves app/project static files directly.

## Why GLIS keeps prefixed classes

GLIS still contains older Bootstrap-based screens while the redesigned public and portal screens use Tailwind/daisyUI. To prevent collisions with common Bootstrap class names such as `btn`, `card`, `table`, `modal`, `input`, and `badge`, the new design uses:

- Tailwind prefix: `tw:`
- daisyUI component prefix: `d-`
- Example: `tw:flex`, `tw:bg-base-100`, `tw:d-btn`, `tw:d-card`

Do not remove these prefixes while Bootstrap compatibility is still required.

## Themes

The committed stylesheet contains the GLIS themes:

- `glis`
- `glis-dark`

`static/js/app.js` synchronizes the existing light/dark preference with Bootstrap's `data-bs-theme` and daisyUI's `data-theme`.

## No npm requirement

The following build-only files are intentionally not part of the Django project anymore:

- `package.json`
- `package-lock.json`
- `static/src/tailwind.css`

The generated production stylesheet is version-controlled, so pulling the repository is enough to receive the UI.

## Deployment

For Vercel/WhiteNoise or another Django deployment, deploy exactly like the rest of the project:

```bash
python manage.py collectstatic --noinput
```

No Node build stage is required.

## Important

If a future UI change introduces a Tailwind/daisyUI class that is not already present in `static/css/glis-tailwind.css`, regenerate the production stylesheet separately before committing that UI change. Normal application developers and deployments still do not need npm.
