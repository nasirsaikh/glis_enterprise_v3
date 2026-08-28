from django import forms
from apscheduler.triggers.cron import CronTrigger

from .models import ScheduledJob


class ScheduledJobForm(forms.ModelForm):
    class Meta:
        model = ScheduledJob
        fields = "__all__"

    def clean_cron_expression(self):
        expression = self.cleaned_data["cron_expression"].strip()
        parts = expression.split()
        if len(parts) != 5:
            raise forms.ValidationError(
                "Cron expression must contain exactly 5 fields: "
                "minute hour day-of-month month day-of-week."
            )
        minute, hour, day, month, weekday = parts
        try:
            CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=weekday,
                timezone=self.cleaned_data.get("timezone") or "Asia/Muscat",
            )
        except Exception as exc:
            raise forms.ValidationError(f"Invalid cron expression: {exc}")
        return expression

    def clean(self):
        cleaned = super().clean()
        job_type = cleaned.get("job_type")

        if job_type == ScheduledJob.JobType.PYTHON and not cleaned.get("handler"):
            self.add_error("handler", "Python jobs require a registered handler.")

        if job_type == ScheduledJob.JobType.SQL and not cleaned.get("sql_query"):
            self.add_error("sql_query", "SQL jobs require SQL text.")

        if job_type == ScheduledJob.JobType.STORED_PROCEDURE and not cleaned.get("stored_procedure"):
            self.add_error("stored_procedure", "Stored procedure jobs require a procedure name.")

        if job_type == ScheduledJob.JobType.HTTP and not cleaned.get("http_url"):
            self.add_error("http_url", "HTTP jobs require a URL.")

        return cleaned
