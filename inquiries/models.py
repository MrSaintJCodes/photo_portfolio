import uuid

from django.db import models
from portfolio.service_content import ServiceKind


class Inquiry(models.Model):
    submission_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    organization = models.CharField(max_length=160, blank=True)
    assignment_type = models.CharField(max_length=80, blank=True)
    service = models.CharField(max_length=40, choices=ServiceKind.choices, blank=True)
    event_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=160, blank=True)
    message = models.TextField()
    photos = models.ManyToManyField("portfolio.Photo", blank=True, related_name="inquiries")
    language = models.CharField(max_length=2, default="en")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    workflow_status = models.CharField(max_length=20, default="new",
        choices=[("new", "New"), ("in-progress", "In progress"), ("closed", "Closed")])
    notification_status = models.CharField(max_length=16, default="pending",
        choices=[("pending", "Pending"), ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed")])
    notification_started_at = models.DateTimeField(null=True, blank=True)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    last_notification_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} \u00b7 {self.created_at:%Y-%m-%d}" if self.created_at else self.name


class RateLimitBucket(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
