# Bootstrap Multiselect assets

Bootstrap Multiselect **v2.0.0** (Bootstrap 5 release) is bundled with jQuery
**v3.7.1**. The upstream source and license headers are retained. The only bundle
integration is the final `noConflict(true)` call, which exposes `glisJQuery`
without replacing existing Django/CMS `$` or `jQuery` globals.

Upstream: https://github.com/davidstutz/bootstrap-multiselect/tree/v2.0.0

jQuery source: Django's vendored upstream jQuery 3.7.1 distribution.
jQuery license: `jquery-LICENSE.txt`.

`static/js/searchable-selects.js` initializes the plugin on portal/public
multi-selects and preserves native values, form validation and HTMX changes.
Django admin's built-in autocomplete and filtered select widgets keep their
existing search behavior.
