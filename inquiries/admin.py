from django.contrib import admin
from django.utils.html import format_html_join
from django.utils.translation import gettext_lazy as _

from .models import Inquiry
from .services import notify_owner
from portfolio.admin import thumbnail


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "service_label", "created_at", "workflow_status", "notification_status")
    list_editable = ("workflow_status",)
    list_filter = ("workflow_status", "notification_status", "service", "assignment_type")
    search_fields = ("name", "email", "organization", "message")
    readonly_fields = ("submission_id", "name", "email", "organization", "assignment_type", "service_label", "event_date", "location",
                       "message", "language", "created_at", "updated_at", "notification_status", "notification_started_at",
                       "notification_sent_at", "last_notification_error", "selected_photographs")
    actions = ("retry_notifications",)
    exclude = ("photos", "service")

    @admin.display(description=_("Photography service"))
    def service_label(self, obj):
        return obj.get_service_display() or "-"

    def has_add_permission(self, request):
        return False

    @admin.display(description="Selected photographs")
    def selected_photographs(self, obj):
        return format_html_join("", '<p>{} {}</p>', ((thumbnail(photo), photo.title_en) for photo in obj.photos.prefetch_related("renditions"))) or "No photographs selected."

    @admin.action(description="Retry pending or failed notifications")
    def retry_notifications(self, request, queryset):
        sent = sum(notify_owner(inquiry) for inquiry in queryset)
        self.message_user(request, f"Accepted {sent} notifications. Check notification status for details.")
