from django.core.management.base import BaseCommand, CommandError

from portfolio.models import Photo
from portfolio.services.images import process_photo


class Command(BaseCommand):
    help = "Rebuild public derivatives from private sources."

    def add_arguments(self, parser):
        parser.add_argument("--photo", help="Optional photo UUID")

    def handle(self, *args, **options):
        photos = Photo.objects.all()
        if options["photo"]:
            photos = photos.filter(identifier=options["photo"])
        failures = []
        for photo in photos:
            if not process_photo(photo):
                failures.append(str(photo.identifier))
        if failures:
            raise CommandError(f"Failed: {', '.join(failures)}")
        self.stdout.write(self.style.SUCCESS("Renditions rebuilt."))
