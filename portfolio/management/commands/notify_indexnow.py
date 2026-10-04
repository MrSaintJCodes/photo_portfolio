import re
import time
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from portfolio.checks import valid_origin
from portfolio.services.content import get_site
from portfolio.services.seo import absolute_url, public_pages


class Command(BaseCommand):
    help = "Explicitly notify IndexNow of public canonical URLs. Disabled until configured."

    def add_arguments(self, parser):
        parser.add_argument("--url", action="append", help="A current public path or canonical URL; repeat as needed.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if not settings.INDEXNOW_ENABLED:
            raise CommandError("IndexNow is disabled. Configure a public origin and ownership key before activation.")
        if not valid_origin(settings.PUBLIC_SITE_URL, True) or not re.fullmatch(r"[A-Za-z0-9-]{8,128}", settings.INDEXNOW_KEY):
            raise CommandError("A valid HTTPS public origin and ownership key are required.")
        if not settings.INDEXING_ENABLED:
            raise CommandError("Indexing is disabled on this installation.")
        allowed = {absolute_url(entry["path"]) for entry in public_pages(get_site())}
        urls = list(dict.fromkeys(absolute_url(url) for url in options["url"])) if options["url"] else sorted(allowed)
        if any(url not in allowed for url in urls):
            raise CommandError("Only current public canonical URLs can be submitted; no drafts, mirrors, filters, or external hosts.")
        if options["dry_run"]:
            self.stdout.write("\n".join(urls))
            return
        payload = {"host": urlsplit(settings.PUBLIC_SITE_URL).hostname, "key": settings.INDEXNOW_KEY,
                   "keyLocation": absolute_url(f"/indexnow/{settings.INDEXNOW_KEY}.txt"), "urlList": urls}
        for attempt in range(3):
            try:
                response = requests.post("https://api.indexnow.org/indexnow", json=payload, timeout=(5, 15))
                if response.status_code in (200, 202):
                    self.stdout.write(self.style.SUCCESS(f"Notification accepted for {len(urls)} URLs. Indexing is not guaranteed."))
                    return
                if response.status_code not in (429, 500, 502, 503, 504):
                    raise CommandError(f"IndexNow rejected the notification ({response.status_code}).")
            except requests.RequestException as exc:
                if attempt == 2:
                    raise CommandError("IndexNow could not be reached after three attempts.") from exc
            if attempt < 2:
                time.sleep(2 ** attempt)
        raise CommandError("IndexNow remained unavailable after three attempts. Rerun the command later.")
