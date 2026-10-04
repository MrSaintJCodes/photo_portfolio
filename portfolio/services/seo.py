import json
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.db.models import Max
from django.templatetags.static import static
from django.urls import reverse, translate_url
from django.utils.translation import gettext as _, override

from portfolio.checks import valid_origin
from portfolio.models import Category, Photo, ServiceOffering, ServicePage, Story
from .content import public_hero, rendition_data


def public_origin():
    return settings.PUBLIC_SITE_URL.rstrip("/") if valid_origin(settings.PUBLIC_SITE_URL) else "http://127.0.0.1:8000"


def absolute_url(path):
    parsed = urlsplit(path)
    if parsed.scheme in {"https", "http"} and parsed.netloc:
        return path
    return public_origin() + "/" + path.lstrip("/")


def description(text):
    return " ".join(text.split())[:300]


def image_object(photo, language, person_id):
    with override(language):
        path = reverse("photo", args=[photo.identifier])
        rendition = max((r for r in photo.renditions.all() if r.format == "jpeg"), key=lambda r: r.width)
        return {"@type": "ImageObject", "@id": absolute_url(path) + "#image", "url": absolute_url(path),
                "contentUrl": absolute_url(rendition.file.url), "width": rendition.width, "height": rendition.height,
                "name": photo.title, "caption": photo.caption or photo.alt,
                "creator": {"@id": person_id}, "creditText": photo.credit}


