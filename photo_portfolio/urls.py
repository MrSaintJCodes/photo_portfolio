"""Root URL configuration."""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path
from django.views.generic import RedirectView

from portfolio import discovery, views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/en/", permanent=False)),
    path("about/", RedirectView.as_view(url="/en/about/", permanent=False)),
    path("contact/", RedirectView.as_view(url="/en/contact/", permanent=False)),
    path("healthz/", views.health, name="health"),
    path("private/originals/<uuid:identifier>/", views.private_original, name="private-original"),
    path("private/renditions/<int:rendition_id>/", views.private_preview, name="private-preview"),
    path("sitemap.xml", discovery.sitemap, name="sitemap"),
    path("robots.txt", discovery.robots, name="robots"),
    path("llms.txt", discovery.llms, name="llms"),
    path("indexnow/<str:key>.txt", discovery.indexnow_key, name="indexnow-key"),
]
urlpatterns += i18n_patterns(path("", include("portfolio.urls")))
if not settings.USE_S3:
    urlpatterns += [path("media/<path:key>", views.public_media, name="public-media")]
