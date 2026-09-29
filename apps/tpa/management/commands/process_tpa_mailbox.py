from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.tpa.services.mailbox import poll_inbound_mailbox


class Command(BaseCommand):
    help = (
        "Synchronize the configured TPA mailbox. Microsoft Graph application authentication "
        "is the primary provider; legacy IMAP remains an explicit fallback."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help=(
                "GLIS user used as the ingestion actor/requester. "
                "Defaults to the first active superuser."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional maximum messages. Defaults to TPA_MAIL_MAX_MESSAGES_PER_RUN.",
        )
        parser.add_argument(
            "--no-ai",
            action="store_true",
            help="Store unread emails and attachments without AI/workflow processing.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options.get("username")
        if username:
            actor = User.objects.filter(username=username, is_active=True).first()
            if actor is None:
                raise CommandError(f"Active user {username!r} was not found.")
        else:
            actor = (
                User.objects.filter(is_superuser=True, is_active=True)
                .order_by("pk")
                .first()
            )
            if actor is None:
                raise CommandError(
                    "No active superuser exists. Pass --username with an active GLIS user."
                )

        result = poll_inbound_mailbox(
            actor=actor,
            limit=(max(int(options["limit"]), 1) if options["limit"] else None),
            process_ai=(False if options["no_ai"] else None),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "TPA mailbox polling completed: "
                f"created={result['created']}, "
                f"processed={result['processed']}, "
                f"review={result.get('review', 0)}, "
                f"ignored={result.get('ignored', 0)}, "
                f"failed={result.get('failed', 0)}, "
                f"skipped={result.get('skipped', 0)}."
            )
        )