def build_metadata(request, site):
    language = request.LANGUAGE_CODE.split("-")[0]
    other_language = "fr" if language == "en" else "en"
    name = request.resolver_match.url_name if request.resolver_match else ""
    obj = getattr(request, "seo_object", None)
    photos = getattr(request, "seo_photos", [])
    hero = public_hero(site)
    social_image = rendition_data(hero).get("social", "")
    titles = {
        "home": _("Sports & Event Photographer in Montr\u00e9al"), "work": _("Selected work"),
        "stories": _("Stories & collections"), "about": _("About Justin St-Laurent"),
        "contact": _("Contact"), "privacy": _("Privacy"), "services": _("Sports photography services"),
        "shortlist": _("Saved photographs"),
    }
    descriptions = {
        "home": _("Sports and event photography by Justin St-Laurent, based on Montr\u00e9al's South Shore. Action, effort, and the people behind every moment."),
        "work": _("Sport in its most decisive moments. Selected photographs by MrSaintJ Photography."),
        "stories": _("Action, atmosphere, and the people in between."), "about": site.biography,
        "contact": site.contact_intro, "privacy": _("How inquiry information is used by MrSaintJ Photography."),
        "services": site.services_intro,
        "shortlist": _("Selected portfolio photographs for your inquiry."),
    }
    title = f"{titles.get(name, site.brand)} | {site.brand}" if name in titles else site.brand
    summary = descriptions.get(name, site.tagline)
    canonical_path = request.path
    noindex = not settings.INDEXING_ENABLED or name == "shortlist"
    language_switch = translate_url(request.get_full_path(), other_language)
    alternates = [{"language": lang, "url": absolute_url(translate_url(request.path, lang))} for lang in ("en", "fr")]
    if name == "work":
        noindex = noindex or bool(set(request.GET) - {"page"})
        page_number = getattr(getattr(request, "seo_page", None), "number", 1)
        if "category" not in request.GET and page_number > 1:
            canonical_path += "?" + urlencode({"page": page_number})
            for alternate in alternates:
                alternate["url"] += "?" + urlencode({"page": page_number})
    if isinstance(obj, (Photo, Story, ServicePage)):
        title = f"{obj.title} | {site.brand}"
        summary = (obj.caption or obj.alt) if isinstance(obj, Photo) else obj.introduction
        cover = obj if isinstance(obj, Photo) else obj.cover_photo if isinstance(obj, Story) else photos[0] if photos else hero
        social_image = rendition_data(cover).get("social", "")
    if isinstance(obj, ServicePage):
        title = getattr(obj, f"seo_title_{language}") or title
        summary = getattr(obj, f"seo_description_{language}") or summary
        alternates = [{"language": lang, "url": absolute_url(obj.url(lang))} for lang in ("en", "fr") if obj.available(lang)]
        with override(other_language):
            language_switch = obj.url(other_language) if obj.available(other_language) else reverse("services")
    elif isinstance(obj, (Photo, Story)):
        required = ("title", "alt") if isinstance(obj, Photo) else ("title", "introduction")
        alternates = [alternate for alternate in alternates if all(getattr(obj, f"{field}_{alternate['language']}") for field in required)]
        noindex = noindex or not all(getattr(obj, f"{field}_{language}") for field in required)
    if name == "about":
        social_image = static("images/justin-st-laurent.jpg")
    elif name == "services":
        social_image = rendition_data(getattr(request, "services_cover", hero)).get("social", "")
    canonical = absolute_url(canonical_path)
    person_id = absolute_url("/#photographer")
    website_id = absolute_url("/#website")
    graph = [
        {"@type": "Person", "@id": person_id, "name": site.photographer_name, "url": absolute_url("/en/about/"),
         "image": absolute_url(static("images/justin-st-laurent.jpg")),
         "sameAs": [url for url in (site.instagram_url, site.linkedin_url, site.flickr_url) if url]},
        {"@type": "WebSite", "@id": website_id, "url": absolute_url("/"), "name": site.brand,
         "inLanguage": ["en", "fr"], "publisher": {"@id": person_id}},
    ]
    webpage = {"@type": "CollectionPage" if name in {"work", "stories", "services"} else "WebPage",
               "@id": canonical + "#webpage", "url": canonical, "name": title, "description": description(summary),
               "inLanguage": language, "isPartOf": {"@id": website_id}, "about": {"@id": person_id}}
    if name == "work":
        webpage["@type"] = ["CollectionPage", "ImageGallery"]
    images = [image_object(photo, language, person_id) for photo in photos if photo.is_public]
    if images:
        webpage["primaryImageOfPage"] = {"@id": images[0]["@id"]}
        webpage["hasPart"] = [{"@id": image["@id"]} for image in images]
    if isinstance(obj, ServicePage):
        service_id = absolute_url(f"/#service-{obj.key}")
        graph.append({"@type": "Service", "@id": service_id, "name": obj.title, "description": obj.introduction,
                      "url": canonical, "provider": {"@id": person_id},
                      "areaServed": ["Montr\u00e9al", "South Shore of Montr\u00e9al, Qu\u00e9bec"]})
        webpage["mainEntity"] = {"@id": service_id}
    if name == "services":
        service_ids = []
        for offering in getattr(request, "seo_offerings", []):
            service_id = canonical + "#service-" + offering.key
            service_ids.append(service_id)
            graph.append({"@type": "Service", "@id": service_id, "name": offering.title,
                          "description": offering.description, "url": canonical + "#" + offering.key,
                          "provider": {"@id": person_id},
                          "areaServed": ["Montr\u00e9al", "Longueuil", "South Shore of Montr\u00e9al, Qu\u00e9bec"]})
        webpage["mainEntity"] = {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": index, "item": {"@id": identifier}}
            for index, identifier in enumerate(service_ids, 1)]}
    graph.extend([webpage, *images])
    with override(language):
        breadcrumbs = [{"@type": "ListItem", "position": 1, "name": site.brand, "item": absolute_url(reverse("home"))}]
        if isinstance(obj, (ServicePage, Photo, Story)):
            parent = "services" if isinstance(obj, ServicePage) else "work" if isinstance(obj, Photo) else "stories"
            breadcrumbs.append({"@type": "ListItem", "position": 2, "name": titles[parent], "item": absolute_url(reverse(parent))})
        if name != "home":
            breadcrumbs.append({"@type": "ListItem", "position": len(breadcrumbs) + 1, "name": obj.title if obj else titles.get(name, site.brand), "item": canonical})
    graph.append({"@type": "BreadcrumbList", "@id": canonical + "#breadcrumbs", "itemListElement": breadcrumbs})
    structured = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return {"title": title, "description": description(summary), "canonical": canonical, "alternates": alternates,
            "image": absolute_url(social_image) if social_image else "", "noindex": noindex,
            "structured_data": structured, "language_switch": language_switch,
            "markdown_url": absolute_url(request.path + "index.md") if settings.LLMS_TXT_ENABLED and name in {"about", "services", "service", "stories", "story", "contact"} else ""}


