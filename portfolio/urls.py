from django.urls import path

from . import discovery, views
from inquiries.views import contact


urlpatterns = [
    path("", views.home, name="home"),
    path("work/", views.work, name="work"),
    path("services/", views.services, name="services"),
    path("services/index.md", discovery.markdown, {"kind": "services"}, name="services-markdown"),
    path("services/<slug:slug>/index.md", discovery.markdown, {"kind": "service"}, name="service-markdown"),
    path("services/<slug:slug>/", views.service_detail, name="service"),
    path("shortlist/", views.shortlist, name="shortlist"),
    path("shortlist/photos/", discovery.shortlist_photos, name="shortlist-photos"),
    path("photos/<uuid:identifier>/", views.photo_detail, name="photo"),
    path("stories/", views.stories, name="stories"),
    path("stories/index.md", discovery.markdown, {"kind": "stories"}, name="stories-markdown"),
    path("stories/<slug:slug>/index.md", discovery.markdown, {"kind": "story"}, name="story-markdown"),
    path("stories/<slug:slug>/", views.story_detail, name="story"),
    path("about/", views.about, name="about"),
    path("about/index.md", discovery.markdown, {"kind": "about"}, name="about-markdown"),
    path("contact/", contact, name="contact"),
    path("contact/index.md", discovery.markdown, {"kind": "contact"}, name="contact-markdown"),
    path("privacy/", views.privacy, name="privacy"),
]
