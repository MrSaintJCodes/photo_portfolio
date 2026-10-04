from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpResponsePermanentRedirect
from urllib.parse import urlsplit

from .checks import valid_origin


class IndexingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.INDEXING_ENABLED and valid_origin(settings.PUBLIC_SITE_URL, True) and request.method in {"GET", "HEAD"}:
            preferred = urlsplit(settings.PUBLIC_SITE_URL)
            requested = urlsplit("//" + request.get_host())
            preferred_host = (preferred.hostname.lower(), preferred.port or 443)
            try:
                if requested.port == 0:
                    raise ValueError()
                requested_host = (requested.hostname.lower(), requested.port or 443)
            except ValueError as exc:
                raise DisallowedHost("Invalid request Host port.") from exc
            if not request.path.startswith(("/healthz/", "/admin/", "/private/", "/media/")) and requested_host != preferred_host:
                return HttpResponsePermanentRedirect(settings.PUBLIC_SITE_URL.rstrip("/") + request.get_full_path())
        response = self.get_response(request)
        if not settings.INDEXING_ENABLED:
            response["X-Robots-Tag"] = "noindex, nofollow"
        elif request.GET.get("category") or "/shortlist/" in request.path:
            response.setdefault("X-Robots-Tag", "noindex, follow")
        return response
