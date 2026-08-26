from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from apps.tickets.models import Notification, Ticket, TicketEscalation, TicketEvent
from services.ticket_workflow import notify_users


class Command(BaseCommand):
    help = "Process SLA escalation levels, approval reminders and category-driven automatic closure. Run every five minutes."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        escalation_count = 0
        auto_closed = 0
        active = Ticket.objects.exclude(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED]).select_related("sla_policy", "assignee__profile", "category").prefetch_related("sla_policy__escalation_levels__target_users", "sla_policy__escalation_levels__target_groups__members")
        for ticket in active:
            if not ticket.sla_policy or not ticket.resolution_due_at:
                continue
            for rule in ticket.sla_policy.escalation_levels.filter(is_active=True):
                if now < ticket.resolution_due_at + timedelta(minutes=rule.trigger_after_minutes):
                    continue
                escalation, created = TicketEscalation.objects.get_or_create(ticket=ticket, rule=rule, defaults={"message": rule.notification_message or f"{ticket.reference} breached SLA escalation level {rule.level}."})
                if not created:
                    continue
                recipients = list(rule.target_users.filter(is_active=True))
                for group in rule.target_groups.all():
                    recipients.extend(group.members.filter(is_active=True))
                if rule.include_assignee_reporting_manager and ticket.assignee and getattr(ticket.assignee, "profile", None) and ticket.assignee.profile.reporting_manager:
                    recipients.append(ticket.assignee.profile.reporting_manager)
                escalation.escalated_to_users.add(*recipients)
                notify_users(recipients, ticket=ticket, kind="sla", title=f"SLA escalation L{rule.level}: {ticket.reference}", body=escalation.message, send_email_message=True)
                TicketEvent.objects.create(ticket=ticket, event_type="sla_escalation", summary=f"SLA escalated to level {rule.level}", details={"rule": rule.pk})
                escalation_count += 1

        resolved = Ticket.objects.filter(status=Ticket.Status.RESOLVED, resolved_at__isnull=False).select_related("category", "requester")
        for ticket in resolved:
            if ticket.resolved_at + timedelta(days=ticket.category.auto_close_days) <= now:
                ticket.status, ticket.closed_at = Ticket.Status.CLOSED, now
                ticket.save(update_fields=["status", "closed_at", "updated_at"])
                TicketEvent.objects.create(ticket=ticket, event_type="auto_closed", summary=f"Automatically closed after {ticket.category.auto_close_days} days")
                notify_users([ticket.requester], ticket=ticket, kind="update", title=f"Ticket automatically closed: {ticket.reference}", body=f"Reopening is allowed for {ticket.category.reopen_allowed_days} days.", send_email_message=ticket.category.send_update_email)
                auto_closed += 1

        self.stdout.write(self.style.SUCCESS(f"Processed {escalation_count} SLA escalation(s) and {auto_closed} automatic closure(s)."))
