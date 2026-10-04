import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override
from PIL import Image

from .models import Category, Photo, PhotoRendition, SiteSettings, Story, StoryPhoto, localized
from .services.content import lightbox_data, rendition_data
from .services.images import process_photo, validate_source


def image_upload(size=(800, 500), orientation=None):
    image = Image.new("RGB", size, "#458476")
    stream = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
        exif[315] = "Private source metadata"
    image.save(stream, "JPEG", exif=exif)
    return SimpleUploadedFile("photo.jpg", stream.getvalue(), content_type="image/jpeg")


class MediaTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.storage_override = override_settings(STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                        "OPTIONS": {"location": root / "public", "base_url": "/media/"}},
            "originals": {"BACKEND": "portfolio.storage.PrivateFileSystemStorage",
                          "OPTIONS": {"location": root / "private"}},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        })
        self.storage_override.enable()
        self.addCleanup(self.storage_override.disable)


class PublicationTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(slug="race-day", name_en="Race day", name_fr="Jour de course")
        self.public = self.make_photo("Visible moment", "published")
        self.draft = self.make_photo("Secret draft title", "draft")
        self.category.cover_photo = self.public
        self.category.save()
        SiteSettings.objects.create(hero_photo=self.public)
        self.story = Story.objects.create(slug="race-day", title_en="Race day", introduction_en="The moments of effort.",
                                          cover_photo=self.public, status="published")
        StoryPhoto.objects.create(story=self.story, photo=self.public, order=1)
        StoryPhoto.objects.create(story=self.story, photo=self.draft, order=2)

    def make_photo(self, title, status):
        photo = Photo.objects.create(title_en=title, alt_en=title, source="private.jpg", width=800, height=500,
                                     processing_status="ready", status=status, featured=True)
        PhotoRendition.objects.create(photo=photo, file=f"photos/{photo.identifier}.jpeg", width=800, height=500,
                                     format="jpeg", byte_size=100)
        photo.categories.add(self.category)
        return photo

    def test_drafts_are_excluded_from_pages_lightbox_and_sitemap(self):
        for path in ("/en/", "/en/work/", "/en/stories/race-day/", "/sitemap.xml"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.draft.title_en)
            self.assertNotContains(response, str(self.draft.identifier))
        self.assertEqual(self.client.get(reverse("photo", args=[self.draft.identifier])).status_code, 404)

    def test_unpublishing_a_cover_removes_the_story_and_hero(self):
        self.public.status = "draft"
        self.public.save(update_fields=["status"])
        self.assertEqual(self.client.get("/en/stories/race-day/").status_code, 404)
        self.assertNotContains(self.client.get("/en/"), str(self.public.identifier))
        self.assertNotContains(self.client.get("/sitemap.xml"), "/stories/race-day/")

    def test_stories_are_removed_from_navigation_and_home_without_deleting_content(self):
        for language in ("en", "fr"):
            for route in ("", "work/", "services/", "about/", "contact/"):
                with self.subTest(language=language, route=route):
                    response = self.client.get(f"/{language}/{route}")
                    self.assertEqual(response.status_code, 200)
                    self.assertNotContains(response, f'href="/{language}/stories/"')
                    for destination in ("work", "services", "about", "contact"):
                        self.assertContains(response, f'href="/{language}/{destination}/"')
                    if not route:
                        self.assertNotContains(response, 'class="section-shell stories-section"')
                        self.assertNotIn("stories", response.context)
            self.assertEqual(self.client.get(f"/{language}/stories/").status_code, 200)
            self.assertEqual(self.client.get(f"/{language}/stories/{self.story.slug}/").status_code, 200)
        self.assertTrue(Story.objects.filter(pk=self.story.pk, status="published").exists())

    def test_depth_script_is_homepage_only_and_requires_a_public_hero(self):
        for language in ("en", "fr"):
            response = self.client.get(f"/{language}/")
            self.assertContains(response, 'type="module" src="/static/js/hero-depth.js"')
            self.assertContains(response, "(max-width: 360px) 593px, (max-width: 600px) 663px, 109vw")
            self.assertContains(response, 'fetchpriority="high"')
            for route in ("work/", "about/", "contact/"):
                self.assertNotContains(self.client.get(f"/{language}/{route}"), "hero-depth.js")
        self.public.status = "draft"
        self.public.save(update_fields=["status"])
        self.assertNotContains(self.client.get("/en/"), "hero-depth.js")

    def test_failed_processing_excludes_previously_published_photos(self):
        self.public.processing_status = "failed"
        self.public.save(update_fields=["processing_status"])
        self.assertNotContains(self.client.get("/en/work/"), self.public.title_en)

    def test_category_filter_empty_invalid_and_unknown(self):
        Category.objects.create(slug="empty", name_en="Empty")
        response = self.client.get("/en/work/?category=race-day")
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(self.client.get("/en/work/?category=empty").status_code, 200)
        self.assertNotContains(self.client.get("/en/work/"), 'category=empty')
        self.assertEqual(self.client.get("/en/work/?category=unknown").status_code, 404)
        self.assertEqual(self.client.get("/en/work/?category=../../../").status_code, 404)
        self.assertEqual(self.client.get("/en/work/?category=").status_code, 200)

    def test_pagination_keeps_filter_and_has_no_duplicates(self):
        for number in range(20):
            self.make_photo(f"Moment {number}", "published")
        first = self.client.get("/en/work/?category=race-day")
        second = self.client.get("/en/work/?category=race-day&page=2")
        self.assertEqual(len(first.context["page"]), 18)
        self.assertEqual(len(second.context["page"]), 3)
        self.assertContains(first, 'page=2&amp;category=race-day')
        self.assertFalse(set(p.pk for p in first.context["page"]) & set(p.pk for p in second.context["page"]))

    def test_language_switch_retains_page_and_filter_with_content_fallback(self):
        response = self.client.get("/en/work/?category=race-day")
        self.assertContains(response, '/fr/work/?category=race-day')
        response = self.client.get("/fr/work/?category=race-day")
        self.assertContains(response, "Jour de course")
        self.assertContains(response, "S\u00e9lection de photos")
        self.assertContains(response, self.public.title_en)
        with override("fr"):
            self.assertEqual(localized(self.public, "title"), self.public.title_en)

    def test_unpublished_cover_is_rejected_by_owner_settings(self):
        site = SiteSettings.objects.get()
        site.hero_photo = self.draft
        with self.assertRaises(ValidationError):
            site.full_clean()

    def test_missing_settings_and_photos_render_gracefully(self):
        SiteSettings.objects.all().delete()
        Photo.objects.all().delete()
        for path in ("/en/", "/en/work/", "/en/about/", "/en/contact/"):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_about_uses_owner_portrait_in_both_languages_without_adding_to_work(self):
        site = SiteSettings.objects.get()
        site.instagram_url = "https://www.instagram.com/mrsaintj/"
        site.linkedin_url = "https://www.linkedin.com/in/mrsaintj123/"
        site.save()
        count = Photo.objects.count()
        for language, alt in (("en", "Portrait of Justin St-Laurent"), ("fr", "Portrait de Justin St-Laurent")):
            response = self.client.get(f"/{language}/about/")
            self.assertContains(response, "/static/images/justin-st-laurent.jpg")
            self.assertContains(response, alt)
            self.assertContains(response, 'width="959" height="960"')
            self.assertContains(response, site.instagram_url)
            self.assertContains(response, site.linkedin_url)
            self.assertContains(response, site.flickr_url)
            self.assertNotContains(response, f'src="{self.public.renditions.first().file.url}"')
            self.assertNotContains(self.client.get(f"/{language}/work/"), 'src="/static/images/justin-st-laurent.jpg"')
        self.assertEqual(Photo.objects.count(), count)

    def test_private_original_requires_staff_and_admin_form_renders(self):
        actual = Photo.objects.create(title_en="Upload", alt_en="Upload", source=image_upload((120, 80)))
        url = reverse("private-original", args=[actual.identifier])
        preview = reverse("private-preview", args=[actual.renditions.first().pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.get(preview).status_code, 302)
        user = get_user_model().objects.create_user("owner", is_staff=True, is_superuser=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code, 200)
        preview_response = self.client.get(preview)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_response["Cache-Control"], "private, no-store")
        preview_response.close()
        self.assertEqual(self.client.get(reverse("admin:portfolio_photo_change", args=[actual.pk])).status_code, 200)
        with self.assertRaises(ValueError):
            _ = actual.source.url

    def test_public_media_route_serves_renditions_but_never_drafts_or_sources(self):
        photo = Photo.objects.create(title_en="Media", alt_en="Media", source=image_upload((120, 80)))
        photo.status = "published"
        photo.save()
        url = photo.renditions.filter(format="jpeg").first().file.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        response.close()
        self.assertEqual(self.client.get(f"/media/{photo.source.name}").status_code, 404)
        photo.status = "draft"
        photo.save()
        self.assertEqual(self.client.get(url).status_code, 404)


