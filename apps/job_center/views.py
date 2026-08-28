from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import JobExecution, ScheduledJob
from .scheduler import get_scheduler, run_job_now


@staff_member_required
def dashboard_api(request):
    today = timezone.localdate()

    data = {
        "scheduler_running_in_this_process": get_scheduler() is not None,
        "jobs_total": ScheduledJob.objects.count(),
        "jobs_enabled": ScheduledJob.objects.filter(enabled=True).count(),
        "executions_running": JobExecution.objects.filter(status=JobExecution.Status.RUNNING).count(),
        "executions_failed_today": JobExecution.objects.filter(
            created_at__date=today,
            status__in=[JobExecution.Status.FAILED, JobExecution.Status.TIMEOUT],
        ).count(),
        "executions_success_today": JobExecution.objects.filter(
            created_at__date=today,
            status=JobExecution.Status.SUCCESS,
        ).count(),
    }
    return JsonResponse(data)


@staff_member_required
@require_POST
def run_now_api(request, pk):
    job = get_object_or_404(ScheduledJob, pk=pk)
    run_job_now(job.pk, request.user.pk)
    return JsonResponse({
        "success": True,
        "message": f"{job.name} submitted.",
    })
