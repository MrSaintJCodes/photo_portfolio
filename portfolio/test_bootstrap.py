import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError

from .models import Photo, SiteSettings
from .tests import MediaTestCase, image_upload


class PreparedImportTests(MediaTestCase):
    def prepare_bundle(self):
        repo = Path(__file__).resolve().parent.parent
        root = Path(self.directory.name)
        source_dir = root / "bundled"
        source_dir.mkdir()
        hero = next(entry for entry in json.loads((repo / "content/seed_photos.json").read_text())
                    if entry["id"] == "53984262444")
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps([hero]))
        (source_dir / f"{hero['id']}.jpg").write_bytes(image_upload((120, 80)).read())
        rendition_dir = root / "prepared"
        production_database = root / "production.sqlite3"
        production_database.write_bytes(b"production database sentinel")
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{production_database}"
        result = subprocess.run(
            [sys.executable, str(repo / "scripts/prepare_photos.py"), "--manifest", str(manifest),
             "--source-dir", str(source_dir), "--output-dir", str(rendition_dir)],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(production_database.read_bytes(), b"production database sentinel")
        self.assertFalse(Photo.objects.exists())
        return {"manifest": str(manifest), "source_dir": str(source_dir),
                "rendition_dir": str(rendition_dir), "stdout": io.StringIO(), "stderr": io.StringIO()}

    @patch("portfolio.management.commands.import_portfolio_photos.download_image")
    @patch("portfolio.services.images.normalized_image", side_effect=AssertionError("Startup must not decode the original"))
    def test_prepared_import_restores_missing_files_without_rendering_or_resetting_edits(self, normalize, download):
        options = self.prepare_bundle()
        call_command("import_portfolio_photos", **options)
        photo = Photo.objects.get()
        self.assertTrue(photo.is_public)
        self.assertEqual((photo.width, photo.height), (120, 80))
        identifier = photo.identifier
        photo.title_en = "Owner's title"
        photo.status = "draft"
        photo.save()
        site = SiteSettings.objects.get()
        site.hero_focal_x = 42
        site.biography_en = "Owner's biography"
        site.save()
        original_source = photo.source.name
        photo.source.storage.delete(original_source)
        for rendition in photo.renditions.all():
            rendition.file.storage.delete(rendition.file.name)

        call_command("import_portfolio_photos", **options)
        photo.refresh_from_db()
        site.refresh_from_db()
        self.assertEqual(photo.identifier, identifier)
        self.assertEqual(photo.title_en, "Owner's title")
        self.assertEqual(photo.status, "draft")
        self.assertNotEqual(photo.source.name, original_source)
        self.assertTrue(photo.source.storage.exists(photo.source.name))
        self.assertTrue(all(r.file.storage.exists(r.file.name) for r in photo.renditions.all()))
        self.assertEqual(site.hero_photo_id, photo.pk)
        self.assertEqual(site.hero_focal_x, 42)
        self.assertEqual(site.biography_en, "Owner's biography")

        source_name = photo.source.name
        missing = photo.renditions.get(format="jpeg")
        missing.file.storage.delete(missing.file.name)
        call_command("import_portfolio_photos", **options)
        photo.refresh_from_db()
        self.assertEqual(photo.source.name, source_name)
        self.assertTrue(missing.file.storage.exists(missing.file.name))
        self.assertEqual(Photo.objects.count(), 1)
        normalize.assert_not_called()
        download.assert_not_called()

    @patch("portfolio.services.images.normalized_image", side_effect=AssertionError("Startup must not decode the original"))
    def test_incomplete_prepared_copy_fails_cleanly_and_can_resume(self, normalize):
        options = self.prepare_bundle()
        missing = Path(options["rendition_dir"]) / "53984262444/120.jpeg"
        original = missing.read_bytes()
        missing.unlink()
        with self.assertRaisesMessage(CommandError, "Incomplete imports"):
            call_command("import_portfolio_photos", **options)
        photo = Photo.objects.get()
        self.assertEqual(photo.processing_status, "failed")
        self.assertFalse(photo.renditions.exists())
        self.assertFalse(any((Path(self.directory.name) / "public/photos").rglob("*.webp")))
        missing.write_bytes(original)
        call_command("import_portfolio_photos", **options)
        photo.refresh_from_db()
        self.assertTrue(photo.is_public)
        self.assertEqual(Photo.objects.count(), 1)
        normalize.assert_not_called()

    def test_owner_replacement_keeps_its_original_when_display_images_need_repair(self):
        options = self.prepare_bundle()
        call_command("import_portfolio_photos", **options)
        photo = Photo.objects.get()
        photo.source = image_upload((160, 90))
        photo.save()
        source_name = photo.source.name
        rendition = photo.renditions.get(format="jpeg")
        rendition.file.storage.delete(rendition.file.name)
        call_command("import_portfolio_photos", **options)
        photo.refresh_from_db()
        self.assertEqual(photo.source.name, source_name)
        self.assertEqual((photo.width, photo.height), (160, 90))
        self.assertEqual(set(photo.renditions.values_list("width", "height")), {(160, 90)})

    def test_volume_mount_supplies_defaults_and_explicit_media_paths_take_precedence(self):
        repo = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        env.update(RAILWAY_VOLUME_MOUNT_PATH="/data", DEBUG="True")
        env.pop("MEDIA_ROOT", None)
        env.pop("PRIVATE_MEDIA_ROOT", None)
        code = (
            "import json\nfrom unittest.mock import patch\n"
            "with patch('dotenv.load_dotenv'):\n"
            "    from photo_portfolio import settings\n"
            "print(json.dumps([str(settings.MEDIA_ROOT), str(settings.PRIVATE_MEDIA_ROOT)]))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], cwd=repo, env=env,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), ["/data/media", "/data/private"])
        env.update(MEDIA_ROOT="", PRIVATE_MEDIA_ROOT="")
        result = subprocess.run([sys.executable, "-c", code], cwd=repo, env=env,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), ["/data/media", "/data/private"])
        env.update(MEDIA_ROOT="/uploads/public", PRIVATE_MEDIA_ROOT="/uploads/private")
        result = subprocess.run([sys.executable, "-c", code], cwd=repo, env=env,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), ["/uploads/public", "/uploads/private"])
