from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _, override

from .models import Category, PartnerCredit, Photo, PhotoRendition, ServiceOffering, ServicePage, ServiceSlugRedirect, SiteSettings, Story, StorySlugRedirect
from .services.content import get_site, lightbox_data, public_hero
from .service_content import audience_copy, booking_copy, planning_steps


def home(request):
    site = get_site(request)
    hero = public_hero(site)
    entrances = []
    used = []
    for slug in ("race-day", "team-sports", "athlete-stories"):
        category = Category.objects.filter(slug=slug, active=True).select_related("cover_photo").prefetch_related("cover_photo__renditions").first()
        if not category:
            continue
        cover = category.cover_photo
        if not cover or not cover.is_public:
            cover = Photo.objects.prepared().filter(categories=category).first()
        if cover:
            entrances.append({"category": category, "photo": cover})
            used.append(cover.pk)
    selected = list(Photo.objects.prepared().filter(featured=True).exclude(pk__in=used)[:6])
    request.seo_photos = list({photo.pk: photo for photo in ([hero] if hero else []) + selected}.values())
    return render(request, "portfolio/home.html", {"hero": hero, "entrances": entrances,
        "services": ServicePage.objects.public(), "partner_credits": PartnerCredit.objects.filter(active=True),
        "selected_photos": selected,
        "lightbox_photos": lightbox_data(selected)})


def work(request):
    photos = Photo.objects.prepared()
    slug = request.GET.get("category", "")
    category = None
    if slug:
        category = get_object_or_404(Category, slug=slug, active=True)
        photos = photos.filter(categories=category)
    categories = Category.objects.filter(active=True, photos__in=Photo.objects.public()).distinct()
    page = Paginator(photos, 18).get_page(request.GET.get("page"))
    request.seo_page = page
    request.seo_photos = list(page.object_list)
    return render(request, "portfolio/work.html", {"page": page, "category": category,
        "categories": categories, "lightbox_photos": lightbox_data(page.object_list),
        "page_description": _("Sport in its most decisive moments. Selected photographs by MrSaintJ Photography.")})


def photo_detail(request, identifier):
    photo = get_object_or_404(Photo.objects.prepared(), identifier=identifier)
    request.seo_object = photo
    request.seo_photos = [photo]
    return render(request, "portfolio/photo.html", {"photo": photo, "page_description": photo.alt,
        "related_stories": Story.objects.public().filter(photos=photo).distinct(),
        "related_services": ServicePage.objects.public().filter(photos=photo).distinct()})


def stories(request):
    return render(request, "portfolio/stories.html", {"stories": Story.objects.prepared(),
        "page_description": _("Action, atmosphere, and the people in between.")})


def story_detail(request, slug):
    story = Story.objects.prepared().filter(slug=slug).first()
    if not story:
        archived = StorySlugRedirect.objects.filter(slug=slug, story__in=Story.objects.public()).select_related("story").first()
        if archived:
            return HttpResponsePermanentRedirect(reverse("story", args=[archived.story.slug]))
        raise Http404()
    sequence = list(story.sequence.filter(photo__in=Photo.objects.public()).select_related("photo").prefetch_related("photo__renditions"))
    request.seo_object = story
    request.seo_photos = list({photo.pk: photo for photo in [story.cover_photo, *[item.photo for item in sequence]]}.values())
    return render(request, "portfolio/story.html", {"story": story, "sequence": sequence,
        "lightbox_photos": lightbox_data([item.photo for item in sequence]), "page_description": story.introduction})


def about(request):
    return render(request, "portfolio/about.html", {"page_description": get_site(request).biography})


def services(request):
    site = get_site(request)
    cover = site.services_cover_photo
    if not cover or not cover.is_public:
        cover = Photo.objects.prepared().filter(flickr_id="54689682884").first() or public_hero(site)
    offerings = list(ServiceOffering.objects.public().select_related("cover_photo", "detail_page").prefetch_related("cover_photo__renditions"))
    request.seo_offerings = offerings
    request.seo_photos = list({photo.pk: photo for photo in ([cover] if cover else []) +
                              [item.cover_photo for item in offerings if item.cover_photo and item.cover_photo.is_public]}.values())
    request.services_cover = cover
    return render(request, "portfolio/services.html", {"cover": cover, "offerings": offerings,
        "services": ServicePage.objects.public(), "audience": audience_copy(),
        "planning_steps": planning_steps(), "booking_copy": booking_copy()})


def service_detail(request, slug):
    language = request.LANGUAGE_CODE.split("-")[0]
    service = ServicePage.objects.public(language).filter(**{f"slug_{language}": slug}).first()
    if not service:
        archived = ServiceSlugRedirect.objects.filter(language=language, slug=slug).select_related("service").first()
        if archived and archived.service.available(language):
            return HttpResponsePermanentRedirect(archived.service.url(language))
        raise Http404()
    sequence = service.photo_sequence.filter(photo__in=Photo.objects.public()).select_related("photo").prefetch_related("photo__renditions")
    photos = [item.photo for item in sequence]
    related = service.story_sequence.filter(story__in=Story.objects.public()).select_related("story", "story__cover_photo").prefetch_related("story__cover_photo__renditions")
    request.seo_object = service
    request.seo_photos = photos
    return render(request, "portfolio/service.html", {"service": service, "photos": photos,
        "related_stories": [item.story for item in related], "questions": service.questions.filter(active=True),
        "lightbox_photos": lightbox_data(photos)})


def shortlist(request):
    return render(request, "portfolio/shortlist.html")


def privacy(request):
    return render(request, "portfolio/privacy.html")


def health(request):
    return JsonResponse({"status": "ok"})


def public_media(request, key):
    rendition = PhotoRendition.objects.filter(file=key, photo__in=Photo.objects.public()).first()
    if rendition:
        response = FileResponse(rendition.file.open("rb"), content_type="image/webp" if rendition.format == "webp" else "image/jpeg")
        response["Cache-Control"] = "public, max-age=86400"
        return response
    site = SiteSettings.objects.filter(cv=key).exclude(cv="").first()
    if site:
        return FileResponse(site.cv.open("rb"), as_attachment=True, filename="MrSaintJ-Photography-CV.pdf", content_type="application/pdf")
    raise Http404()


@staff_member_required
def private_preview(request, rendition_id):
    rendition = get_object_or_404(PhotoRendition, pk=rendition_id)
    response = FileResponse(rendition.file.open("rb"), content_type="image/webp" if rendition.format == "webp" else "image/jpeg")
    response["Cache-Control"] = "private, no-store"
    return response


@staff_member_required
def private_original(request, identifier):
    photo = get_object_or_404(Photo, identifier=identifier)
    if not photo.source:
        raise Http404()
    return FileResponse(photo.source.open("rb"), as_attachment=True, filename=f"{photo.identifier}.source")
