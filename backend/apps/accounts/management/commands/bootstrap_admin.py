from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.services import run_first_setup, setup_completed


class Command(BaseCommand):
    help = "First-run setup from ADMIN_EMAIL / ADMIN_PASSWORD / COMPANY_NAME env vars (no-op if already set up)."

    def handle(self, *args, **options):
        if setup_completed():
            self.stdout.write("Setup already completed; nothing to do.")
            return
        if not (settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD):
            self.stdout.write("ADMIN_EMAIL / ADMIN_PASSWORD not set; first-run setup will happen in the browser.")
            return
        run_first_setup(company_name=settings.COMPANY_NAME, email=settings.ADMIN_EMAIL.lower(),
                        password=settings.ADMIN_PASSWORD, first_name="Admin")
        self.stdout.write(self.style.SUCCESS(f"Created company '{settings.COMPANY_NAME}' and Admin {settings.ADMIN_EMAIL}."))
