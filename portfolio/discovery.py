import hashlib
import re
from xml.etree import ElementTree as ET

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _, override
from django.views.decorators.http import require_GET

from .models import Photo, ServiceOffering, ServicePage, Story
from .service_content import audience_copy, booking_copy, planning_steps
from .services.content import get_site
from .services.seo import absolute_url, public_pages
from .services.shortlist import public_selection


def document(request, body, content_type, canonical=""):
    body = body.encode("utf-8") if isinstance(body, str) else body
    etag = '"' + hashlib.sha256(body).hexdigest() + '"'
    response = HttpResponseNotModified() if request.headers.get("If-None-Match") == etag else HttpResponse(body, content_type=content_type)
    response["ETag"] = etag
    response["Cache-Control"] = "no-cache"
    if canonical:
        response["Link"] = f'<{canonical}>; rel="canonical"'
    return response


@require_GET
def sitemap(request):
    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    image_namespace = "http://www.google.com/schemas/sitemap-image/1.1"
    ET.register_namespace("", namespace)
    ET.register_namespace("image", image_namespace)
    root = ET.Element(f"{{{namespace}}}urlset")
    for entry in public_pages(get_site(request)):
        node = ET.SubElement(root, f"{{{namespace}}}url")
        ET.SubElement(node, f"{{{namespace}}}loc").text = absolute_url(entry["path"])
        if entry["updated"]:
            ET.SubElement(node, f"{{{namespace}}}lastmod").text = entry["updated"].isoformat()
        for url in dict.fromkeys(entry["images"]):
            image = ET.SubElement(node, f"{{{image_namespace}}}image")
            ET.SubElement(image, f"{{{image_namespace}}}loc").text = absolute_url(url)
    return document(request, ET.tostring(root, encoding="utf-8", xml_declaration=True), "application/xml; charset=utf-8")


@require_GET
def robots(request):
    rules = "Disallow: /\n" if not settings.INDEXING_ENABLED else "Disallow: /admin/\nDisallow: /private/\nDisallow: /en/shortlist/\nDisallow: /fr/shortlist/\n"
    return HttpResponse(f"User-agent: *\n{rules}Sitemap: {absolute_url('/sitemap.xml')}\n", content_type="text/plain; charset=utf-8")


def md_text(value):
    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", value)


def md_link(title, path):
    return f"[{md_text(title)}]({absolute_url(path)})"


@require_GET
def markdown(request, kind, slug=None):
    if not settings.LLMS_TXT_ENABLED:
        raise Http404()
    site = get_site(request)
    language = request.LANGUAGE_CODE.split("-")[0]
    sections = []
    if kind == "about":
        title = _("About Justin St-Laurent")
        sections = [md_text(site.biography), md_text(site.approach)]
        sections.append("\n".join(f"- [{name}]({url})" for name, url in (("Instagram", site.instagram_url), ("LinkedIn", site.linkedin_url), ("Flickr", site.flickr_url)) if url))
    elif kind == "contact":
        title = _("Contact")
        sections = [md_text(site.contact_intro), md_text(site.location), md_text(site.public_email), md_link(_("Contact"), reverse("contact"))]
    elif kind == "services":
        title = site.services_heading
        sections = [md_text(site.services_intro), md_link(_("Tell me about your shoot"), reverse("contact")),
                    md_link(_("Explore my sports portfolio"), reverse("work"))]
        for offering in ServiceOffering.objects.public(language).select_related("detail_page"):
            sections.append(f"## {md_text(offering.title)}\n\n{md_text(offering.description)}\n\n"
                            + md_link(offering.inquiry_label, offering.inquiry_url))
            if offering.detail_url:
                sections.append(md_link(offering.detail_page.title, offering.detail_url))
        sections.extend([f"## {_('Who I work with')}\n\n{md_text(audience_copy())}",
                         f"## {_('Planning your shoot')}\n\n" + "\n".join(f"{index}. {md_text(step)}" for index, step in enumerate(planning_steps(), 1)),
                         f"## {_('What are you planning?')}\n\n{md_text(booking_copy())}",
                         md_link(_("Request a quote"), reverse("contact"))])
    elif kind == "service":
        service = get_object_or_404(ServicePage.objects.public(language), **{f"slug_{language}": slug})
        title = service.title
        sections = [md_text(service.introduction), md_text(service.body), "\n".join(f"- {md_text(topic)}" for topic in service.coverage)]
        sections.extend(f"## {md_text(question.question)}\n\n{md_text(question.answer)}" for question in service.questions.filter(active=True))
        sections.extend(md_link(photo.title, reverse("photo", args=[photo.identifier])) for photo in service.photos.public())
        sections.append(md_link(_("Contact"), reverse("contact")))
    elif kind == "stories":
        title = _("Stories & collections")
        sections = ["\n\n".join(f"- {md_link(story.title, reverse('story', args=[story.slug]))}: {md_text(story.introduction)}" for story in Story.objects.public())]
    elif kind == "story":
        story = get_object_or_404(Story.objects.public(), slug=slug)
        title = story.title
        sections = [md_text(story.introduction), md_text(story.body), md_text(story.behind_frame)]
        sections.extend(md_link(item.photo.title, reverse("photo", args=[item.photo.identifier])) for item in story.sequence.filter(photo__in=Photo.objects.public()).select_related("photo"))
    else:
        raise Http404()
    canonical = absolute_url(request.path.removesuffix("index.md"))
    body = f"# {md_text(title)}\n\n" + "\n\n".join(section for section in sections if section) + "\n"
    response = document(request, body, "text/markdown; charset=utf-8", canonical)
    response["X-Robots-Tag"] = "noindex, follow"
    return response


@require_GET
def llms(request):
    if not settings.LLMS_TXT_ENABLED:
        raise Http404()
    site = get_site(request)
    body = [f"# {md_text(site.brand)}", f"> {md_text(site.biography_en)}"]
    for language, heading in (("en", "English"), ("fr", "Fran\u00e7ais")):
        with override(language):
            body.append(f"## {heading}")
            for name, label in (("about", _("About Justin St-Laurent")), ("services", _("Photography services")), ("stories", _("Stories & collections")), ("contact", _("Contact"))):
                body.append(f"- {md_link(label, reverse(name) + 'index.md')}")
            body.extend(f"- {md_link(service.title, service.url(language) + 'index.md')}" for service in ServicePage.objects.public(language)[:3])
    response = document(request, "\n\n".join(body) + "\n", "text/plain; charset=utf-8")
    response["X-Robots-Tag"] = "noindex, follow"
    return response


@require_GET
def shortlist_photos(request):
    raw = request.GET.get("ids", "")
    try:
        photos = public_selection(raw.split(",") if raw else [])
    except ValueError:
        response = JsonResponse({"error": _("Please review your saved photographs.")}, status=400)
    else:
        items = []
        for photo in photos:
            thumbnail = next(r for r in photo.renditions.all() if r.format == "jpeg")
            items.append({"id": str(photo.identifier), "title": photo.title, "alt": photo.alt,
                          "href": reverse("photo", args=[photo.identifier]), "src": thumbnail.file.url,
                          "width": thumbnail.width, "height": thumbnail.height})
        response = JsonResponse({"photos": items})
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@require_GET
def indexnow_key(request, key):
    if not settings.INDEXNOW_ENABLED or key != settings.INDEXNOW_KEY:
        raise Http404()
    return HttpResponse(key, content_type="text/plain; charset=utf-8")
