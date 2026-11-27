"""Run daily (e.g. cron at 00:30): expire licences, raise monthly rates on the
1st of the month, and flag complaints that breached the 48-hour standard."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core import audit
from finance import services
from workflow.models import Complaint


class Command(BaseCommand):
    help = "Daily council finance & charter jobs"

    def handle(self, *args, **opts):
        User = get_user_model()
        actor = User.objects.filter(role="TREASURER", is_active=True).first() or User.objects.filter(is_superuser=True).first()
        token = audit.set_actor(actor)
        try:
            n = services.expire_licences()
            self.stdout.write(f"{n} licence(s) expired")
            from social.services import expire_permits

            self.stdout.write(f"{expire_permits()} natural resources permit(s) expired")
            today = timezone.localdate()
            if today.day == 1 and actor is not None:
                created, skipped = services.run_rates_billing(actor, today.year, today.month)
                self.stdout.write(f"Rates billing: {created} raised, {skipped} skipped")
            breached = Complaint.objects.alive().filter(acknowledged_at__isnull=True, acknowledge_due__lt=timezone.now())
            for c in breached:
                heads = [u for u in User.objects.filter(department=c.department, is_active=True) if u.is_head]
                services.notify(heads + list(User.objects.filter(role="CEO")), f"Charter breach: {c.reference} not acknowledged in 48h", c.subject,
                                f"/staff/complaints/{c.pk}/")
            self.stdout.write(f"{breached.count()} complaint(s) past 48h without acknowledgement")
        finally:
            audit._actor.reset(token)
