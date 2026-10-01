# Compact Bootstrap UI

GLIS uses Bootstrap **5.3.2** across the public site and authenticated portal. The migration keeps the existing pages, navigation, dashboard panels, ticket conversation/sidebar arrangement, creation and processing wizards, HTMX endpoints, permissions and form field names. English/LTR, Arabic/RTL and System/Light/Dark preferences remain supported. Conversation cards continue to fit their content.

## Assets and reference

| Supplied reference | Repository implementation |
| --- | --- |
| [Course Planner](https://course-planner-140256174016.asia-south1.run.app/) | Compact neutral surfaces, blue primary controls, small labels, inputs, buttons, tables and cards applied to GLIS's existing layout |
| [Bootstrap bundle 5.3.2](https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js) | Identical pinned local `static/js/bootstrap.bundle.min.js`, including Popper |
| [Reference style.css v1.97](https://course-planner-140256174016.asia-south1.run.app/static/css/style.css?v=1.97) | Adapted component rules and light/dark tokens in `static/css/style.css` |
| [Reference main.js v1.97](https://course-planner-140256174016.asia-south1.run.app/static/js/main.js?v=1.97) | Adapted reusable Bootstrap behavior in `static/js/main.js`; GLIS retains its own theme, navigation, CSRF and processing behavior |
| [Bootstrap CSS](https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css) / [RTL CSS](https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.rtl.min.css) | Identical pinned local `bootstrap.min.css` and `bootstrap.rtl.min.css`, selected by `components/bootstrap_styles.html` |

Local assets avoid a production dependency on changes or availability of the reference application. The reference's course-specific selectors, API/authentication behavior and unsafe HTML toast interpolation are omitted. Bootstrap's MIT license notices remain in the vendor files.

No Tailwind or DaisyUI stylesheet, dependency, compiler or build step is required. Historical database migrations with old theme names remain unchanged. Fixed GLIS layout extensions in `bootstrap-layout.css` preserve grid column counts, spans and media sizing that Bootstrap's standard utilities do not express. Existing page-specific CSS keeps branded public sections, dashboard panels, member tables and rich text layouts.

## Component behavior

| Area | Bootstrap implementation |
| --- | --- |
| Inputs, selects and files | `form-control`, `form-select`, small controls and shared labels/errors |
| Checkbox/radio groups | `form-check-input` on inputs only; separate choice containers and fieldsets retain label clicks, keyboard input and repeated values |
| Dialogs | `modal` / `modal-dialog` / `modal-content` / `modal-body`, declarative triggers and dismiss controls |
| Dropdowns and tabs | Bootstrap dropdowns and tab buttons, including validated/error member panels |
| Mobile portal navigation | Responsive Bootstrap offcanvas with desktop full/icon sidebar modes retained |
| Loading and feedback | Bootstrap spinners, alerts and safely rendered toasts |
| Step navigation and conversation | Small GLIS semantic components using Bootstrap colors and spacing; business state is unchanged |

`main.js` moves opened modals to the body so transformed cards cannot cover them. It preserves inherited HTMX target/swap/encoding/synchronization attributes and the dialog's original position. Before its containing workspace is replaced, it hides/disposes the modal, removes its backdrop and returns the element to that workspace. Member note controls retain their external form associations; Cancel/Escape restores unsaved values. Workflow validation can reopen the relevant modal after a server response.

## Development and deployment

1. Edit Django templates, widget classes and the shared CSS/JavaScript directly.
2. Run `python scripts/check_bootstrap_assets.py`, JavaScript syntax checks, Django checks/tests and the browser suite in `scripts/test_portal_ui.cjs`.
3. Pull the change and run `python manage.py collectstatic --noinput` during deployment. No new database migration is needed for this UI change.
4. Hard refresh browsers if static assets are cached. Bootstrap and reference adaptations have explicit version query strings; hashed static storage remains compatible.

Migration validation completed: the full 235-test Django suite passed with two existing SQLite concurrency skips, all 11 browser regression tests passed, and 107 templates compiled. Browser checks against 26 rendered Django page/view combinations covered portal and public CMS layouts, saved assignments and HTMX filters, member tabs, modal dismissal, light/dark mode and English/Arabic mobile navigation, with no JavaScript exceptions or horizontal overflow.

CI validates the Bootstrap boundary and browser regressions in `.github/workflows/bootstrap-ui.yml`. The existing Django/TPA regression workflow remains in place.
