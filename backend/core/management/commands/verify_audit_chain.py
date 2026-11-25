from django.core.management.base import BaseCommand, CommandError

from core.models import AuditLog


class Command(BaseCommand):
    help = "Verify that no audit-trail entry has been altered or deleted."

    def handle(self, *args, **opts):
        ok, broken = AuditLog.verify_chain()
        if not ok:
            raise CommandError(f"Audit chain BROKEN at entry #{broken}. Investigate possible tampering.")
        self.stdout.write(self.style.SUCCESS(f"Audit chain intact ({AuditLog.objects.count()} entries)."))