class ImageProcessingTests(MediaTestCase):
    def test_multi_picture_jpeg_uses_only_the_primary_photo_without_private_metadata(self):
        stream = io.BytesIO()
        primary = Image.new("RGB", (120, 80), (30, 150, 40))
        auxiliary = Image.new("RGB", (40, 30), (210, 20, 10))
        exif = Image.Exif()
        exif[315] = "Private source metadata"
        primary.save(stream, "MPO", save_all=True, append_images=[auxiliary], exif=exif)
        upload = SimpleUploadedFile("camera.jpg", stream.getvalue(), content_type="image/jpeg")
        validate_source(upload)
        photo = Photo.objects.create(title_en="Camera original", alt_en="Camera original", source=upload)
        self.assertEqual(photo.processing_status, "ready")
        self.assertEqual((photo.width, photo.height), (120, 80))
        for rendition in photo.renditions.all():
            with rendition.file.open("rb") as file, Image.open(file) as image:
                self.assertEqual(getattr(image, "n_frames", 1), 1)
                self.assertFalse(image.getexif())
                red, green, blue = image.convert("RGB").getpixel((0, 0))
                self.assertGreater(green, red)

    def test_exif_orientation_dimensions_metadata_and_no_upscaling(self):
        photo = Photo.objects.create(title_en="Turned photo", alt_en="Turned photo", source=image_upload((800, 500), orientation=6))
        self.assertEqual((photo.width, photo.height), (500, 800))
        self.assertEqual(photo.processing_status, "ready")
        self.assertSetEqual(set(photo.renditions.values_list("format", flat=True)), {"jpeg", "webp"})
        for rendition in photo.renditions.all():
            with rendition.file.open("rb") as file, Image.open(file) as image:
                self.assertEqual(image.size, (rendition.width, rendition.height))
                self.assertLessEqual(max(image.size), 800)
                self.assertFalse(image.getexif())
        data = rendition_data(photo)
        self.assertIn("500w", data["jpeg_srcset"])
        self.assertNotIn("800w", data["jpeg_srcset"])

    def test_corrupt_and_oversized_inputs_fail_cleanly(self):
        with self.assertRaises(ValidationError):
            validate_source(SimpleUploadedFile("bad.jpg", b"not an image"))
        with override_settings(PHOTO_MAX_PIXELS=100):
            with self.assertRaises(ValidationError):
                validate_source(image_upload((20, 20)))
        with override_settings(PHOTO_MAX_BYTES=100):
            with self.assertRaises(ValidationError):
                validate_source(image_upload((20, 20)))

    def test_regeneration_is_idempotent_and_source_replacement_versions_urls(self):
        photo = Photo.objects.create(title_en="Photo", alt_en="Photo", source=image_upload((100, 60)))
        keys = set(photo.renditions.values_list("file", flat=True))
        modified = photo.updated_at
        self.assertTrue(all("photo-" in key and "-v3/" in key for key in keys))
        self.assertTrue(process_photo(photo))
        self.assertEqual(keys, set(photo.renditions.values_list("file", flat=True)))
        self.assertEqual(modified, photo.updated_at)
        photo.source = image_upload((120, 80))
        photo.save()
        self.assertNotEqual(keys, set(photo.renditions.values_list("file", flat=True)))

    def test_native_resolution_above_2560_is_available_in_both_formats_and_lightbox(self):
        from PIL.JpegImagePlugin import get_sampling
        photo = Photo.objects.create(title_en="Native detail", alt_en="Native detail", source=image_upload((3200, 1800)))
        for fmt in ("jpeg", "webp"):
            full = photo.renditions.filter(format=fmt).order_by("-width").first()
            self.assertEqual((full.width, full.height), (3200, 1800))
            with full.file.open("rb") as file, Image.open(file) as image:
                self.assertEqual(image.size, (3200, 1800))
                self.assertFalse(image.getexif())
                if fmt == "jpeg":
                    self.assertEqual(get_sampling(image), 0)
                    self.assertEqual(image.quantization[0][0], 2)
        data = rendition_data(photo)
        self.assertIn("3200w", data["jpeg_srcset"])
        self.assertIn("3200w", data["webp_srcset"])
        self.assertEqual(data["full"], photo.renditions.get(format="jpeg", width=3200).file.url)
        self.assertEqual(data["social"], photo.renditions.get(format="jpeg", width=1280).file.url)
        self.assertEqual(lightbox_data([photo])[0]["url"], data["full"])
        photo.status = "published"
        photo.save()
        response = self.client.get(reverse("photo", args=[photo.identifier]))
        self.assertTrue(response.context["seo"]["image"].endswith(data["social"]))
        graph = json.loads(response.context["seo"]["structured_data"])["@graph"]
        metadata = next(item for item in graph if item["@type"] == "ImageObject")
        self.assertEqual((metadata["width"], metadata["height"]), (3200, 1800))
        self.assertTrue(metadata["contentUrl"].endswith(data["full"]))

    def test_quality_upgrade_versions_existing_cached_renditions(self):
        photo = Photo.objects.create(title_en="Quality", alt_en="Quality", source=image_upload((120, 80)))
        rendition = photo.renditions.first()
        old_name = rendition.file.name.replace("-v3/", "-v2/")
        rendition.file.storage.save(old_name, ContentFile(b"old compressed pixels"))
        rendition.file.name = old_name
        rendition.save()
        self.assertTrue(process_photo(photo))
        self.assertFalse(photo.renditions.filter(file__contains="-v2/").exists())
        self.assertTrue(all("-v3/" in name for name in photo.renditions.values_list("file", flat=True)))

    def test_failure_is_recorded_and_cannot_publish(self):
        photo = Photo.objects.create(title_en="Broken", alt_en="Broken", source=SimpleUploadedFile("bad.jpg", b"bad"))
        self.assertEqual(photo.processing_status, "failed")
        self.assertTrue(photo.processing_error)
        photo.status = "published"
        with self.assertRaises(ValidationError):
            photo.full_clean()


