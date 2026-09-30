from django.utils import translation


class RequestLocaleMiddleware:
    """Keep application labels and URLs in the locale selected by the visitor.

    CMS may activate a published content fallback while constructing a lazy
    response. Its content can fall back without changing the public shell,
    translated links, HTMX endpoints or response language.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _restore(request):
        if getattr(request, "LANGUAGE_CODE", None):
            translation.activate(request.LANGUAGE_CODE)

    def process_template_response(self, request, response):
        self._restore(request)
        return response

    def __call__(self, request):
        response = self.get_response(request)
        self._restore(request)
        return response
