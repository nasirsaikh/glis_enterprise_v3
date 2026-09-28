# Django 6.1 Compatibility Audit

Audit date: 2026-09-28

## Upgrade target

The project is pinned to **Django 6.1.1**.

Django 6.1 supports Python 3.12, 3.13 and 3.14. The repository intentionally keeps `requires-python = "==3.12.*"` in `pyproject.toml` for the deployment/Vercel baseline. A local Python 3.13 virtual environment is valid for Django 6.1.

The project-level Django 6.1 email deprecation has also been addressed: `glis/settings.py` now defines `MAILERS` while retaining the existing `EMAIL_*` **environment variable names** so deployed secrets/configuration do not need to change.

## Status definitions

- **Confirmed**: the package/project metadata explicitly declares Django 6.1 support.
- **Verify**: the pinned release does not explicitly declare Django 6.1 support, or its published compatibility metadata stops at an earlier Django release. This does not automatically mean it is broken; it means the combination must pass the GLIS test suite before production use.
- **Framework-neutral**: no Django compatibility declaration is expected; validate Python/platform compatibility through the package resolver and runtime tests.

## Confirmed Django 6.1 support

| Package | Pinned version | Status | Notes |
|---|---:|---|---|
| Django | 6.1.1 | Confirmed | Supports Python 3.12-3.14 |
| django-cms | 5.1.1 | Confirmed | PyPI classifier includes Django 6.1 |
| djangorestframework | 3.18.0 | Confirmed | Official requirements include Django 5.2, 6.0, 6.1 |
| django-filter | 26.1 | Confirmed | PyPI classifier includes Django 6.1 |
| django-htmx | 1.29.0 | Confirmed | PyPI classifier includes Django 6.1 |
| django-allauth | 65.19.1 | Confirmed | PyPI classifier includes Django 6.1 |
| mssql-django | 1.8.0 | Confirmed | Microsoft backend explicitly supports Django 5.2, 6.0, 6.1 and Python 3.10-3.14 |
| django-polymorphic | 4.11.7 | Confirmed | PyPI classifier includes Django 6.1 |
| django-treebeard | 5.3.1 | Confirmed | v5.3.1 metadata includes Django 6.1; MSSQL is an officially supported backend |
| django-stubs-ext | 6.1.0 | Confirmed | Project metadata includes Django 6.1 |
| djangocms-history | 3.0.0 | Confirmed | 3.x documentation supports Django 6.1 and django CMS 5.1 |
| djangocms-versioning | 2.7.0 | Confirmed | 2.x project metadata supports the Django 6.1 / django CMS 5.1 line |

## Packages requiring runtime verification

These packages are **not being declared incompatible**. Their pinned release metadata simply does not explicitly certify Django 6.1, so GLIS must validate them with `pip check`, Django system checks and the test suite.

