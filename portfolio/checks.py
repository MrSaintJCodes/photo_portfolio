import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Error, Warning, register


def valid_origin(value, require_https=False):
    if not isinstance(value, str) or any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urlsplit(value)
        return bool(parsed.hostname and parsed.port != 0 and parsed.scheme in ({"https"} if require_https else {"http", "https"})
                    and not parsed.username and not parsed.password and parsed.path in ("", "/")
                    and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


@register()
def discovery_configuration(app_configs, **kwargs):
    issues = []
    if settings.INDEXING_ENABLED and not valid_origin(settings.PUBLIC_SITE_URL, require_https=True):
        issues.append(Error("Indexing requires a preferred HTTPS PUBLIC_SITE_URL origin without a path or credentials.", id="portfolio.E001"))
    elif settings.PUBLIC_SITE_URL and not valid_origin(settings.PUBLIC_SITE_URL):
        issues.append(Warning("PUBLIC_SITE_URL is not a valid origin; metadata will use the local development origin.", id="portfolio.W001"))
    elif not settings.DEBUG and not settings.PUBLIC_SITE_URL:
        issues.append(Warning("Set PUBLIC_SITE_URL before launch. Request Host headers are never used for metadata.", id="portfolio.W002"))
    if settings.INDEXNOW_ENABLED and (not valid_origin(settings.PUBLIC_SITE_URL, True)
                                    or not re.fullmatch(r"[A-Za-z0-9-]{8,128}", settings.INDEXNOW_KEY)):
        issues.append(Error("IndexNow requires an HTTPS public origin and an 8-128 character ownership key.", id="portfolio.E002"))
    return issues
