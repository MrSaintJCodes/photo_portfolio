from django.urls import reverse

from portfolio.models import Photo, SiteSettings


def get_site(request=None):
    if request is not None and hasattr(request, "portfolio_site"):
        return request.portfolio_site
    site = SiteSettings.objects.select_related("hero_photo", "mobile_hero_photo", "services_cover_photo").prefetch_related(
        "hero_photo__renditions", "mobile_hero_photo__renditions", "services_cover_photo__renditions").first() or SiteSettings()
    if request is not None:
        request.portfolio_site = site
    return site


def rendition_data(photo):
    if not photo:
        return {}
    renditions = list(photo.renditions.all())
    webp = [r for r in renditions if r.format == "webp"]
    jpeg = [r for r in renditions if r.format == "jpeg"]
    if not jpeg:
        return {}
    fallback = next((r for r in jpeg if r.width >= 768), jpeg[-1])
    social = next((r for r in jpeg if r.width >= 1280), jpeg[-1])
    return {"src": fallback.file.url,
            "webp_srcset": ", ".join(f"{r.file.url} {r.width}w" for r in webp),
            "jpeg_srcset": ", ".join(f"{r.file.url} {r.width}w" for r in jpeg),
            "full": jpeg[-1].file.url, "social": social.file.url, "width": photo.width, "height": photo.height,
            "alt": photo.alt, "focal_x": photo.focal_x, "focal_y": photo.focal_y}


def lightbox_data(photos):
    return [{"id": str(photo.identifier), "detail": reverse("photo", args=[photo.identifier]),
             "url": rendition_data(photo).get("full"), "alt": photo.alt,
             "caption": photo.caption or photo.title, "source": photo.source_url} for photo in photos]


def public_hero(site):
    if site.hero_photo and site.hero_photo.is_public:
        return site.hero_photo
    return Photo.objects.prepared().filter(featured=True).first()