def public_pages(site):
    photos = list(Photo.objects.prepared())
    stories = list(Story.objects.prepared().prefetch_related("sequence__photo__renditions"))
    services = list(ServicePage.objects.filter(status="published").prefetch_related("photo_sequence__photo__renditions", "story_sequence__story__cover_photo", "questions"))
    offerings = list(ServiceOffering.objects.filter(status="published").select_related("cover_photo").prefetch_related("cover_photo__renditions"))
    publication_changes = [value for model in (Photo, Story, ServicePage, ServiceOffering)
                           if (value := model.objects.aggregate(changed=Max("publication_changed_at"))["changed"])]
    latest = max([site.updated_at, *[photo.updated_at for photo in photos], *[story.updated_at for story in stories],
                  *[service.updated_at for service in services], *[offering.updated_at for offering in offerings], *publication_changes,
                  *Category.objects.filter(active=True, photos__in=Photo.objects.public()).values_list("updated_at", flat=True)], default=None) if site.pk else None
    entries = []
    for language in ("en", "fr"):
        with override(language):
            for name in ("home", "work", "stories", "services", "about", "contact", "privacy"):
                entries.append({"path": reverse(name), "updated": latest if name in {"home", "work", "stories", "services"} else site.updated_at if site.pk else None, "images": []})
            for photo in photos:
                if not photo.title_en or not photo.alt_en or not all(getattr(photo, f"{field}_{language}") for field in ("title", "alt")):
                    continue
                entries.append({"path": reverse("photo", args=[photo.identifier]), "updated": photo.updated_at,
                                "images": [rendition_data(photo)["full"]]})
            for story in stories:
                if not all(getattr(story, f"{field}_{language}") for field in ("title", "introduction")):
                    continue
                sequence = [item for item in story.sequence.all() if item.photo.is_public]
                publication_changes = [item.photo.publication_changed_at for item in story.sequence.all() if item.photo.publication_changed_at]
                changes = [story.updated_at, story.cover_photo.updated_at, *[item.updated_at for item in sequence],
                           *[item.photo.updated_at for item in sequence], *publication_changes]
                entries.append({"path": reverse("story", args=[story.slug]), "updated": max(changes),
                                "images": [rendition_data(story.cover_photo)["full"], *[rendition_data(item.photo)["full"] for item in sequence]]})
            for service in services:
                if not service.available(language):
                    continue
                sequence = [item for item in service.photo_sequence.all() if item.photo.is_public]
                publication_changes = [item.photo.publication_changed_at for item in service.photo_sequence.all() if item.photo.publication_changed_at]
                publication_changes += [item.story.publication_changed_at for item in service.story_sequence.all() if item.story.publication_changed_at]
                publication_changes += [item.story.cover_photo.publication_changed_at for item in service.story_sequence.all()
                                        if item.story.cover_photo and item.story.cover_photo.publication_changed_at]
                changes = [service.updated_at, *[item.updated_at for item in sequence], *[item.photo.updated_at for item in sequence],
                           *[question.updated_at for question in service.questions.all() if question.active],
                           *[item.updated_at for item in service.story_sequence.all() if item.story.status == "published"],
                           *[item.story.updated_at for item in service.story_sequence.all() if item.story.status == "published"], *publication_changes]
                entries.append({"path": service.url(language), "updated": max(changes),
                                "images": [rendition_data(item.photo)["full"] for item in sequence]})
    return entries
