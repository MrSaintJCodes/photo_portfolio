import io
import json
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils.translation import override

from .models import Photo, PhotoRendition, ServiceOffering, ServicePage, SiteSettings
from .service_content import ServiceKind
from .services.seo import public_pages
from .tests import MediaTestCase


@override_settings(PUBLIC_SITE_URL="https://portfolio.example", INDEXING_ENABLED=True,
                   ALLOWED_HOSTS=["portfolio.example", "testserver"])
class ServicesRefreshTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        self.client.defaults["HTTP_HOST"] = "portfolio.example"
        self.site = SiteSettings.objects.create()
        self.copy = json.loads((settings.BASE_DIR / "content/offerings.json").read_text())
        for item in self.copy:
            if item["photo_id"]:
                photo = Photo.objects.create(flickr_id=item["photo_id"], title_en=item["title_en"],
                    title_fr=item["title_fr"], alt_en="A sporting moment", alt_fr="Un moment sportif",
                    source="private.jpg", status="published", processing_status="ready", width=4000, height=2500)
                PhotoRendition.objects.create(photo=photo, format="jpeg", file=f"photos/{photo.identifier}.jpeg",
                                             width=4000, height=2500, byte_size=100)
        self.banner = Photo.objects.create(flickr_id="54689682884", title_en="Through the ropes",
            title_fr="Entre les cordes", alt_en="Participants under a rope net", alt_fr="Participants sous un filet",
            source="private.jpg", status="published", processing_status="ready", width=5999, height=3749)
        PhotoRendition.objects.create(photo=self.banner, format="jpeg", file=f"photos/{self.banner.identifier}.jpeg",
                                     width=5999, height=3749, byte_size=100)
        call_command("seed_services", stdout=io.StringIO())

    def test_six_localized_offerings_have_exact_copy_and_stable_inquiry_links(self):
        self.assertEqual(ServiceOffering.objects.count(), 6)
        self.assertEqual(ServicePage.objects.count(), 3)
        for language in ("en", "fr"):
            response = self.client.get(f"/{language}/services/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'class="offering-card', count=6)
            self.assertEqual(response.context["site"].services_heading, getattr(self.site, f"services_heading_{language}"))
            for item, offering in zip(self.copy, response.context["offerings"]):
                self.assertContains(response, f'href="/{language}/contact/?service={item["key"]}"')
                self.assertEqual(offering.title, item[f"title_{language}"])
                self.assertEqual(offering.description, item[f"description_{language}"])
            self.assertContains(response, f'href="/{language}/contact/"')

    def test_team_offering_has_approved_group_cover_and_public_images_keep_native_size(self):
        response = self.client.get("/en/services/")
        self.assertContains(response, 'class="offering-card" id="team-photos"')
        offering = next(item for item in response.context["offerings"] if item.key == ServiceKind.TEAM)
        self.assertEqual(offering.cover_photo.flickr_id, "54645194272")
        self.assertContains(response, f"photos/{offering.cover_photo.identifier}.jpeg")
        self.assertContains(response, "4000w")
        self.assertEqual(response.context["cover"].flickr_id, "54689682884")
        self.assertNotContains(response, "private.jpg")

    def test_services_banner_uses_approved_native_photo_in_both_languages(self):
        for language in ("en", "fr"):
            with self.subTest(language=language):
                response = self.client.get(f"/{language}/services/")
                self.assertEqual(response.context["cover"], self.banner)
                self.assertContains(response, f"photos/{self.banner.identifier}.jpeg 5999w")
                self.assertNotContains(response, "private.jpg")

    def test_services_banner_respects_owner_selected_cover_without_changing_homepage(self):
        photo = Photo.objects.get(flickr_id="54645194272")
        self.site.hero_photo = self.banner
        self.site.services_cover_photo = photo
        self.site.save()
        call_command("seed_services", stdout=io.StringIO())
        response = self.client.get("/en/services/")
        self.assertEqual(response.context["cover"], photo)
        self.site.refresh_from_db()
        self.assertEqual(self.site.hero_photo, self.banner)
        self.assertEqual(self.site.services_cover_photo, photo)

    def test_services_banner_excludes_unavailable_photos_and_uses_public_homepage_fallback(self):
        photo = Photo.objects.get(flickr_id="54645194272")
        self.site.hero_photo = photo
        self.site.services_cover_photo = self.banner
        self.site.save()
        for status, processing in (("draft", "ready"), ("published", "pending")):
            with self.subTest(status=status, processing=processing):
                Photo.objects.filter(pk=self.banner.pk).update(status=status, processing_status=processing)
                response = self.client.get("/en/services/")
                self.assertEqual(response.context["cover"], photo)
                self.assertNotContains(response, f"photos/{self.banner.identifier}.jpeg")

    def test_team_offering_without_a_cover_retains_text_led_fallback(self):
        offering = ServiceOffering.objects.get(key=ServiceKind.TEAM)
        offering.cover_photo = None
        offering.save()
        response = self.client.get("/en/services/")
        self.assertContains(response, 'class="offering-card offering-text-led" id="team-photos"')

    def test_explicit_cover_selection_preserves_copy_status_and_other_offerings(self):
        offering = ServiceOffering.objects.get(key=ServiceKind.TEAM)
        offering.cover_photo = None
        offering.title_en = "Owner's group sessions"
        offering.status = "draft"
        offering.save()
        others = list(ServiceOffering.objects.exclude(pk=offering.pk).values("pk", "cover_photo_id", "updated_at"))
        call_command("seed_services", stdout=io.StringIO())
        offering.refresh_from_db()
        self.assertIsNone(offering.cover_photo)
        call_command("seed_services", set_cover=ServiceKind.TEAM, stdout=io.StringIO())
        offering.refresh_from_db()
        self.assertEqual(offering.cover_photo.flickr_id, "54645194272")
        self.assertEqual(offering.title_en, "Owner's group sessions")
        self.assertEqual(offering.status, "draft")
        self.assertEqual(list(ServiceOffering.objects.exclude(pk=offering.pk).values("pk", "cover_photo_id", "updated_at")), others)

    def test_explicit_cover_selection_rejects_an_unavailable_photo_without_clearing_cover(self):
        offering = ServiceOffering.objects.get(key=ServiceKind.TEAM)
        photo = offering.cover_photo
        photo.status = "draft"
        photo.save()
        with self.assertRaisesMessage(CommandError, "Import the offering's approved photograph"):
            call_command("seed_services", set_cover=ServiceKind.TEAM, stdout=io.StringIO())
        offering.refresh_from_db()
        self.assertEqual(offering.cover_photo_id, photo.pk)


    def test_seeding_preserves_owner_edits_images_order_and_publication(self):
        offering = ServiceOffering.objects.get(key=ServiceKind.TEAM)
        offering.title_en = "My team sessions"
        offering.order = 15
        offering.status = "draft"
        offering.cover_photo = Photo.objects.first()
        offering.save()
        self.site.services_heading_en = "Owner's services"
        self.site.save()
        call_command("seed_services", stdout=io.StringIO())
        offering.refresh_from_db()
        self.site.refresh_from_db()
        self.assertEqual(offering.title_en, "My team sessions")
        self.assertEqual(offering.status, "draft")
        self.assertEqual(offering.order, 15)
        self.assertIsNotNone(offering.cover_photo)
        self.assertEqual(self.site.services_heading_en, "Owner's services")

    def test_unpublished_or_untranslated_cards_are_absent_from_html_graph_and_markdown(self):
        draft = ServiceOffering.objects.get(key=ServiceKind.RACE)
        draft.status = "draft"
        draft.save()
        missing = ServiceOffering.objects.get(key=ServiceKind.FITNESS)
        missing.description_fr = ""
        missing.save()
        for path in ("/fr/services/", "/fr/services/index.md"):
            response = self.client.get(path)
            self.assertNotContains(response, draft.title_fr)
            self.assertNotContains(response, missing.title_en)
            self.assertNotContains(response, missing.title_fr)
        self.assertContains(self.client.get("/en/services/"), missing.title_en)

    def test_metadata_graph_and_markdown_describe_the_visible_six_offerings(self):
        for language in ("en", "fr"):
            response = self.client.get(f"/{language}/services/")
            graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',
                                         response.content.decode(), re.S).group(1))["@graph"]
            nodes = [item for item in graph if item["@type"] == "Service"]
            self.assertEqual(len(nodes), 6)
            markdown = self.client.get(f"/{language}/services/index.md")
            self.assertEqual(markdown["Link"], f'<https://portfolio.example/{language}/services/>; rel="canonical"')
            for copy, node in zip(self.copy, nodes):
                self.assertEqual(node["description"], copy[f"description_{language}"])
                self.assertContains(markdown, copy[f"description_{language}"])
                self.assertContains(markdown, f"/{language}/contact/?service={copy['key']}")
            self.assertEqual(response.context["seo"]["canonical"], f"https://portfolio.example/{language}/services/")
            if language == "fr":
                self.assertIn("Services de photographie sportive", response.context["seo"]["title"])
                self.assertNotContains(response, "Tell me about your shoot")

    def test_unavailable_cover_becomes_text_led_and_cannot_be_selected_in_admin(self):
        offering = ServiceOffering.objects.get(key=ServiceKind.ATHLETE)
        photo = offering.cover_photo
        photo.status = "draft"
        photo.save()
        response = self.client.get("/en/services/")
        self.assertContains(response, 'class="offering-card offering-text-led" id="athlete-portraits"')
        self.assertNotContains(response, f"photos/{photo.identifier}.jpeg")
        with self.assertRaises(ValidationError):
            offering.full_clean()
        self.site.services_cover_photo = photo
        with self.assertRaises(ValidationError):
            self.site.full_clean()

    def test_offer_edit_unpublish_and_delete_invalidate_discovery(self):
        def modified():
            return next(entry["updated"] for entry in public_pages(SiteSettings.objects.get()) if entry["path"] == "/en/services/")
        before = modified()
        offering = ServiceOffering.objects.get(key=ServiceKind.TEAM)
        offering.description_en += " Updated."
        offering.save()
        self.assertGreater(modified(), before)
        before = modified()
        offering.status = "draft"
        offering.save(update_fields=["status"])
        self.assertGreater(modified(), before)
        offering = ServiceOffering.objects.get(key=ServiceKind.ATHLETE)
        before = modified()
        offering.delete()
        self.assertGreater(modified(), before)

    def test_admin_exposes_localized_copy_images_order_and_status(self):
        user = get_user_model().objects.create_superuser("owner", "owner@example.com", "secret")
        self.client.force_login(user)
        offering = ServiceOffering.objects.first()
        response = self.client.get(f"/admin/portfolio/serviceoffering/{offering.pk}/change/")
        self.assertEqual(response.status_code, 200)
        for field in ("title_en", "title_fr", "description_en", "description_fr", "inquiry_label_en", "inquiry_label_fr", "cover_photo", "order", "status"):
            self.assertContains(response, f'name="{field}"')

    def test_camera_is_decorative_and_links_remain_real_navigation(self):
        response = self.client.get("/en/services/")
        self.assertContains(response, 'data-pixel-camera aria-hidden="true" hidden')
        self.assertContains(response, 'data-pixel-camera-backdrop aria-hidden="true" hidden')
        self.assertContains(response, 'focusable="false"')
        self.assertContains(response, 'data-camera-transition href="/en/contact/?service=team-photos"')
        self.assertContains(response, "js/pixel-camera.js")
        total = sum((settings.BASE_DIR / path).stat().st_size for path in (
            "templates/components/pixel_camera.html", "static/css/pixel-camera.css", "static/js/pixel-camera.js"))
        self.assertLess(total, 10 * 1024)

    @override_settings(PIXEL_CAMERA_TRANSITIONS_ENABLED=False)
    def test_camera_setting_omits_all_effect_assets_and_markup(self):
        response = self.client.get("/en/services/")
        self.assertNotContains(response, "data-pixel-camera")
        self.assertNotContains(response, "js/pixel-camera.js")
        self.assertNotContains(response, "css/pixel-camera.css")
