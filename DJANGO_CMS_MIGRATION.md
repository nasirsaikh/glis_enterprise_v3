# GLIS local CMS -> django CMS migration

This branch replaces the local `apps.cms` application namespace with `apps.app_settings` and introduces the real django CMS package.

## Important: existing databases

The former local app used Django's app label `cms`. Therefore existing databases may contain both:

- legacy tables named `cms_*` (including `cms_page`), and
- `django_migrations` rows whose `app` value is `cms`.

The real django CMS also uses the app label/table prefix `cms`. **Do not run `python manage.py migrate` against an existing GLIS database until the legacy tables/data have been moved to the `app_settings_*` namespace and the old migration-history rows have been reconciled.**

For a new/empty development database, install requirements, generate the initial `app_settings` migration, then migrate normally:

```bash
pip install -r requirements.txt
python manage.py makemigrations app_settings
python manage.py migrate
python manage.py cms check
python manage.py createsuperuser
python manage.py runserver
```

For an existing production/test database, first take a full database backup. Then migrate the legacy `cms_*` tables/data to `app_settings_*` using a reviewed database migration appropriate to the database engine. SQL Server requires special attention because django CMS does not list SQL Server among its officially supported production databases.

## URL transition

During migration:

- existing GLIS public pages remain served by `apps.app_settings` at their existing URLs;
- django CMS pages are mounted under `/pages/`;
- after content has been migrated and verified, django CMS can become the root catch-all URL and the legacy Page/PageSection models can be retired.

## Templates

The branch includes:

- `templates/cms/glis_page.html`
- `templates/cms/glis_home.html`
- `templates/cms/glis_portal_page.html`

The public GLIS shell now loads the django CMS toolbar and sekizai CSS/JS blocks while preserving the existing Bootstrap/GLIS theme.
