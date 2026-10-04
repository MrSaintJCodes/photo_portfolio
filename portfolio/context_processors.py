from django.conf import settings
from django.utils.translation import get_language

from .services.content import get_site
from .services.seo import build_metadata


def site_identity(request):
    site = get_site(request)
    language = (get_language() or "en").split("-")[0]
    other_language = "fr" if language == "en" else "en"
    seo = build_metadata(request, site)
    return {"site": site, "site_name": site.brand, "photographer_name": site.photographer_name, "seo": seo,
            "language": language, "other_language": other_language,
            "language_switch_url": seo["language_switch"],
            "active_page": request.resolver_match.url_name if request.resolver_match else "",
            "llms_enabled": settings.LLMS_TXT_ENABLED,
            "pixel_camera_enabled": settings.PIXEL_CAMERA_TRANSITIONS_ENABLED,
            "google_verification": settings.GOOGLE_SITE_VERIFICATION,
            "bing_verification": settings.BING_SITE_VERIFICATION}
