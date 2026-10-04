import io
import json
import re
import uuid
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse

from .checks import discovery_configuration, valid_origin
from .models import (PartnerCredit, Photo, PhotoRendition, ServiceFAQ, ServicePage, ServicePhoto,
                     ServiceStory, SiteSettings, Story, StoryPhoto)
from .services.shortlist import public_selection
from .services.seo import public_pages
from .tests import MediaTestCase


@override_settings(PUBLIC_SITE_URL="https://portfolio.example", INDEXING_ENABLED=True,
                   ALLOWED_HOSTS=["portfolio.example", "testserver", "wrong.example"])
class DiscoveryTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        self.site = SiteSettings.objects.create(instagram_url="https://www.instagram.com/mrsaintj/",
                                               linkedin_url="https://www.linkedin.com/in/mrsaintj123/")
        self.photo = self.make_photo("Decisive moment", "published")
        self.draft = self.make_photo("Private draft", "draft")
        self.site.hero_photo = self.photo
        self.site.save()
        self.story = Story.objects.create(slug="the-effort", title_en="The effort", title_fr="L'effort",
                                         introduction_en="The visible action.", introduction_fr="L'action visible.",
                                         status="published", cover_photo=self.photo)
        StoryPhoto.objects.create(story=self.story, photo=self.photo)
        StoryPhoto.objects.create(story=self.story, photo=self.draft)
        self.service = ServicePage.objects.create(key="sport", slug_en="sport", slug_fr="sports",
            title_en="Sports photography", title_fr="Photographie sportive", introduction_en="Coverage of effort.",
            introduction_fr="Le reportage de l'effort.", body_en="The assignment.", body_fr="Le mandat.", status="published")
        ServicePhoto.objects.create(service=self.service, photo=self.photo)
        ServicePhoto.objects.create(service=self.service, photo=self.draft)
        ServiceStory.objects.create(service=self.service, story=self.story)
        self.faq = ServiceFAQ.objects.create(service=self.service, question_en="Where?", question_fr="Où?",
                                            answer_en="Montréal and the South Shore.", answer_fr="Montréal et la Rive-Sud.")

    def make_photo(self, title, status):
        photo = Photo.objects.create(title_en=title, title_fr=f"FR {title}", alt_en=f"Action: {title}",
            alt_fr=f"Action FR : {title}", source="private-original.jpg",
            source_url="https://www.flickr.com/photos/194206904@N02/53984262444/",
            status=status, processing_status="ready", width=800, height=500)
        PhotoRendition.objects.create(photo=photo, format="jpeg", file=f"photos/{photo.identifier}.jpeg",
                                     width=800, height=500, byte_size=100)
        return photo

    def get(self, path, **kwargs):
        return self.client.get(path, HTTP_HOST="portfolio.example", **kwargs)

    def graph(self, response):
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', response.content.decode(), re.S)
        return json.loads(match.group(1))["@graph"]

    def test_localized_services_have_equivalent_links_public_images_and_visible_faq(self):
        for language, slug, title, answer in (("en", "sport", self.service.title_en, self.faq.answer_en),
                                             ("fr", "sports", self.service.title_fr, self.faq.answer_fr)):
            response = self.get(f"/{language}/services/{slug}/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, title)
            self.assertContains(response, answer)
            self.assertContains(response, f"/{language}/contact/")
            self.assertContains(response, f"/{language}/stories/the-effort/")
            self.assertNotContains(response, self.draft.title_en)
            self.assertEqual(len(response.context["seo"]["alternates"]), 2)
        self.assertEqual(self.get("/fr/services/sport/").status_code, 404)

    def test_missing_translation_uses_services_index_switch_and_french_visible_metadata(self):
        response = self.get("/fr/services/sports/")
        self.assertIn(self.service.title_fr, response.context["seo"]["title"])
        self.assertEqual(response.context["seo"]["description"], self.service.introduction_fr)
        self.service.title_fr = ""
        self.service.save()
        response = self.get("/en/services/sport/")
        self.assertEqual(response.context["language_switch_url"], "/fr/services/")
        self.assertEqual([item["language"] for item in response.context["seo"]["alternates"]], ["en"])
        self.assertEqual(self.get("/fr/services/sports/").status_code, 404)
        self.assertNotContains(self.get("/sitemap.xml"), "/fr/services/sports/")

    def test_slug_renames_redirect_directly_without_loops_and_drafts_disappear(self):
        for slug in ("new-sport", "latest-sport"):
            self.service.slug_en = slug
            self.service.save()
        for slug in ("sport", "new-sport"):
            response = self.get(f"/en/services/{slug}/")
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response["Location"], "/en/services/latest-sport/")
        self.service.slug_en = "sport"
        self.service.save()
        self.assertEqual(self.get("/en/services/sport/").status_code, 200)
        self.assertEqual(self.get("/en/services/latest-sport/")["Location"], "/en/services/sport/")
        self.service.status = "draft"
        self.service.save()
        for path in ("/en/services/sport/", "/en/services/latest-sport/", "/en/services/sport/index.md"):
            self.assertEqual(self.get(path).status_code, 404)
        self.assertNotContains(self.get("/llms.txt"), "/services/sport/")

    def test_unknown_and_deleted_services_return_404(self):
        self.assertEqual(self.get("/en/services/unknown/").status_code, 404)
        self.service.delete()
        self.assertEqual(self.get("/en/services/sport/").status_code, 404)

    def test_story_slug_redirects_use_current_published_cover_and_do_not_loop(self):
        self.story.slug = "new-effort"
        self.story.save()
        self.story.slug = "latest-effort"
        self.story.save()
        response = self.get("/fr/stories/the-effort/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/fr/stories/latest-effort/")
        self.story.slug = "the-effort"
        self.story.save()
        self.assertEqual(self.get("/fr/stories/the-effort/").status_code, 200)
        self.photo.status = "draft"
        self.photo.save()
        self.assertEqual(self.get("/fr/stories/latest-effort/").status_code, 404)

    @override_settings(INDEXING_ENABLED=False)
    def test_metadata_never_uses_request_host_and_staging_is_noindex(self):
        response = self.client.get("/en/work/", HTTP_HOST="wrong.example")
        self.assertEqual(response.context["seo"]["canonical"], "https://portfolio.example/en/work/")
        self.assertNotContains(response, "wrong.example")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertContains(response, 'content="noindex, follow"')
        self.assertContains(self.get("/robots.txt"), "Disallow: /\n")

    def test_preferred_host_redirect_is_stable_and_preserves_filters(self):
        response = self.client.get("/fr/work/?category=race-day", HTTP_HOST="wrong.example")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://portfolio.example/fr/work/?category=race-day")
        self.assertEqual(self.get("/fr/work/").status_code, 200)
        self.assertEqual(self.client.get("/healthz/", HTTP_HOST="wrong.example").status_code, 200)

    def test_filter_variants_are_noindex_and_unfiltered_pagination_is_canonical(self):
        response = self.get("/en/work/?category=")
        self.assertTrue(response.context["seo"]["noindex"])
        self.assertEqual(response.context["seo"]["canonical"], "https://portfolio.example/en/work/")
        for number in range(18):
            self.make_photo(f"Extra {number}", "published")
        response = self.get("/en/work/?page=2")
        self.assertFalse(response.context["seo"]["noindex"])
        self.assertEqual(response.context["seo"]["canonical"], "https://portfolio.example/en/work/?page=2")
        self.assertEqual(response.context["seo"]["alternates"][1]["url"], "https://portfolio.example/fr/work/?page=2")

    @override_settings(PUBLIC_SITE_URL="https://portfolio.example:443")
    def test_default_https_port_does_not_cause_preferred_host_redirect_loops(self):
        self.assertEqual(self.get("/en/").status_code, 200)
        self.assertEqual(self.client.get("/en/", HTTP_HOST="portfolio.example:443").status_code, 200)
        self.assertEqual(self.client.get("/en/", HTTP_HOST="portfolio.example:999999").status_code, 400)

    def test_json_ld_reflects_visible_identity_and_images_and_escapes_script_content(self):
        self.photo.title_en = '</script><script>alert("unsafe")</script>'
        self.photo.save()
        response = self.get(f"/en/photos/{self.photo.identifier}/")
        graph = self.graph(response)
        person = next(node for node in graph if node["@type"] == "Person")
        image = next(node for node in graph if node["@type"] == "ImageObject")
        self.assertEqual(person["name"], "Justin St-Laurent")
        self.assertEqual(person["sameAs"], [self.site.instagram_url, self.site.linkedin_url, self.site.flickr_url])
        self.assertEqual(image["name"], self.photo.title_en)
        self.assertEqual((image["width"], image["height"]), (800, 500))
        self.assertTrue(image["contentUrl"].startswith("https://portfolio.example/media/photos/"))
        self.assertEqual(image["creator"]["@id"], person["@id"])
        self.assertNotContains(response, '<script>alert("unsafe")')
        for value in ("LocalBusiness", "streetAddress", "private-original.jpg", "private.example", "Secret draft"):
            self.assertNotContains(response, value)
        service_graph = self.graph(self.get("/fr/services/sports/"))
        self.assertEqual(next(node for node in service_graph if node["@type"] == "Service")["name"], self.service.title_fr)

    def test_missing_jpeg_cannot_publish_or_leak_into_public_outputs(self):
        self.photo.renditions.update(format="webp")
        self.assertFalse(self.photo.is_public)
        self.assertFalse(Photo.objects.public().filter(pk=self.photo.pk).exists())
        for path in ("/en/", "/en/work/", "/en/services/sport/", "/sitemap.xml", "/en/services/sport/index.md"):
            response = self.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, str(self.photo.identifier))
        self.assertEqual(self.get(f"/en/photos/{self.photo.identifier}/").status_code, 404)

    def test_sitemap_has_stable_lastmod_and_safe_images_and_updates_with_content(self):
        response = self.get("/sitemap.xml")
        root = ET.fromstring(response.content)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "i": "http://www.google.com/schemas/sitemap-image/1.1"}
        locations = [node.text for node in root.findall("s:url/s:loc", ns)]
        images = [node.text for node in root.findall("s:url/i:image/i:loc", ns)]
        self.assertIn("https://portfolio.example/fr/services/sports/", locations)
        self.assertTrue(images)
        self.assertTrue(all(url.startswith("https://portfolio.example/media/photos/") for url in images))
        self.assertFalse(any("shortlist" in url or "index.md" in url or "?" in url for url in locations))
        self.assertNotContains(response, str(self.draft.identifier))
        self.assertEqual(response.content, self.get("/sitemap.xml").content)
        self.assertEqual(self.get("/sitemap.xml", HTTP_IF_NONE_MATCH=response["ETag"]).status_code, 304)
        self.photo.title_en = "Changed visible title"
        self.photo.save()
        changed = self.get("/sitemap.xml")
        self.assertNotEqual(changed["ETag"], response["ETag"])
        self.assertContains(changed, self.photo.updated_at.isoformat())
        self.photo.status = "draft"
        self.photo.save()
        for path in ("/sitemap.xml", "/en/services/sport/index.md", "/en/stories/index.md"):
            self.assertNotContains(self.get(path), str(self.photo.identifier))
        self.assertNotContains(self.get("/sitemap.xml"), "/stories/the-effort/")

    def test_unpublication_advances_collection_lastmod_but_private_edits_do_not(self):
        before = {entry["path"]: entry["updated"] for entry in public_pages(self.site)}
        self.draft.title_en = "Still private"
        self.draft.save()
        after = {entry["path"]: entry["updated"] for entry in public_pages(self.site)}
        self.assertEqual(before["/en/services/sport/"], after["/en/services/sport/"])
        self.assertEqual(before["/en/work/"], after["/en/work/"])
        self.photo.status = "draft"
        self.photo.save(update_fields=["status"])
        after = {entry["path"]: entry["updated"] for entry in public_pages(self.site)}
        self.assertGreater(after["/en/services/sport/"], before["/en/services/sport/"])
        self.assertGreater(after["/en/work/"], before["/en/work/"])
        self.service.status = "draft"
        self.service.save(update_fields=["status"])
        updated = {entry["path"]: entry["updated"] for entry in public_pages(self.site)}
        self.assertGreater(updated["/en/services/"], after["/en/services/"])

    def test_markdown_and_llms_use_public_localized_records_and_canonical_html(self):
        response = self.get("/fr/services/sports/index.md")
        self.assertEqual(response["Content-Type"], "text/markdown; charset=utf-8")
        self.assertEqual(response["Link"], '<https://portfolio.example/fr/services/sports/>; rel="canonical"')
        self.assertEqual(response["X-Robots-Tag"], "noindex, follow")
        self.assertContains(response, self.service.introduction_fr)
        self.assertContains(response, self.faq.answer_fr)
        self.assertNotContains(response, self.draft.title_fr)
        self.assertEqual(self.get("/fr/services/sports/index.md", HTTP_IF_NONE_MATCH=response["ETag"]).status_code, 304)
        self.service.body_fr = "Le texte mis à jour."
        self.service.save()
        self.assertNotEqual(response["ETag"], self.get("/fr/services/sports/index.md")["ETag"])
        guide = self.get("/llms.txt")
        self.assertEqual(guide["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(guide, "# MrSaintJ Photography")
        self.assertContains(guide, "https://portfolio.example/fr/services/sports/index.md")
        for url in re.findall(r"\]\((https://portfolio.example[^)]+)\)", guide.content.decode()):
            self.assertEqual(self.get(url.removeprefix("https://portfolio.example")).status_code, 200)
        contact = self.get("/en/contact/index.md")
        for value in ("csrf", "submission_token", "<form", "private-original.jpg", "private.example"):
            self.assertNotContains(contact, value)

    def test_removing_public_relations_and_photos_advances_parent_lastmod(self):
        before = {entry["path"]: entry["updated"] for entry in public_pages(self.site)}
        ServicePhoto.objects.get(service=self.service, photo=self.photo).delete()
        self.service.refresh_from_db()
        after = {entry["path"]: entry["updated"] for entry in public_pages(self.site)}
        self.assertGreater(after["/en/services/sport/"], before["/en/services/sport/"])
        before = after
        self.faq.delete()
        self.service.refresh_from_db()
        after = {entry["path"]: entry["updated"] for entry in public_pages(self.site)}
        self.assertGreater(after["/en/services/sport/"], before["/en/services/sport/"])
        before = after
        self.photo.delete()
        self.site.refresh_from_db()
        after = {entry["path"]: entry["updated"] for entry in public_pages(self.site)}
        self.assertGreater(after["/en/work/"], before["/en/work/"])

    @override_settings(LLMS_TXT_ENABLED=False)
    def test_optional_guide_and_mirrors_can_be_disabled(self):
        for path in ("/llms.txt", "/en/about/index.md", "/fr/services/sports/index.md"):
            self.assertEqual(self.get(path).status_code, 404)
        response = self.get("/en/about/")
        self.assertNotContains(response, 'type="text/markdown"')
        self.assertNotContains(response, 'href="/llms.txt"')

    def test_shortlist_validation_is_bounded_ordered_and_rejects_untrusted_values(self):
        identifiers = [str(self.photo.identifier), str(self.draft.identifier), str(uuid.uuid4()), str(self.photo.identifier)]
        self.assertEqual([photo.pk for photo in public_selection(identifiers)], [self.photo.pk])
        for values in (None, {}, "not a list", [12], ["private-original.jpg"], [str(self.photo.identifier)] * 13):
            with self.subTest(values=values), self.assertRaises(ValueError):
                public_selection(values)
        response = self.get("/fr/shortlist/photos/?ids=" + ",".join(identifiers))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(response.json()["photos"][0]["title"], self.photo.title_fr)
        self.assertEqual(len(response.json()["photos"]), 1)
        self.assertEqual(self.get("/en/shortlist/photos/?ids=bogus").status_code, 400)
        self.assertTrue(self.get("/en/shortlist/").context["seo"]["noindex"])

    def test_behind_frame_is_optional_owner_entered_localized_and_escaped(self):
        path = f"/en/photos/{self.photo.identifier}/"
        self.assertNotContains(self.get(path), '<details class="behind-frame"')
        self.photo.behind_frame_en = "An owner-written note. <script>not HTML</script>"
        self.photo.behind_frame_fr = "Une note du photographe."
        self.photo.save()
        response = self.get(path)
        self.assertContains(response, "An owner-written note.")
        self.assertNotContains(response, "<script>not HTML</script>")
        self.assertContains(self.get(f"/fr/photos/{self.photo.identifier}/"), self.photo.behind_frame_fr)
        self.story.behind_frame_fr = "Le point de vue du photographe."
        self.story.save()
        self.assertContains(self.get("/fr/stories/the-effort/index.md"), self.story.behind_frame_fr)

    def test_service_seed_preserves_owner_edits_and_keeps_company_credits_hidden(self):
        call_command("seed_services", stdout=io.StringIO())
        service = ServicePage.objects.get(key="sports-montreal")
        service.title_en = "Owner-approved title"
        service.save()
        call_command("seed_services", stdout=io.StringIO())
        service.refresh_from_db()
        self.assertEqual(service.title_en, "Owner-approved title")
        self.assertEqual(ServicePage.objects.count(), 4)
        self.assertFalse(PartnerCredit.objects.filter(active=True).exists())
        for path in ("/en/", "/en/about/", "/llms.txt", "/en/about/index.md"):
            for name in PartnerCredit.objects.values_list("display_name", flat=True):
                self.assertNotContains(self.get(path), name)

    def test_owner_admin_forms_render_with_content_warnings_and_ordered_inlines(self):
        user = get_user_model().objects.create_user("owner", is_staff=True, is_superuser=True)
        self.client.force_login(user)
        for model, obj in (("servicepage", self.service), ("sitesettings", self.site), ("story", self.story)):
            self.assertEqual(self.get(reverse(f"admin:portfolio_{model}_change", args=[obj.pk])).status_code, 200)
        self.assertContains(self.get("/admin/portfolio/servicepage/"), "SEO overrides missing")

    def test_origin_validation_rejects_credentials_paths_whitespace_and_invalid_ports(self):
        self.assertTrue(valid_origin("https://portfolio.example/", True))
        for value in ("http://portfolio.example", "https://name:secret@portfolio.example", "https://portfolio.example/path",
                      "https://portfolio.example?x=1", "https://port folio.example", "https://portfolio.example\n",
                      "https://portfolio.example:999999", "https://portfolio.example:0", "//portfolio.example"):
            self.assertFalse(valid_origin(value, True), value)
        with override_settings(PUBLIC_SITE_URL="http://portfolio.example"):
            self.assertIn("portfolio.E001", [issue.id for issue in discovery_configuration(None)])

    @override_settings(GOOGLE_SITE_VERIFICATION="owner-google", BING_SITE_VERIFICATION="owner-bing")
    def test_verification_tags_are_configured_not_invented(self):
        response = self.get("/en/")
        self.assertContains(response, 'name="google-site-verification" content="owner-google"')
        self.assertContains(response, 'name="msvalidate.01" content="owner-bing"')

    @patch("portfolio.management.commands.notify_indexnow.requests.post")
    def test_indexnow_disabled_never_calls_external_provider(self, post):
        with self.assertRaises(CommandError):
            call_command("notify_indexnow", stdout=io.StringIO())
        self.assertEqual(self.get("/indexnow/owner-key123.txt").status_code, 404)
        post.assert_not_called()

    @override_settings(INDEXNOW_ENABLED=True, INDEXNOW_KEY="owner-key123")
    @patch("portfolio.management.commands.notify_indexnow.time.sleep")
    @patch("portfolio.management.commands.notify_indexnow.requests.post")
    def test_indexnow_submits_only_canonical_public_urls_with_timeout_and_retries(self, post, sleep):
        post.side_effect = [Mock(status_code=503), Mock(status_code=202)]
        call_command("notify_indexnow", stdout=io.StringIO())
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["host"], "portfolio.example")
        self.assertEqual(payload["keyLocation"], "https://portfolio.example/indexnow/owner-key123.txt")
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 15))
        self.assertTrue(all(url.startswith("https://portfolio.example/") for url in payload["urlList"]))
        self.assertFalse(any(str(self.draft.identifier) in url or "shortlist" in url or "index.md" in url for url in payload["urlList"]))
        self.assertContains(self.get("/indexnow/owner-key123.txt"), "owner-key123")
        self.assertEqual(self.get("/indexnow/wrong-key.txt").status_code, 404)

    @override_settings(INDEXNOW_ENABLED=True, INDEXNOW_KEY="owner-key123")
    @patch("portfolio.management.commands.notify_indexnow.requests.post")
    def test_indexnow_dry_run_and_rejected_urls_never_call_provider(self, post):
        call_command("notify_indexnow", dry_run=True, stdout=io.StringIO())
        for url in ("https://external.example/en/", "/en/work/?category=race-day", "/en/services/sport/index.md",
                    f"/en/photos/{self.draft.identifier}/"):
            with self.subTest(url=url), self.assertRaises(CommandError):
                call_command("notify_indexnow", url=[url], stdout=io.StringIO())
        post.assert_not_called()
