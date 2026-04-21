"""
Management command: clean_carts
================================

Deletes cart records (and their related items via CASCADE) that were created
more than N days ago AND have not been checked out.

Usage
-----
    python manage.py clean_carts
    python manage.py clean_carts --days 14
    python manage.py clean_carts --days 7 --include-checked-out
    python manage.py clean_carts --days 30 --dry-run

Cron job example (daily at 2 AM)
----------------------------------
    0 2 * * * /path/to/venv/bin/python /path/to/project/manage.py clean_carts --days 30
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cart.models import Cart


class Command(BaseCommand):
    help = (
        "Delete abandoned cart records older than a configurable number of days. "
        "By default only unchecked-out carts are removed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help=(
                "Remove carts created more than this many days ago. " "Defaults to 90."
            ),
        )
        parser.add_argument(
            "--include-checked-out",
            action="store_true",
            default=False,
            help=(
                "Also remove carts that have already been checked out. "
                "By default only abandoned (unchecked-out) carts are deleted."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show how many carts would be deleted without actually deleting them.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        include_checked_out = options["include_checked_out"]
        dry_run = options["dry_run"]

        if days < 1:
            raise CommandError("--days must be a positive integer.")

        cutoff = timezone.now() - timedelta(days=days)

        qs = Cart.objects.filter(creation_date__lt=cutoff)
        if not include_checked_out:
            qs = qs.filter(checked_out=False)

        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would delete {count} cart(s) older than {days} day(s)."
                )
            )
            return

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No carts older than {days} day(s) found. Nothing to delete."
                )
            )
            return

        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {count} cart(s) (and their items) older than {days} day(s)."
            )
        )
