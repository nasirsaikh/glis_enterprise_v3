from django.apps import AppConfig


class TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tasks"
    verbose_name = "Task Management"

    def ready(self):
        from . import signals  # noqa: F401