class SeedTests(MediaTestCase):
    @patch("portfolio.management.commands.import_portfolio_photos.download_image")
    def test_targeted_source_upgrade_preserves_other_photos_and_owner_framing(self, download):
        download.side_effect = lambda url: image_upload((120, 80))
        output = io.StringIO()
        call_command("import_portfolio_photos", stdout=output)
        photo = Photo.objects.get(flickr_id="53984262444")
        original = photo.source.name
        photo.title_en = "Owner's water photograph"
        photo.focal_x = 31
        photo.save()
        other_photos = Photo.objects.exclude(pk=photo.pk).order_by("pk")
        before = list(other_photos.values("pk", "source", "width", "height", "status", "title_en", "updated_at"))
        site = SiteSettings.objects.get()
        site.hero_focal_x, site.hero_focal_y = 42, 33
        site.mobile_focal_x, site.mobile_focal_y = 51, 37
        site.save()
        download.reset_mock()
        download.side_effect = lambda url: image_upload((2048, 1280))

        call_command("import_portfolio_photos", flickr_id="53984262444", replace_files=True, stdout=output)

        download.assert_called_once()
        self.assertTrue(download.call_args.args[0].endswith("_o.jpg"))
        photo.refresh_from_db()
        site.refresh_from_db()
        self.assertEqual((photo.width, photo.height), (2048, 1280))
        self.assertEqual(photo.title_en, "Owner's water photograph")
        self.assertEqual(photo.focal_x, 31)
        self.assertEqual(photo.status, "published")
        self.assertNotEqual(photo.source.name, original)
        self.assertEqual(photo.renditions.order_by("-width").first().width, 2048)
        self.assertEqual(list(other_photos.values("pk", "source", "width", "height", "status", "title_en", "updated_at")), before)
        self.assertEqual(site.hero_photo_id, photo.pk)
        self.assertEqual((site.hero_focal_x, site.hero_focal_y, site.mobile_focal_x, site.mobile_focal_y), (42, 33, 51, 37))

    @patch("portfolio.management.commands.import_portfolio_photos.download_image")
    def test_unknown_target_is_rejected_before_seeding_or_downloading(self, download):
        with self.assertRaisesMessage(CommandError, "not in the approved manifest"):
            call_command("import_portfolio_photos", flickr_id="unknown", stdout=io.StringIO())
        download.assert_not_called()
        self.assertFalse(Photo.objects.exists())
        self.assertFalse(SiteSettings.objects.exists())

    @patch("portfolio.management.commands.import_portfolio_photos.download_image")
    def test_original_source_is_preferred_and_fallbacks_are_explicit(self, download):
        manifest = json.loads((Path(__file__).resolve().parent.parent / "content/seed_photos.json").read_text())
        hero = next(entry for entry in manifest if entry["id"] == "53984262444")
        output, errors = io.StringIO(), io.StringIO()
        download.side_effect = [OSError("Original unavailable"), image_upload((200, 120))]
        call_command("import_portfolio_photos", flickr_id=hero["id"], stdout=output, stderr=errors)
        self.assertEqual([call.args[0] for call in download.call_args_list], [hero["original_url"], hero["larger_url"]])
        self.assertIn("largest source unavailable", errors.getvalue())
        self.assertEqual(Photo.objects.get(flickr_id=hero["id"]).width, 200)

        download.reset_mock()
        download.side_effect = [OSError("Original unavailable"), OSError("Large unavailable"), image_upload((120, 80))]
        call_command("import_portfolio_photos", flickr_id=hero["id"], replace_files=True, stdout=output, stderr=errors)
        self.assertEqual([call.args[0] for call in download.call_args_list], [hero["original_url"], hero["larger_url"], hero["url"]])

    def test_every_manifest_photo_records_a_real_original_and_its_dimensions(self):
        manifest = json.loads((Path(__file__).resolve().parent.parent / "content/seed_photos.json").read_text())
        for entry in manifest:
            self.assertTrue(entry["original_url"].endswith(f"_o.jpg"))
            self.assertIn(f"/{entry['id']}_", entry["original_url"])
            self.assertGreater(entry["original_width"], 0)
            self.assertGreater(entry["original_height"], 0)
        hero = next(entry for entry in manifest if entry["id"] == "53984262444")
        self.assertEqual((hero["original_width"], hero["original_height"]), (4957, 3098))

    @patch("portfolio.management.commands.import_portfolio_photos.download_image")
    def test_original_swimming_hero_can_be_restored_explicitly_without_reimporting_files(self, download):
        download.side_effect = lambda url: image_upload((120, 80))
        output = io.StringIO()
        call_command("import_portfolio_photos", stdout=output)
        site = SiteSettings.objects.get()
        self.assertEqual(site.hero_photo.flickr_id, "53984262444")
        site.hero_photo = Photo.objects.get(flickr_id="52988480862")
        site.hero_focal_y = 60
        site.mobile_focal_y = 55
        site.save()
        call_command("import_portfolio_photos", stdout=output)
        site.refresh_from_db()
        self.assertEqual(site.hero_photo.flickr_id, "52988480862")

        call_command("import_portfolio_photos", set_hero=True, stdout=output)
        site.refresh_from_db()
        self.assertEqual(site.hero_photo.flickr_id, "53984262444")
        self.assertEqual((site.hero_focal_x, site.hero_focal_y), (50, 48))
        self.assertEqual((site.mobile_focal_x, site.mobile_focal_y), (50, 38))
        self.assertEqual(Photo.objects.public().count(), 25)
        self.assertEqual(download.call_count, 25)
        for language in ("en", "fr"):
            self.assertEqual(self.client.get(f"/{language}/").context["hero"].flickr_id, "53984262444")

    @patch("portfolio.management.commands.import_portfolio_photos.download_image")
    def test_seed_and_import_repeat_without_duplicates_or_overwriting_edits(self, download):
        download.side_effect = lambda url: image_upload((120, 80))
        output = io.StringIO()
        call_command("import_portfolio_photos", stdout=output)
        site = SiteSettings.objects.get()
        site.biography_en = "Owner's edited biography"
        site.hero_photo = Photo.objects.get(flickr_id="54689711439")
        site.hero_focal_x = 42
        site.hero_focal_y = 33
        site.save()
        photo = Photo.objects.first()
        photo.title_en = "Owner's edited title"
        photo.status = "draft"
        photo.save()
        call_command("import_portfolio_photos", stdout=output)
        photo.refresh_from_db()
        site.refresh_from_db()
        self.assertEqual(Photo.objects.count(), 25)
        self.assertEqual(Category.objects.count(), 4)
        self.assertEqual(Story.objects.count(), 3)
        self.assertEqual(photo.title_en, "Owner's edited title")
        self.assertEqual(photo.status, "draft")
        self.assertEqual(site.biography_en, "Owner's edited biography")
        self.assertEqual(site.hero_photo.flickr_id, "54689711439")
        self.assertEqual((site.hero_focal_x, site.hero_focal_y), (42, 33))
        self.assertEqual(download.call_count, 25)

    @patch("portfolio.management.commands.import_portfolio_photos.download_image")
    def test_full_album_extends_existing_selection_and_is_complete_across_pages(self, download):
        download.side_effect = lambda url: image_upload((120, 80))
        manifest = json.loads((Path(__file__).resolve().parent.parent / "content/seed_photos.json").read_text())
        starter = Path(self.directory.name) / "starter.json"
        starter.write_text(json.dumps(manifest[:7]))
        output = io.StringIO()
        call_command("import_portfolio_photos", manifest=str(starter), stdout=output)
        initial = Photo.objects.get(flickr_id="53984262444")
        original_source = initial.source.name
        initial.title_en = "Owner's water photograph"
        initial.focal_x = 31
        initial.save()
        initial.categories.clear()
        featured_ids = set(Photo.objects.filter(featured=True).values_list("flickr_id", flat=True))
        hero = SiteSettings.objects.get().hero_photo_id

        call_command("import_portfolio_photos", stdout=output)
        initial.refresh_from_db()
        self.assertEqual(initial.title_en, "Owner's water photograph")
        self.assertEqual(initial.focal_x, 31)
        self.assertEqual(initial.source.name, original_source)
        self.assertFalse(initial.categories.exists())
        self.assertEqual(SiteSettings.objects.get().hero_photo_id, hero)
        self.assertSetEqual(set(Photo.objects.filter(featured=True).values_list("flickr_id", flat=True)), featured_ids)
        self.assertEqual(download.call_count, 25)
        expected_ids = {entry["id"] for entry in manifest}
        self.assertEqual(len(manifest), 25)
        self.assertEqual(len(expected_ids), 25)
        self.assertSetEqual(set(Photo.objects.public().values_list("flickr_id", flat=True)), expected_ids)
        for language in ("en", "fr"):
            first = self.client.get(f"/{language}/work/")
            second = self.client.get(f"/{language}/work/?page=2")
            self.assertEqual(len(first.context["page"]), 18)
            self.assertEqual(len(second.context["page"]), 7)
            displayed = list(first.context["page"]) + list(second.context["page"])
            self.assertSetEqual({photo.flickr_id for photo in displayed}, expected_ids)
            for response in (first, second):
                self.assertEqual(len(response.context["lightbox_photos"]), len(response.context["page"]))

    @patch("portfolio.management.commands.import_portfolio_photos.download_image")
    def test_failed_initial_import_can_resume(self, download):
        from django.core.management.base import CommandError
        download.side_effect = OSError("Unavailable")
        with self.assertRaises(CommandError):
            call_command("import_portfolio_photos", stdout=io.StringIO(), stderr=io.StringIO())
        download.side_effect = lambda url: image_upload((100, 60))
        call_command("import_portfolio_photos", stdout=io.StringIO())
        self.assertEqual(Photo.objects.public().count(), 25)
