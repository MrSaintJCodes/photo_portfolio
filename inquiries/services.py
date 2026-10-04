import hashlib
import ipaddress
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from django.utils.translation import override

from .models import Inquiry, RateLimitBucket
from portfolio.models import Photo
from portfolio.services.seo import absolute_url


logger = logging.getLogger(__name__)


def client_address(request):
    remote = request.META.get("REMOTE_ADDR", "unknown")
    networks = [ipaddress.ip_network(value) for value in settings.TRUSTED_PROXY_CIDRS]

    def trusted(address):
        try:
            return any(ipaddress.ip_address(address) in network for network in networks)
        except ValueError:
            return False

    if trusted(remote):
        addresses = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") + [remote]
        for address in reversed(addresses):
            address = address.strip()
            if address and not trusted(address):
                try:
                    return str(ipaddress.ip_address(address))
                except ValueError:
                    return remote
    return remote


def consume_rate_limit(request):
    window = settings.INQUIRY_RATE_WINDOW
    bucket_number = int(time.time()) // window
    key = hashlib.sha256(f"{settings.SECRET_KEY}:{client_address(request)}:{bucket_number}".encode()).hexdigest()
    with transaction.atomic():
        bucket, _ = RateLimitBucket.objects.get_or_create(key=key,
            defaults={"expires_at": timezone.now() + timedelta(seconds=window)})
        bucket = RateLimitBucket.objects.select_for_update().get(pk=bucket.pk)
        if bucket.count >= settings.INQUIRY_RATE_LIMIT:
            return False
        bucket.count += 1
        bucket.save(update_fields=["count"])
    RateLimitBucket.objects.filter(expires_at__lt=timezone.now()).delete()
    return True


def notify_owner(inquiry):
    console_in_production = not settings.DEBUG and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend"
    if not settings.CONTACT_TO_EMAIL or not settings.CONTACT_FROM_EMAIL or console_in_production:
        Inquiry.objects.filter(pk=inquiry.pk).exclude(notification_status="sent").update(
            last_notification_error="Configure a delivery backend, CONTACT_FROM_EMAIL, and CONTACT_TO_EMAIL to enable notifications.")
        return False
    now = timezone.now()
    eligible = Q(notification_status__in=["pending", "failed"]) | Q(
        notification_status="sending", notification_started_at__lt=now - timedelta(minutes=5))
    claimed = Inquiry.objects.filter(pk=inquiry.pk).filter(eligible).update(
        notification_status="sending", notification_started_at=now)
    if not claimed:
        return False
    try:
        validate_email(settings.CONTACT_FROM_EMAIL)
        validate_email(settings.CONTACT_TO_EMAIL)
        body = "\n".join([
            f"Name: {inquiry.name}", f"Email: {inquiry.email}", f"Organization: {inquiry.organization}",
            f"Assignment: {inquiry.assignment_type}", f"Date: {inquiry.event_date or ''}",
            f"Location: {inquiry.location}", "", inquiry.message,
        ])
        with override(inquiry.language):
            if inquiry.service:
                body += f"\n\nService: {inquiry.get_service_display()}"
            selected = inquiry.photos.filter(pk__in=Photo.objects.public().values("pk"))
            if selected:
                body += "\n\nSelected photographs:\n" + "\n".join(
                    f"{photo.title}: {absolute_url(reverse('photo', args=[photo.identifier]))}" for photo in selected)
        sent = EmailMessage(subject=f"MrSaintJ Photography inquiry from {inquiry.name}", body=body,
            from_email=settings.CONTACT_FROM_EMAIL, to=[settings.CONTACT_TO_EMAIL], reply_to=[inquiry.email],
            headers={"X-Submission-ID": f"inquiry/{inquiry.submission_id}"}).send(fail_silently=False)
        if not sent:
            raise RuntimeError("The email backend did not accept the notification.")
        Inquiry.objects.filter(pk=inquiry.pk).update(notification_status="sent", notification_sent_at=now,
                                                   last_notification_error="")
        return True
    except Exception as exc:
        Inquiry.objects.filter(pk=inquiry.pk).update(notification_status="failed", last_notification_error=str(exc)[:2000])
        logger.exception("Inquiry notification failed for %s", inquiry.submission_id)
        return False
