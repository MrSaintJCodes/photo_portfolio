import json
from pathlib import Path
from urllib.parse import urlparse

import requests

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from portfolio.models import Category, Photo, SiteSettings, Story, StoryPhoto
from portfolio.services.images import process_photo, validate_source


COLLECTIONS = [
    ("race-day", "Race day", "Jour de course", "The commitment. The climb. The moment you push through. A collection of effort and expression from obstacle racing.", "L'engagement. La mont\u00e9e. Le moment o\u00f9 l'on se d\u00e9passe. Une s\u00e9lection d'effort et d'expressions en course \u00e0 obstacles.", ["54594388608", "54689711439"]),
    ("in-the-game", "In the game", "Dans le jeu", "Anticipation turns into action in a fraction of a second. A collection from the court, focused on teamwork and the play at the net.", "L'anticipation devient action en une fraction de seconde. Une s\u00e9lection sur le terrain, entre travail d'\u00e9quipe et jeu au filet.", ["54083865091"]),
    ("the-people", "The people", "Les gens", "The shared effort and the joy that follows. A collection of the human moments that make an event more than a result.", "L'effort partag\u00e9 et la joie qui suit. Une s\u00e9lection de moments humains qui font d'un \u00e9v\u00e9nement bien plus qu'un r\u00e9sultat.", ["55379555324", "54689711439", "53984262444"]),
]


def download_image(url):
    if urlparse(url).scheme != "https" or urlparse(url).hostname != "live.staticflickr.com":
        raise ValueError("The portfolio importer only accepts HTTPS Flickr image URLs.")
    with requests.get(url, headers={"User-Agent": "MrSaintJ-Portfolio-Import/1.0"},
                      timeout=(5, 20), stream=True) as response:
        response.raise_for_status()
        if urlparse(response.url).hostname != "live.staticflickr.com":
            raise ValueError("Unexpected image redirect.")
        chunks = []
        size = 0
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > settings.PHOTO_MAX_BYTES:
                raise ValueError("Source exceeds the configured upload limit.")
            chunks.append(chunk)
        data = b"".join(chunks)
    file = ContentFile(data, name="flickr.jpg")
    validate_source(file)
    return file


class Command(BaseCommand):
    help = "Import the approved photographs from local sources or Flickr; preserve edits and retry incomplete imports."

    def add_arguments(self, parser):
        parser.add_argument("--manifest", default=str(settings.BASE_DIR / "content/seed_photos.json"))
        parser.add_argument("--source-dir", help="Import bundled <Flickr ID>.jpg originals from this directory without downloading.")
        parser.add_argument("--rendition-dir", help="Copy display images prepared during the build when they match the original.")
        parser.add_argument("--flickr-id", help="Import or replace only this approved Flickr photo ID.")
        parser.add_argument("--replace-files", action="store_true", help="Explicitly replace already imported source files.")
        parser.add_argument("--set-hero", action="store_true", help="Select the manifest's hero and its focal points explicitly.")

    def handle(self, *args, **options):
        entries = json.loads(Path(options["manifest"]).read_text())
        if options["flickr_id"]:
            entries = [entry for entry in entries if entry["id"] == options["flickr_id"]]
            if not entries:
                raise CommandError("This Flickr photo ID is not in the approved manifest.")
        call_command("seed_portfolio", stdout=self.stdout)
        failures = []
        for entry in entries:
            photo, created = Photo.objects.get_or_create(flickr_id=entry["id"], defaults={
                "title_en": entry["title_en"], "title_fr": entry["title_fr"],
                "alt_en": entry["alt_en"], "alt_fr": entry["alt_fr"], "featured": entry.get("featured", True),
                "source_url": f"https://www.flickr.com/photos/194206904@N02/{entry['id']}/",
                "order": entry["order"], "focal_x": entry.get("focal_x", 50), "focal_y": entry.get("focal_y", 50),
            })
            initial_import = created or photo.width == 0
            if created:
                photo.categories.set(Category.objects.filter(slug__in=entry["categories"]))
            source_missing = not photo.source or not photo.source.storage.exists(photo.source.name)
            if options["replace_files"] or source_missing:
                try:
                    filename = f"{entry['id']}.jpg"
                    if options["source_dir"]:
                        with (Path(options["source_dir"]) / filename).open("rb") as source:
                            file = File(source, name=filename)
                            validate_source(file)
                            photo.source.save(filename, file, save=False)
                    else:
                        candidates = list(dict.fromkeys(filter(None, (entry.get("original_url"), entry.get("larger_url"), entry["url"]))))
                        file = None
                        for index, url in enumerate(candidates):
                            try:
                                file = download_image(url)
                                break
                            except Exception:
                                if index == len(candidates) - 1:
                                    raise
                        if url != candidates[0]:
                            self.stderr.write(f"{entry['id']}: largest source unavailable; imported a fallback. Retry --replace-files to upgrade.")
                        photo.source.save(filename, file, save=False)
                    photo.save()
                    process_photo(photo, rendition_dir=options["rendition_dir"])
                except Exception as exc:
                    Photo.objects.filter(pk=photo.pk).update(processing_status="failed", processing_error=str(exc))
                    failures.append(entry["id"])
                    self.stderr.write(f"{entry['id']}: {exc}")
                    continue
            else:
                renditions = list(photo.renditions.all())
                if photo.processing_status != "ready" or not renditions or any(
                    not rendition.file.storage.exists(rendition.file.name) for rendition in renditions
                ):
                    process_photo(photo, rendition_dir=options["rendition_dir"])
            if photo.processing_status != "ready":
                failures.append(entry["id"])
                continue
            # Only first-time imports publish content; repeat imports preserve editorial choices.
            if initial_import:
                photo.status = "published"
                photo.save(update_fields=["status"])
            if photo.is_public and entry.get("hero"):
                sites = SiteSettings.objects.all()
                if not options["set_hero"]:
                    sites = sites.filter(hero_photo__isnull=True)
                framing = dict(hero_photo=photo,
                    hero_focal_x=entry.get("hero_focal_x", 50), hero_focal_y=entry.get("hero_focal_y", 50),
                    mobile_focal_x=entry.get("mobile_focal_x", 50), mobile_focal_y=entry.get("mobile_focal_y", 38))
                sites.exclude(**framing).update(**framing, updated_at=timezone.now())
            if photo.is_public and entry.get("entrance"):
                Category.objects.filter(slug=entry["entrance"], cover_photo__isnull=True).update(cover_photo=photo, updated_at=timezone.now())
            self.stdout.write(f"Ready: {photo.title_en} ({photo.width} x {photo.height})")
        if failures:
            raise CommandError(f"Incomplete imports: {', '.join(failures)}. Rerun to resume.")
        for order, (slug, en, fr, intro_en, intro_fr, ids) in enumerate(COLLECTIONS):
            photos = {p.flickr_id: p for p in Photo.objects.public().filter(flickr_id__in=ids)}
            if any(photo_id not in photos for photo_id in ids):
                continue
            story, created = Story.objects.get_or_create(slug=slug, defaults={
                "title_en": en, "title_fr": fr, "introduction_en": intro_en,
                "introduction_fr": intro_fr, "cover_photo": photos[ids[0]], "order": order, "status": "published",
            })
            if created:
                for index, photo_id in enumerate(ids):
                    if photo_id in photos:
                        StoryPhoto.objects.create(story=story, photo=photos[photo_id], order=index)
        call_command("seed_services", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Approved photographs and thematic collections are ready."))
