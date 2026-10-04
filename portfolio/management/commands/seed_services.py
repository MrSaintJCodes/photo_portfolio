import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from portfolio.models import PartnerCredit, Photo, ServiceFAQ, ServiceOffering, ServicePage, ServicePhoto, ServiceStory, Story
from portfolio.service_content import ServiceKind


class Command(BaseCommand):
    help = "Create localized service pages once, preserving subsequent owner edits."

    def add_arguments(self, parser):
        parser.add_argument("--set-cover", choices=ServiceKind.values,
                            help="Explicitly select one offering's approved manifest photograph, preserving other edits.")

    def handle(self, *args, **options):
        entries = json.loads((settings.BASE_DIR / "content/services.json").read_text())
        for order, entry in enumerate(entries):
            copy = {key: value for key, value in entry.items() if key not in {"key", "photo_ids", "story_slugs", "questions"}}
            service, created = ServicePage.objects.get_or_create(key=entry["key"], defaults={**copy, "order": order, "status": "published"})
            if not created:
                continue
            photos = {photo.flickr_id: photo for photo in Photo.objects.public().filter(flickr_id__in=entry["photo_ids"])}
            for position, identifier in enumerate(entry["photo_ids"]):
                if identifier in photos:
                    ServicePhoto.objects.create(service=service, photo=photos[identifier], order=position)
            stories = {story.slug: story for story in Story.objects.public().filter(slug__in=entry["story_slugs"])}
            for position, slug in enumerate(entry["story_slugs"]):
                if slug in stories:
                    ServiceStory.objects.create(service=service, story=stories[slug], order=position)
            for position, question in enumerate(entry["questions"]):
                ServiceFAQ.objects.create(service=service, order=position, **question)
        offerings = json.loads((settings.BASE_DIR / "content/offerings.json").read_text())
        selected_cover = None
        if options.get("set_cover"):
            entry = next(item for item in offerings if item["key"] == options["set_cover"])
            selected_cover = Photo.objects.public().filter(flickr_id=entry["photo_id"]).first()
            if selected_cover is None:
                raise CommandError("Import the offering's approved photograph before setting its cover.")
        for order, entry in enumerate(offerings):
            copy = {key: value for key, value in entry.items() if key not in {"key", "photo_id", "detail_key"}}
            ServiceOffering.objects.get_or_create(key=entry["key"], defaults={
                **copy, "order": order, "status": "published",
                "cover_photo": Photo.objects.public().filter(flickr_id=entry["photo_id"]).first() if entry["photo_id"] else None,
                "detail_page": ServicePage.objects.filter(key=entry["detail_key"]).first(),
            })
        if selected_cover:
            offering = ServiceOffering.objects.get(key=options["set_cover"])
            if offering.cover_photo_id != selected_cover.pk:
                offering.cover_photo = selected_cover
                offering.save(update_fields=["cover_photo", "updated_at"])
        for order, name in enumerate(("Epic Action Imagery", "Sportograf", "FinisherPix")):
            PartnerCredit.objects.get_or_create(display_name=name, defaults={"order": order, "active": False})
        self.stdout.write(self.style.SUCCESS("Service pages are ready. Company credits remain hidden; existing content was preserved."))
