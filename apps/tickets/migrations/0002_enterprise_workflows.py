import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(name="ApprovalWorkflow", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("name", models.CharField(max_length=160)), ("description", models.TextField(blank=True)), ("is_active", models.BooleanField(default=True)),
        ]),
        migrations.CreateModel(name="SLAEscalationRule", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("level", models.PositiveSmallIntegerField(default=1)), ("trigger_after_minutes", models.PositiveIntegerField(help_text="Minutes after the relevant SLA due time.")),
            ("include_assignee_reporting_manager", models.BooleanField(default=False)), ("notification_message", models.CharField(blank=True, max_length=255)), ("is_active", models.BooleanField(default=True)),
            ("policy", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="escalation_levels", to="tickets.slapolicy")),
            ("target_groups", models.ManyToManyField(blank=True, related_name="sla_escalation_rules", to="tickets.supportgroup")),
            ("target_users", models.ManyToManyField(blank=True, related_name="sla_escalation_rules", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ("policy", "level")}),
        migrations.CreateModel(name="ApprovalStep", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("sequence", models.PositiveSmallIntegerField()), ("name", models.CharField(max_length=160)), ("approvals_required", models.PositiveSmallIntegerField(default=1)),
            ("escalation_after_hours", models.PositiveSmallIntegerField(default=24)), ("rejection_ends_workflow", models.BooleanField(default=True)),
            ("workflow", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="tickets.approvalworkflow")),
            ("approver_groups", models.ManyToManyField(blank=True, related_name="ticket_approval_steps", to="tickets.supportgroup")),
            ("approver_users", models.ManyToManyField(blank=True, related_name="ticket_approval_steps", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ("workflow", "sequence")}),
        migrations.AddField(model_name="category", name="approval_workflow", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="categories", to="tickets.approvalworkflow")),
        migrations.AddField(model_name="category", name="auto_close_days", field=models.PositiveSmallIntegerField(default=7)),
        migrations.AddField(model_name="category", name="default_groups", field=models.ManyToManyField(blank=True, related_name="default_for_categories", to="tickets.supportgroup")),
        migrations.AddField(model_name="category", name="default_user", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="default_categories", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="category", name="reopen_allowed_days", field=models.PositiveSmallIntegerField(default=14)),
        migrations.AddField(model_name="category", name="required_documents", field=models.JSONField(blank=True, default=list, help_text="Admin-driven attachment definitions used by the ticket form.")),
        migrations.AddField(model_name="category", name="send_initial_email", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="category", name="send_update_email", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="ticket", name="approval_state", field=models.CharField(choices=[("not_required", "Not required"), ("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], db_index=True, default="not_required", max_length=20)),
        migrations.AddField(model_name="ticket", name="assignees", field=models.ManyToManyField(blank=True, related_name="multi_assigned_tickets", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="ticketattachment", name="source_field", field=models.CharField(blank=True, max_length=80)),
        migrations.CreateModel(name="TicketApproval", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("skipped", "Skipped")], default="pending", max_length=20)),
            ("decided_at", models.DateTimeField(blank=True, null=True)), ("note", models.TextField(blank=True)),
            ("approver", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_approvals", to=settings.AUTH_USER_MODEL)),
            ("step", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_approvals", to="tickets.approvalstep")),
            ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="approvals", to="tickets.ticket")),
        ], options={"ordering": ("step__sequence", "created_at")}),
        migrations.CreateModel(name="TicketEscalation", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("message", models.CharField(max_length=255)), ("rule", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_escalations", to="tickets.slaescalationrule")),
            ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="escalations", to="tickets.ticket")),
            ("escalated_to_users", models.ManyToManyField(blank=True, related_name="ticket_escalations", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="TicketShare", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)), ("expires_at", models.DateTimeField()), ("is_active", models.BooleanField(default=True)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_ticket_shares", to=settings.AUTH_USER_MODEL)),
            ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="received_ticket_shares", to=settings.AUTH_USER_MODEL)),
            ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shares", to="tickets.ticket")),
        ]),
        migrations.CreateModel(name="Notification", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("kind", models.CharField(choices=[("info", "Information"), ("assignment", "Assignment"), ("approval", "Approval"), ("sla", "SLA escalation"), ("update", "Ticket update")], default="info", max_length=30)),
            ("title", models.CharField(max_length=160)), ("body", models.CharField(blank=True, max_length=500)), ("link", models.CharField(blank=True, max_length=255)), ("read_at", models.DateTimeField(blank=True, null=True)),
            ("ticket", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="tickets.ticket")),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="glis_notifications", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ("-created_at",)}),
        migrations.AddConstraint(model_name="slaescalationrule", constraint=models.UniqueConstraint(fields=("policy", "level"), name="unique_sla_policy_level")),
        migrations.AddConstraint(model_name="approvalstep", constraint=models.UniqueConstraint(fields=("workflow", "sequence"), name="unique_approval_workflow_sequence")),
        migrations.AddConstraint(model_name="ticketapproval", constraint=models.UniqueConstraint(fields=("ticket", "step", "approver"), name="unique_ticket_step_approver")),
        migrations.AddConstraint(model_name="ticketescalation", constraint=models.UniqueConstraint(fields=("ticket", "rule"), name="unique_ticket_escalation_rule")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["user", "read_at", "-created_at"], name="tickets_not_user_id_17f4ba_idx")),
    ]
