from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render


class HtmxRedirectMiddleware:
    """Keep creation/login redirects working and show workspace access errors inline."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        is_transaction_request = "/tpa/transactions/" in request.path
        is_htmx_request = request.headers.get("HX-Request", "").lower() == "true"
        is_redirect = response.status_code in {301, 302, 303, 307, 308}
        if "/tpa/" in request.path and is_htmx_request and is_redirect and response.has_header("Location"):
            redirect_response = HttpResponse(status=204)
            redirect_response["HX-Redirect"] = response["Location"]
            return redirect_response
        return response

    def process_exception(self, request, exception):
        if (
            request.headers.get("HX-Request", "").lower() == "true"
            and "/tpa/transactions/" in request.path
            and isinstance(exception, (PermissionDenied, Http404))
        ):
            response = render(
                request, "components/request_error.html",
                {"request_error": str(exception) or "You do not have access to this action."},
                status=403 if isinstance(exception, PermissionDenied) else 404,
            )
            response["HX-Retarget"] = "#transaction-request-error"
            response["HX-Reswap"] = "innerHTML"
            return response
        return None
