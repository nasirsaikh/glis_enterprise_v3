from django.contrib.auth import logout
from django.shortcuts import redirect
from django.conf import settings


class LockedAccountMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def locked(request):
        return request.user.is_authenticated and getattr(getattr(request.user, 'profile', None), 'is_locked', False)

    def __call__(self, request):
        if self.locked(request):
            logout(request)
            return redirect(settings.LOGIN_URL)
        response = self.get_response(request)
        if self.locked(request):
            logout(request)
            return redirect(settings.LOGIN_URL)
        return response
