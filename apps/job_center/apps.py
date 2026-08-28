import os
import sys
import threading

from django.apps import AppConfig
from django.conf import settings


class JobCenterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.job_center"
    verbose_name = "Job Center"

    _startup_lock = threading.Lock()
    _started = False

    def ready(self):
        from . import jobs  # noqa: F401

        if not getattr(settings, "JOB_CENTER_ENABLED", True):
            return

        # Prevent scheduler startup for commands where DB/app startup side effects are undesirable.
        blocked_commands = {
            "makemigrations",
            "migrate",
            "collectstatic",
            "shell",
            "dbshell",
            "test",
            "check",
            "showmigrations",
        }
        if len(sys.argv) > 1 and sys.argv[1] in blocked_commands:
            return

        # Django development autoreloader launches a parent process and a child process.
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
            return

        with self._startup_lock:
            if self.__class__._started:
                return

            from .scheduler import start_scheduler
            start_scheduler()
            self.__class__._started = True
