from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .forms import ScheduledJobForm
from .models import JobExecution, ScheduledJob, SchedulerLock,QueuedJob
from .registry import get_registered_jobs
from .scheduler import get_scheduler, run_job_now, sync_jobs


@admin.register(ScheduledJob)
class ScheduledJobAdmin(admin.ModelAdmin):
    form = ScheduledJobForm

    list_display = (
        "name",
        "job_type",
        "cron_expression",
        "enabled",
        "status_badge",
        "last_run_at",
        "next_run_at",
        "run_now_link",
    )
    list_filter = ("job_type", "enabled", "last_status")
    search_fields = ("name", "description", "handler")
    readonly_fields = (
        "last_run_at",
        "next_run_at",
        "last_status",
        "last_message",
        "registered_handlers",
        "created_at",
        "updated_at",
    )
    actions = (
        "run_selected_now",
        "enable_selected",
        "disable_selected",
        "synchronize_scheduler",
    )

    fieldsets = (
        ("Job", {
            "fields": ("name", "description", "job_type", "enabled"),
        }),
        ("Python", {
            "fields": ("handler", "registered_handlers", "parameters"),
        }),
        ("Database", {
            "fields": ("database_alias", "sql_query", "stored_procedure"),
        }),
        ("HTTP", {
            "fields": ("http_url", "http_method", "http_headers", "http_body"),
        }),
        ("Schedule", {
            "fields": (
                "cron_expression",
                "timezone",
                "max_instances",
                "misfire_grace_seconds",
                "coalesce",
            ),
        }),
        ("Retry / Timeout", {
            "fields": (
                "timeout_seconds",
                "retry_count",
                "retry_delay_seconds",
            ),
        }),
        ("Status", {
            "fields": (
                "last_run_at",
                "next_run_at",
                "last_status",
                "last_message",
            ),
        }),
        ("Audit", {
            "fields": ("created_by", "created_at", "updated_at"),
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:job_id>/run-now/",
                self.admin_site.admin_view(self.run_now_view),
                name="job_center_scheduledjob_run_now",
            ),
        ]
        return custom + urls

    def registered_handlers(self, obj=None):
        names = sorted(get_registered_jobs().keys())
        if not names:
            return "No handlers registered."
        return format_html(
            "<br>".join("<code>{}</code>".format(name) for name in names)
        )
    registered_handlers.short_description = "Registered Python handlers"

    def status_badge(self, obj):
        status = obj.last_status or "Never run"
        if status == JobExecution.Status.SUCCESS:
            return format_html('<strong style="color:#198754">● Success</strong>')
        if status in {JobExecution.Status.FAILED, JobExecution.Status.TIMEOUT}:
            return format_html('<strong style="color:#dc3545">● {}</strong>', status.title())
        if status == JobExecution.Status.RUNNING:
            return format_html('<strong style="color:#0d6efd">● Running</strong>')
        return status
    status_badge.short_description = "Status"

    def run_now_link(self, obj):
        url = reverse("admin:job_center_scheduledjob_run_now", args=[obj.pk])
        return format_html('<a class="button" href="{}">Run now</a>', url)
    run_now_link.short_description = "Action"

    def run_now_view(self, request, job_id):
        try:
            run_job_now(job_id, request.user.pk)
            self.message_user(
                request,
                "Job submitted for background execution.",
                messages.SUCCESS,
            )
        except Exception as exc:
            self.message_user(request, str(exc), messages.ERROR)

        return redirect(
            reverse("admin:job_center_scheduledjob_changelist")
        )

    @admin.action(description="▶ Run selected jobs now")
    def run_selected_now(self, request, queryset):
        submitted = 0
        for job in queryset:
            try:
                run_job_now(job.pk, request.user.pk)
                submitted += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f"{job.name}: {exc}",
                    messages.ERROR,
                )

        if submitted:
            self.message_user(
                request,
                f"{submitted} job(s) submitted.",
                messages.SUCCESS,
            )

    @admin.action(description="Enable selected jobs")
    def enable_selected(self, request, queryset):
        queryset.update(enabled=True)
        sync_jobs()
        self.message_user(request, "Selected jobs enabled.", messages.SUCCESS)

    @admin.action(description="Disable selected jobs")
    def disable_selected(self, request, queryset):
        queryset.update(enabled=False)
        sync_jobs()
        self.message_user(request, "Selected jobs disabled.", messages.SUCCESS)

    @admin.action(description="Synchronize scheduler")
    def synchronize_scheduler(self, request, queryset):
        sync_jobs()
        self.message_user(request, "Scheduler synchronized.", messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        try:
            sync_jobs()
        except Exception as exc:
            self.message_user(request, f"Saved, but scheduler sync failed: {exc}", messages.WARNING)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        try:
            sync_jobs()
        except Exception as exc:
            self.message_user(request, f"Saved, but scheduler sync failed: {exc}", messages.WARNING)
        return super().response_change(request, obj)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        try:
            sync_jobs()
        except Exception:
            pass


@admin.register(JobExecution)
class JobExecutionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "status_badge",
        "trigger_type",
        "attempt",
        "started_at",
        "finished_at",
        "duration_seconds",
    )
    list_filter = ("status", "trigger_type", "job")
    search_fields = ("job__name", "error", "output")
    date_hierarchy = "created_at"

    readonly_fields = (
        "job",
        "status",
        "trigger_type",
        "attempt",
        "started_at",
        "finished_at",
        "duration_seconds",
        "parameters",
        "result",
        "output",
        "error",
        "traceback",
        "triggered_by",
        "created_at",
    )

    def status_badge(self, obj):
        if obj.status == JobExecution.Status.SUCCESS:
            return format_html('<strong style="color:#198754">● Success</strong>')
        if obj.status in {JobExecution.Status.FAILED, JobExecution.Status.TIMEOUT}:
            return format_html('<strong style="color:#dc3545">● {}</strong>', obj.status.title())
        if obj.status == JobExecution.Status.RUNNING:
            return format_html('<strong style="color:#0d6efd">● Running</strong>')
        return obj.status
    status_badge.short_description = "Status"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SchedulerLock)
class SchedulerLockAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "heartbeat_at", "expires_at", "scheduler_local_status")
    readonly_fields = ("name", "owner", "heartbeat_at", "expires_at", "updated_at")

    def scheduler_local_status(self, obj):
        return "Running" if get_scheduler() is not None else "Not leader in this process"
    scheduler_local_status.short_description = "Local scheduler"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# admin.py

from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.utils.timezone import now
from django.forms import JSONField
from .models import QueuedJob


class QueuedJobForm(forms.ModelForm):
    class Meta:
        model = QueuedJob
        fields = "__all__"
        widgets = {
            "parameters": forms.Textarea(attrs={"rows": 5, "cols": 80}),
            "result": forms.Textarea(attrs={"rows": 5, "cols": 80}),
        }


@admin.register(QueuedJob)
class QueuedJobAdmin(admin.ModelAdmin):
    form = QueuedJobForm
    
    list_display = [
        "id",
        "handler",
        "status",
        "priority",
        "run_after",
        "attempts",
        "max_attempts",
        "created_at",
        "started_at",
        "finished_at",
    ]
    
    list_display_links = ["id", "handler"]
    
    list_filter = [
        "status",
        "priority",
        "created_at",
        "started_at",
        "finished_at",
    ]
    
    search_fields = [
        "handler",
        "error",
    ]
    
    readonly_fields = [
        "status",
        "attempts",
        "locked_at",
        "started_at",
        "finished_at",
        "result",
        "error",
        "created_at",
    ]
    
    date_hierarchy = "created_at"
    
    ordering = ["-created_at"]
    
    actions = [
        "mark_as_pending",
        "mark_as_cancelled",
        "reset_attempts",
    ]
    
    @admin.action(description="Mark selected jobs as pending")
    def mark_as_pending(self, request, queryset):
        updated = queryset.update(
            status=QueuedJob.Status.PENDING,
            locked_at=None,
            error="",
        )
        self.message_user(request, f"{updated} jobs marked as pending.")
    
    @admin.action(description="Mark selected jobs as cancelled")
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(
            status=QueuedJob.Status.CANCELLED,
            finished_at=now(),
        )
        self.message_user(request, f"{updated} jobs marked as cancelled.")
    
    @admin.action(description="Reset attempts counter")
    def reset_attempts(self, request, queryset):
        updated = queryset.update(attempts=0)
        self.message_user(request, f"Attempts reset for {updated} jobs.")
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return True