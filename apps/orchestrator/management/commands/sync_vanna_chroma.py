from django.core.management.base import BaseCommand, CommandError

from apps.orchestrator.chroma_memory import ChromaDomainMemory
from apps.orchestrator.models import AIDomain, VannaSettings


class Command(BaseCommand):
    help = "Synchronize approved Admin training and policies into each Vanna ChromaDB collection."

    def add_arguments(self, parser):
        parser.add_argument("--domain", help="Optional AI domain slug.")

    def handle(self, *args, **options):
        domains = AIDomain.objects.filter(is_active=True)
        if options.get("domain"):
            domains = domains.filter(slug=options["domain"])
        if not domains.exists():
            raise CommandError("No matching active AI domain was found.")

        settings = VannaSettings.load()
        total = 0
        for domain in domains:
            memory = ChromaDomainMemory(domain=domain, vanna_settings=settings)
            changed = memory.sync_from_admin()
            total += changed
            self.stdout.write(
                self.style.SUCCESS(
                    f"{domain.slug}: {changed} changed document(s); "
                    f"collection={memory.collection_name}; total={memory.collection.count()}"
                )
            )
        self.stdout.write(self.style.SUCCESS(f"ChromaDB synchronization complete: {total} change(s)."))
