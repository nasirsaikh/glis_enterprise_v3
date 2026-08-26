from rest_framework.views import exception_handler


def glis_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return None

    response.data = {
        "success": False,
        "status_code": response.status_code,
        "errors": response.data,
    }

    return response