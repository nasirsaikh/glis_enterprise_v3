from django.contrib import admin, messages

from .models import RecurringTask, Task
from .services import generate_due_tasks


@admin.register(RecurringTask)
class RecurringTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "recurrence",
        "first_due_date",
        "create_days_before",
        "project",
        "category",
        "is_active",
    )
    list_filter = ("recurrence", "is_active", "priority", "project", "category")
    search_fields = ("title", "description", "owner__email", "owner__first_name", "owner__last_name")
    filter_horizontal = ("tagged_users",)
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        result = generate_due_tasks()
        if result["created"]:
            self.message_user(request, f"Generated {result['created']} due task occurrence(s) and linked ticket(s).", messages.SUCCESS)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "due_date", "owner", "ticket", "recurring_task", "is_deleted", "created_at")
    list_filter = ("is_deleted", "priority", "project", "category", "due_date")
    search_fields = ("title", "description", "ticket__reference", "owner__email")
    filter_horizontal = ("tagged_users",)
    readonly_fields = ("recurring_task", "occurrence_date", "ticket", "created_at", "updated_at")
