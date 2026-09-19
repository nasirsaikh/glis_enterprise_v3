from apps.job_center.registry import register_job
from apps.tasks.services import generate_due_tasks


@register_job("tasks.generate_due")
def generate_due_tasks_job(**kwargs):
    return generate_due_tasks()