| Package | Pinned version | Published support signal / concern |
|---|---:|---|
| django-admin-sortable2 | 2.3.1 | Published classifiers stop at Django 5.2 |
| django-ckeditor-5 | 0.2.20 | Does not explicitly advertise Django 6.1 |
| django-classy-tags | 4.1.0 | Published classifiers stop at Django 4.2 |
| django-csp | 4.0 | No Django 6.1 declaration confirmed in this audit |
| django-entangled | 0.7 | No Django 6.1 declaration confirmed in this audit |
| django-environ | 0.12.1 | No Django 6.1 declaration confirmed in this audit |
| django-filer | 3.5.1 | No Django 6.1 declaration confirmed in this audit |
| django-formtools | 2.7 | Published classifiers stop at Django 6.0 |
| django-fsm-2 | 4.2.4 | No Django 6.1 declaration confirmed in this audit |
| django-json-widget | 2.1.1 | No explicit Django 6.1 support declaration found |
| django-location-field | 2.7.3 | Old release; published Python classifiers stop at Python 3.11 |
| django-parler | 2.4 | No explicit Django 6.1 declaration confirmed in this audit |
| django-sekizai | 4.1.0 | Published classifiers are older; django CMS depends on Sekizai, but the individual package metadata is not current to 6.1 |
| django-storages | 1.14.6 | Published classifiers stop at Django 5.1 |
| django-summernote | 0.8.20.0 | High-risk legacy dependency: release is from 2021 and metadata is from much older Django/Python generations |
| django-taggit | 6.1.0 | Published classifiers stop at Django 5.0 |
| django-visitor-tracker | 0.1.0 | No current Django 6.1 support declaration confirmed |
| django-widget-tweaks | 1.5.1 | Published classifiers stop at Django 5.2 |
| djangocms-alias | 3.1.1 | Published classifiers stop at Django 6.0 |
| djangocms-attributes-field | 4.1.2 | No explicit Django 6.1 declaration confirmed in this audit |
| djangocms-audio | 2.1.1 | No explicit Django 6.1 declaration confirmed in this audit |
| djangocms-file | 4.0.1 | Recent release, but no explicit Django 6.1 classifier confirmed |
| djangocms-frontend | 2.5.1 | Published classifier metadata stops at Django 5.2, while django CMS support reaches 5.1 |
| djangocms-icon | 2.1.1 | Published classifiers are substantially older than Django 6.1 |
| djangocms-link | 5.2.0 | Release metadata stops at Django 5.2; upstream development metadata has since added Django 6.1 |
| djangocms-moderation | 2.5.0 | No explicit Django 6.1 declaration confirmed in this audit |
| djangocms-picture | 4.1.1 | No explicit Django 6.1 declaration confirmed in this audit |
| djangocms-rest | 1.2.0 | No explicit Django 6.1 declaration confirmed in this audit |
| djangocms-simple-admin-style | 2.0.2 | No explicit Django 6.1 declaration confirmed in this audit |
| djangocms-snippet | 5.0.2 | Published Django classifiers are old; additionally this plugin should remain restricted because it allows privileged raw markup/script content |
| djangocms-text | 0.9.11 | No explicit Django 6.1 declaration confirmed in this audit |
| djangocms-text-ckeditor5 | 0.48.0 | Current package but no explicit Django 6.1 classifier confirmed |
| djangocms-transfer | 2.0.1 | Published classifiers stop at Django 5.2 |
| djangocms-video | 3.1.0 | Older plugin with no explicit Django 6.1 support declaration |
| djangorestframework-simplejwt | 5.5.1 | Python 3.13 is declared, but Django 6.1 is not explicitly advertised |
| drf-spectacular | 0.30.0 | Important: official support lists Django only through 6.0 and DRF only through 3.17, while GLIS pins DRF 3.18.0 |
| easy-thumbnails | 2.10.1 | Changelog explicitly added Django 5.2; no 6.1 support statement yet |
| whitenoise | 6.12.0 | Modern release, but this audit did not find an explicit Django 6.1 classifier |
| pytest-django | 4.14.0 | Must be verified by the test environment against Django 6.1 |

## Framework-neutral dependencies

Packages such as aiohttp, APScheduler, ChromaDB, cryptography, httpx, NumPy, pandas, Pillow, Plotly, psycopg, pyodbc, Pydantic, SQLAlchemy, Ollama, Vanna and the OpenTelemetry stack do not normally couple to a specific Django release. They still need to resolve for the selected Python/platform.

Use `pip check` after installation to detect dependency metadata conflicts.

## Project code audit for Django 6.1 removals

Repository searches did not find GLIS usage of the following removed/deprecated upgrade hotspots:

- `django.contrib.staticfiles.finders.find(..., all=...)`
- reliance on the old `django.contrib.auth.login()` `request.user` fallback
- PostgreSQL aggregate `ordering=` arguments
- `RemoteUserMiddleware` subclass behavior affected by the 6.1 change
- direct `mail.get_connection()` usage
- email `connection=` arguments

The active notification email job uses `EmailMultiAlternatives` with the default backend, which is compatible with the new default `MAILERS` alias.

## SQL Server note

`mssql-django 1.8.0` explicitly supports Django 6.1. Django 6.1 introduced database-level `on_delete` actions, but GLIS does not need to adopt them. Continue using the existing Python-level `models.CASCADE`, `PROTECT`, `SET_NULL`, etc. unless SQL Server support for a new database-level action has been verified.

## Mandatory validation after pulling the upgrade

Use a clean virtual environment if possible.

```powershell
python --version
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check

python -Wd manage.py check
python manage.py makemigrations --check
python manage.py test
```

For the TPA module specifically:

```powershell
python manage.py test apps.tpa
```

Then exercise these integration paths manually before production promotion:

1. Django Admin login and changelists.
2. django CMS page tree, edit mode, text/link/image/file/video/icon/snippet plugins.
3. Public site rendering in English and Arabic.
4. Portal login, navigation, tickets, attachments and notifications.
5. Google/Microsoft allauth login.
6. DRF schema generation and JWT authentication.
7. SQLite development database.
8. SQL Server staging database through `mssql-django`.
9. Email notification job through the Django 6.1 `MAILERS` configuration.
10. TPA dashboard, policy access, transaction create/submit and linked ticket.

## Release decision

Django 6.1.1 is appropriate for the GLIS **core stack**, but the repository should not be described as having 100% upstream-certified Django 6.1 support because multiple secondary CMS/UI packages have not updated their published support classifiers.

Production acceptance requires the clean-environment installation, `pip check`, full Django test suite and the CMS/API/manual integration checks above. Any failure in an amber dependency should be upgraded/replaced or isolated before production deployment.
