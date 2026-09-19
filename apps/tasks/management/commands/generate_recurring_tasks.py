from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.tasks.services import generate_due_tasks


class Command(BaseCommand):
    help = "Generate recurring task occurrences whose create-ahead date has been reached."

    def add_arguments(self, parser):
        parser.add_argument(
            "--as-of",
            dest="as_of",
            help="Optional YYYY-MM-DD date used instead of today's local date.",
        )

    def handle(self, *args, **options):
        as_of = None
        if options.get("as_of"):
            try:
                as_of = date.fromisoformat(options["as_of"])
            except ValueError as exc:
                raise CommandError("--as-of must use YYYY-MM-DD format.") from exc

        result = generate_due_tasks(as_of=as_of)
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {result['templates_processed']} recurring template(s); "
                f"created {result['created']} task occurrence(s)."
            )
        )
        for error in result["errors"]:
            self.stderr.write(
                self.style.ERROR(
                    f"Recurring task #{error['recurring_task_id']}: {error['error']}"
                )
            )
        if result["errors"]:
            raise CommandError("One or more recurring task templates failed to generate.")
