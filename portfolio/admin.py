from django.contrib import admin, messages
from django import forms
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone

from .models import (Category, PartnerCredit, Photo, PhotoRendition, ServiceFAQ, ServiceOffering, ServicePage, ServicePhoto,
                     ServiceSlugRedirect, ServiceStory, SiteSettings, Story, StoryPhoto, StorySlugRedirect)
from .services.images import process_photo


admin.site.site_header = "MrSaintJ Photography"
admin.site.site_title = "MrSaintJ administration"
admin.site.index_title = "Photographs, stories & inquiries"


def thumbnail(photo):
    rendition = photo.renditions.filter(format="jpeg").first()
    if rendition:
        return format_html('<img src="{}" width="100" height="70" style="object-fit:cover" alt="">',
                           reverse("private-preview", args=[rendition.pk]))
    return "Processing needed"


class RenditionInline(admin.TabularInline):
    model = PhotoRendition
    extra = 0
    fields = ("width", "height", "format", "byte_size")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("preview", "title_en", "status", "processing_status", "translations", "content_checks", "featured", "order")
    list_editable = ("featured", "order")
    list_filter = ("status", "processing_status", "categories", "featured")
    search_fields = ("title_en", "title_fr", "flickr_id")
    filter_horizontal = ("categories",)
    readonly_fields = ("preview", "private_original", "identifier", "width", "height", "processing_status", "processing_error")
    inlines = (RenditionInline,)
    actions = ("rebuild", "publish", "unpublish")
    fieldsets = (
        ("Photograph", {"fields": ("preview", "source", "private_original", "identifier", "status", "featured", "order", "categories")}),
        ("English", {"fields": ("title_en", "caption_en", "alt_en")}),
        ("French", {"fields": ("title_fr", "caption_fr", "alt_fr")}),
        ("Behind the frame", {"fields": ("behind_frame_en", "behind_frame_fr"), "description": "Optional first-person shooting notes. Leave empty until you choose to publish them."}),
        ("Framing & source", {"fields": ("focal_x", "focal_y", "credit", "source_url", "flickr_id")}),
        ("Processing", {"fields": ("width", "height", "processing_status", "processing_error")}),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "source":
            kwargs["widget"] = forms.FileInput
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Preview")
    def preview(self, obj):
        return thumbnail(obj) if obj.pk else "Upload a draft photograph first."

    @admin.display(description="Private source")
    def private_original(self, obj):
        if obj.pk and obj.source:
            return format_html('<a href="{}">Download source (staff only)</a>', reverse("private-original", args=[obj.identifier]))
        return "No source"

    @admin.display(description="French")
    def translations(self, obj):
        return "Complete" if obj.title_fr and obj.alt_fr else "Translation needed"

    @admin.display(description="Content checks")
    def content_checks(self, obj):
        warnings = []
        if not obj.alt_en or not obj.alt_fr:
            warnings.append("Missing localized alt text")
        if obj.status == "published" and not obj.is_public:
            warnings.append("Public rendition unavailable")
        return "; ".join(warnings) or "Ready"

    @admin.action(description="Regenerate web renditions")
    def rebuild(self, request, queryset):
        failed = sum(not process_photo(photo) for photo in queryset)
        self.message_user(request, f"Processing complete. {failed} failures.", messages.ERROR if failed else messages.SUCCESS)

    @admin.action(description="Publish ready photographs")
    def publish(self, request, queryset):
        eligible = queryset.filter(processing_status="ready", renditions__format="jpeg").exclude(status="published")
        count = eligible.distinct().count()
        eligible.update(status="published", updated_at=timezone.now(), publication_changed_at=timezone.now())
        self.message_user(request, f"Published {count} ready photographs.")

    @admin.action(description="Unpublish photographs")
    def unpublish(self, request, queryset):
        queryset.exclude(status="draft").update(status="draft", updated_at=timezone.now(), publication_changed_at=timezone.now())


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_fr", "slug", "active", "order")
    list_editable = ("active", "order")
    prepopulated_fields = {"slug": ("name_en",)}
    autocomplete_fields = ("cover_photo",)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    autocomplete_fields = ("hero_photo", "mobile_hero_photo", "services_cover_photo")
    readonly_fields = ("public_origin_check",)
    fieldsets = (
        ("Identity", {"fields": ("brand", "photographer_name", "location")}),
        ("Homepage", {"fields": ("hero_photo", "mobile_hero_photo", "hero_focal_x", "hero_focal_y", "mobile_focal_x", "mobile_focal_y", "hero_heading_en", "hero_heading_fr", "tagline_en", "tagline_fr")}),
        ("About", {"fields": ("biography_en", "biography_fr", "approach_en", "approach_fr", "cv")}),
        ("Services introduction", {"fields": ("services_heading_en", "services_heading_fr", "services_intro_en", "services_intro_fr", "services_cover_photo")}),
        ("Contact", {"fields": ("contact_intro_en", "contact_intro_fr", "public_email")}),
        ("Social profiles", {"fields": ("instagram_url", "linkedin_url", "flickr_url")}),
        ("Discovery", {"fields": ("public_origin_check",)}),
    )

    @admin.display(description="Public origin")
    def public_origin_check(self, obj):
        from django.conf import settings
        from .checks import valid_origin
        return settings.PUBLIC_SITE_URL if valid_origin(settings.PUBLIC_SITE_URL) else "Configure a valid PUBLIC_SITE_URL before launch."

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


class StoryPhotoInline(admin.TabularInline):
    model = StoryPhoto
    extra = 1
    autocomplete_fields = ("photo",)
    fields = ("photo", "order", "caption_en", "caption_fr")


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("title_en", "kind", "status", "translations", "content_checks", "order")
    list_editable = ("order",)
    list_filter = ("kind", "status")
    search_fields = ("title_en", "title_fr", "slug")
    autocomplete_fields = ("cover_photo",)
    prepopulated_fields = {"slug": ("title_en",)}
    inlines = (StoryPhotoInline,)

    @admin.display(description="French")
    def translations(self, obj):
        return "Complete" if obj.title_fr and obj.introduction_fr else "Translation needed"

    @admin.display(description="Content checks")
    def content_checks(self, obj):
        return "Ready" if obj.cover_photo and obj.cover_photo.is_public else "Published cover unavailable"


@admin.register(StorySlugRedirect)
class StorySlugRedirectAdmin(admin.ModelAdmin):
    list_display = ("slug", "story")
    autocomplete_fields = ("story",)


class ServicePhotoInline(admin.TabularInline):
    model = ServicePhoto
    extra = 0
    autocomplete_fields = ("photo",)
    fields = ("photo", "order")


class ServiceStoryInline(admin.TabularInline):
    model = ServiceStory
    extra = 0
    autocomplete_fields = ("story",)
    fields = ("story", "order")


class ServiceFAQInline(admin.StackedInline):
    model = ServiceFAQ
    extra = 0
    fields = ("question_en", "answer_en", "question_fr", "answer_fr", "active", "order")


@admin.register(ServicePage)
class ServicePageAdmin(admin.ModelAdmin):
    list_display = ("title_en", "key", "status", "content_checks", "order")
    list_editable = ("status", "order")
    list_filter = ("status",)
    search_fields = ("title_en", "title_fr", "slug_en", "slug_fr")
    inlines = (ServicePhotoInline, ServiceStoryInline, ServiceFAQInline)
    fieldsets = (
        ("Publication", {"fields": ("key", "status", "order"), "description": "Changing a published slug retains a redirect to the current page."}),
        ("English", {"fields": ("slug_en", "title_en", "introduction_en", "body_en", "coverage_en")}),
        ("French", {"fields": ("slug_fr", "title_fr", "introduction_fr", "body_fr", "coverage_fr")}),
        ("Search metadata", {"fields": ("seo_title_en", "seo_description_en", "seo_title_fr", "seo_description_fr")}),
    )

    @admin.display(description="Content checks")
    def content_checks(self, obj):
        warnings = []
        if not obj.available("fr"):
            warnings.append("French translation incomplete")
        if not all((obj.seo_title_en, obj.seo_description_en, obj.seo_title_fr, obj.seo_description_fr)):
            warnings.append("SEO overrides missing; visible copy is used")
        if not obj.photos.public().exists():
            warnings.append("No ready public photographs")
        return "; ".join(warnings) or "Ready"


@admin.register(ServiceOffering)
class ServiceOfferingAdmin(admin.ModelAdmin):
    list_display = ("title_en", "key", "status", "content_checks", "order")
    list_editable = ("status", "order")
    list_filter = ("status",)
    search_fields = ("title_en", "title_fr", "description_en", "description_fr")
    autocomplete_fields = ("cover_photo", "detail_page")
    fieldsets = (
        ("Offering", {"fields": ("key", "status", "order", "cover_photo", "detail_page"),
                      "description": "Index-only offering, not a new landing page. Leave the image empty for an intentional text-led card."}),
        ("English", {"fields": ("title_en", "description_en", "inquiry_label_en")}),
        ("French", {"fields": ("title_fr", "description_fr", "inquiry_label_fr")}),
    )

    def get_readonly_fields(self, request, obj=None):
        return ("key",) if obj else ()

    @admin.display(description="Content checks")
    def content_checks(self, obj):
        if not all((obj.title_fr, obj.description_fr, obj.inquiry_label_fr)):
            return "French translation incomplete"
        if obj.cover_photo and not obj.cover_photo.is_public:
            return "Cover unavailable; text-only public fallback"
        return "Ready" if obj.cover_photo else "Text-led offering"


@admin.register(ServiceSlugRedirect)
class ServiceSlugRedirectAdmin(admin.ModelAdmin):
    list_display = ("slug", "language", "service")
    list_filter = ("language",)
    autocomplete_fields = ("service",)


@admin.register(PartnerCredit)
class PartnerCreditAdmin(admin.ModelAdmin):
    list_display = ("display_name", "active", "order")
    list_editable = ("active", "order")
    list_filter = ("active",)
