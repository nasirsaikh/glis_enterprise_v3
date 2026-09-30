from django.http import HttpResponse


class HtmxRedirectMiddleware:
    """Turn transaction-flow redirects into full-page navigations for HTMX forms."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        is_transaction_request = "/tpa/transactions/" in request.path
        is_htmx_request = request.headers.get("HX-Request", "").lower() == "true"
        is_redirect = response.status_code in {301, 302, 303, 307, 308}
        if is_transaction_request and is_htmx_request and is_redirect and response.has_header("Location"):
            redirect_response = HttpResponse(status=204)
            redirect_response["HX-Redirect"] = response["Location"]
            return redirect_response
        return response
