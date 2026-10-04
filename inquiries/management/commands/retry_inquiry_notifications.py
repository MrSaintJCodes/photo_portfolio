from django.core.management.base import BaseCommand

from inquiries.models import Inquiry
from inquiries.services import notify_owner


class Command(BaseCommand):
    help = "Retry unsent inquiry notifications, including stale interrupted attempts."

    def handle(self, *args, **options):
        inquiries = Inquiry.objects.exclude(notification_status="sent")
        sent = sum(notify_owner(inquiry) for inquiry in inquiries)
        self.stdout.write(f"Accepted {sent} notifications.")
