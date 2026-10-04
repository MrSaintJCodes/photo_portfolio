import io
import json
import uuid
from unittest.mock import patch

from django.core import mail
from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from portfolio.models import Photo, PhotoRendition

from .models import Inquiry
from .services import client_address, notify_owner


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", CONTACT_FROM_EMAIL="hello@example.com",
                   CONTACT_TO_EMAIL="owner@example.com", STORAGES={**settings.STORAGES,
                   "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class InquiryTests(TestCase):
    def test_service_query_is_optional_validated_and_translated(self):
        from portfolio.service_content import ServiceKind
        for language in ("en", "fr"):
            for key in ServiceKind.values:
                response = self.client.get(f"/{language}/contact/", {"service": key})
                self.assertEqual(response.context["form"]["service"].value(), key)
            for invalid in ("unknown", "https://example.com", "<script>"):
                response = self.client.get(f"/{language}/contact/", {"service": invalid})
                self.assertEqual(response.context["form"]["service"].value(), "")
        self.assertContains(self.client.get("/fr/contact/?service=team-photos"), "Photos d&#x27;équipe et de groupe")

    def test_service_can_be_changed_and_survives_validation_errors(self):
        response = self.client.get("/en/contact/?service=athlete-portraits")
        data = {"name": "Alex", "email": "invalid", "message": "Team shoot", "service": "team-photos",
                "submission_token": response.context["form"].initial["submission_token"]}
        response = self.client.post("/en/contact/", data)
        self.assertEqual(response.context["form"]["service"].value(), "team-photos")
        self.assertFalse(Inquiry.objects.exists())
        data["email"] = "alex@example.com"
        self.assertEqual(self.client.post("/en/contact/", data).status_code, 302)
        self.assertEqual(Inquiry.objects.get().service, "team-photos")

    def test_unknown_post_service_is_rejected_and_empty_selection_is_allowed(self):
        data = self.payload()
        data["service"] = "injected-service"
        response = self.client.post("/en/contact/", data)
        self.assertIn("service", response.context["form"].errors)
        self.assertFalse(Inquiry.objects.exists())
        data["service"] = ""
        self.assertEqual(self.client.post("/en/contact/", data).status_code, 302)
        self.assertEqual(Inquiry.objects.get().service, "")

    def test_service_label_is_localized_in_notification_and_admin_and_dedup_preserves_it(self):
        response = self.client.get("/fr/contact/?service=athlete-portraits")
        data = {"name": "Alex", "email": "alex@example.com", "message": "Portraits",
                "service": "athlete-portraits", "submission_token": response.context["form"].initial["submission_token"]}
        self.client.post("/fr/contact/", data)
        inquiry = Inquiry.objects.get()
        self.assertIn("Service: Portraits individuels d'athlètes", mail.outbox[0].body)
        data["service"] = "team-photos"
        self.client.post("/fr/contact/", data)
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.service, "athlete-portraits")
        self.assertEqual(len(mail.outbox), 1)
        user = get_user_model().objects.create_superuser("owner", "owner@example.com", "secret")
        self.client.force_login(user)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "fr"
        response = self.client.get(f"/admin/inquiries/inquiry/{inquiry.pk}/change/")
        self.assertContains(response, "Portraits individuels d&#x27;athlètes")

    @patch("inquiries.services.EmailMessage.send", side_effect=RuntimeError("Provider unavailable"))
    def test_service_survives_notification_retry(self, send):
        data = self.payload()
        data["service"] = "fitness-promotion"
        self.client.post("/en/contact/", data)
        inquiry = Inquiry.objects.get()
        self.assertEqual(inquiry.service, "fitness-promotion")
        send.side_effect = None
        send.return_value = 1
        with patch("inquiries.services.EmailMessage", wraps=mail.EmailMessage) as email:
            self.assertTrue(notify_owner(inquiry))
            self.assertIn("Service: Fitness and sports promotion", email.call_args.kwargs["body"])

    def payload(self, client=None):
        response = (client or self.client).get("/en/contact/")
        return {"name": "Alex", "email": "alex@example.com", "message": "A match worth photographing.",
                "submission_token": response.context["form"].initial["submission_token"]}

    def test_valid_submission_is_saved_notified_and_redirected(self):
        response = self.client.post("/en/contact/", self.payload(), follow=True)
        self.assertContains(response, "Thanks for getting in touch.")
        inquiry = Inquiry.objects.get()
        self.assertEqual(inquiry.notification_status, "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "hello@example.com")
        self.assertEqual(mail.outbox[0].reply_to, ["alex@example.com"])

    def test_duplicate_submission_creates_one_inquiry_and_one_notification(self):
        data = self.payload()
        self.client.post("/en/contact/", data)
        self.client.post("/en/contact/", data)
        self.assertEqual(Inquiry.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def make_photo(self, title, status="published"):
        photo = Photo.objects.create(title_en=title, alt_en=title, source="private-source.jpg",
                                     processing_status="ready", status=status)
        PhotoRendition.objects.create(photo=photo, format="jpeg", file=f"photos/{photo.identifier}.jpeg",
                                     width=800, height=500, byte_size=100)
        return photo

    @override_settings(PUBLIC_SITE_URL="https://portfolio.example")
    def test_shortlist_is_validated_saved_and_included_in_owner_notification(self):
        photo = self.make_photo("Selected public moment")
        draft = self.make_photo("Hidden moment", "draft")
        data = self.payload()
        data["selected_photos"] = json.dumps([str(photo.identifier), str(draft.identifier), str(uuid.uuid4()), str(photo.identifier)])
        self.assertEqual(self.client.post("/en/contact/", data).status_code, 302)
        self.assertEqual(list(Inquiry.objects.get().photos.all()), [photo])
        self.assertIn(f"https://portfolio.example/en/photos/{photo.identifier}/", mail.outbox[0].body)
        self.assertNotIn(str(draft.identifier), mail.outbox[0].body)
        self.assertNotIn("private-source", mail.outbox[0].body)
        user = get_user_model().objects.create_user("owner", is_staff=True, is_superuser=True)
        self.client.force_login(user)
        response = self.client.get(f"/admin/inquiries/inquiry/{Inquiry.objects.get().pk}/change/")
        self.assertContains(response, photo.title_en)
        self.assertContains(response, reverse("private-preview", args=[photo.renditions.first().pk]))
        self.assertNotContains(response, 'name="photos"')

    def test_duplicate_submission_cannot_replace_the_original_shortlist(self):
        first = self.make_photo("First")
        second = self.make_photo("Second")
        data = self.payload()
        data["selected_photos"] = json.dumps([str(first.identifier)])
        self.client.post("/en/contact/", data)
        data["selected_photos"] = json.dumps([str(second.identifier)])
        self.client.post("/en/contact/", data)
        self.assertEqual(list(Inquiry.objects.get().photos.all()), [first])
        self.assertEqual(len(mail.outbox), 1)

    def test_malformed_and_excess_shortlists_do_not_create_an_inquiry(self):
        for values in ("not json", "{}", "[7]", '["https://private.example/source.jpg"]', json.dumps([str(uuid.uuid4())] * 13)):
            data = self.payload()
            data["selected_photos"] = values
            response = self.client.post("/en/contact/", data)
            self.assertContains(response, "Please review your saved photographs.")
            self.assertFalse(Inquiry.objects.exists())

    @patch("inquiries.services.EmailMessage.send", side_effect=RuntimeError("Provider unavailable"))
    def test_shortlist_survives_notification_failure_and_unpublication_before_retry(self, send):
        photo = self.make_photo("Selected moment")
        data = self.payload()
        data["selected_photos"] = json.dumps([str(photo.identifier)])
        self.client.post("/en/contact/", data)
        inquiry = Inquiry.objects.get()
        self.assertEqual(list(inquiry.photos.all()), [photo])
        photo.status = "draft"
        photo.save()
        send.side_effect = None
        send.return_value = 1
        with patch("inquiries.services.EmailMessage", wraps=mail.EmailMessage) as email:
            notify_owner(inquiry)
            self.assertNotIn(str(photo.identifier), email.call_args.kwargs["body"])
        self.assertEqual(list(inquiry.photos.all()), [photo])

    @override_settings(CONTACT_TO_EMAIL="", CONTACT_FROM_EMAIL="")
    def test_missing_email_configuration_preserves_a_pending_inquiry(self):
        response = self.client.post("/en/contact/", self.payload(), follow=True)
        self.assertContains(response, "Thanks for getting in touch.")
        self.assertEqual(Inquiry.objects.get().notification_status, "pending")
        self.assertEqual(len(mail.outbox), 0)

    @patch("inquiries.services.EmailMessage.send", side_effect=RuntimeError("Provider unavailable"))
    def test_notification_failure_preserves_inquiry_and_retry_succeeds(self, send):
        self.client.post("/en/contact/", self.payload())
        inquiry = Inquiry.objects.get()
        self.assertEqual(inquiry.notification_status, "failed")
        self.assertIn("Provider unavailable", inquiry.last_notification_error)
        send.side_effect = None
        send.return_value = 1
        call_command("retry_inquiry_notifications", stdout=io.StringIO())
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.notification_status, "sent")
        self.assertFalse(notify_owner(inquiry))
        self.assertEqual(send.call_count, 2)

    def test_validation_errors_and_honeypot_do_not_persist(self):
        data = self.payload()
        data.update(email="not-an-email", message="")
        response = self.client.post("/en/contact/", data)
        self.assertContains(response, "Enter a valid email address")
        self.assertFalse(Inquiry.objects.exists())
        data = self.payload()
        data["website"] = "Spam"
        self.assertEqual(self.client.post("/en/contact/", data).status_code, 302)
        self.assertFalse(Inquiry.objects.exists())

    def test_submission_token_cannot_be_reused_by_another_session(self):
        data = self.payload()
        other = Client()
        other.get("/en/contact/")
        response = other.post("/en/contact/", data)
        self.assertContains(response, "This form has expired")
        self.assertFalse(Inquiry.objects.exists())

    @override_settings(INQUIRY_RATE_LIMIT=1)
    def test_rate_limit_is_shared_across_sessions_and_forwarded_headers_cannot_bypass_it(self):
        self.client.post("/en/contact/", self.payload())
        other = Client()
        response = other.post("/en/contact/", self.payload(other), HTTP_X_FORWARDED_FOR="203.0.113.2")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(Inquiry.objects.count(), 1)

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/en/contact/", self.payload(client)).status_code, 403)

    @patch("inquiries.views.Inquiry.objects.get_or_create", side_effect=OperationalError("Database unavailable"))
    def test_persistence_failure_keeps_input_and_shows_error(self, create):
        response = self.client.post("/en/contact/", self.payload())
        self.assertContains(response, "Your message could not be saved")
        self.assertContains(response, "A match worth photographing.")
        self.assertFalse(Inquiry.objects.exists())

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_only_trusted_proxies_can_supply_forwarded_addresses(self):
        request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="203.0.113.2, 10.0.0.1")
        self.assertEqual(client_address(request), "203.0.113.2")
        request.META["REMOTE_ADDR"] = "198.51.100.1"
        self.assertEqual(client_address(request), "198.51.100.1")

    @override_settings(EMAIL_BACKEND="inquiries.backends.ResendBackend", RESEND_API_KEY="test-key")
    @patch("resend.Emails.send", return_value={"id": "test-notification"})
    def test_resend_uses_configured_sender_reply_to_and_idempotency_key(self, send):
        self.client.post("/en/contact/", self.payload())
        payload, options = send.call_args.args
        inquiry = Inquiry.objects.get()
        self.assertEqual(payload["from"], "hello@example.com")
        self.assertEqual(payload["reply_to"], "alex@example.com")
        self.assertEqual(options["idempotency_key"], f"inquiry/{inquiry.submission_id}")
