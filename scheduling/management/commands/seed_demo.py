from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from scheduling.demo_data import demo_walkthrough, seed_demo


class Command(BaseCommand):
    help = "Seed fictional demo accounts covering scheduling features; reruns preserve manual edits."
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument("--week", help="Week containing YYYY-MM-DD; defaults to Halifax's current week on first run.")
        parser.add_argument("--reset", action="store_true",
                            help="Restore only seed-owned demo accounts, deleting their manual schedule edits.")

    def handle(self, *args, **options):
        try:
            result = seed_demo(week=options["week"], reset=options["reset"])
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        self.stdout.write(demo_walkthrough(result))
