import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import get_language
from django.utils import timezone

from .storage import original_storage
from .service_content import ServiceKind, SERVICES_HEADING_EN, SERVICES_HEADING_FR, SERVICES_INTRO_EN, SERVICES_INTRO_FR


def localized(obj, field, language=None):
    language = (language or get_language() or "en").split("-")[0]
    return getattr(obj, f"{field}_{language}", "") or getattr(obj, f"{field}_en", "")


def source_path(instance, filename):
    return f"sources/{instance.identifier}/{uuid.uuid4().hex}/{filename}"


class Category(models.Model):
    slug = models.SlugField(unique=True)
    name_en = models.CharField(max_length=80)
    name_fr = models.CharField(max_length=80, blank=True)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    cover_photo = models.ForeignKey("Photo", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="category_covers")

    class Meta:
        ordering = ["order", "pk"]
        verbose_name_plural = "categories"

    @property
    def name(self):
        return localized(self, "name")

    def __str__(self):
        return self.name_en


class PhotoQuerySet(models.QuerySet):
    def public(self):
        return self.filter(status="published", processing_status="ready", renditions__format="jpeg").distinct()

    def prepared(self):
        return self.public().prefetch_related("renditions", "categories")


class Photo(models.Model):
    identifier = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source = models.FileField(upload_to=source_path, storage=original_storage)
    source_url = models.URLField(blank=True)
    flickr_id = models.CharField(max_length=30, unique=True, null=True, blank=True)
    title_en = models.CharField(max_length=160)
    title_fr = models.CharField(max_length=160, blank=True)
    caption_en = models.TextField(blank=True)
    caption_fr = models.TextField(blank=True)
    behind_frame_en = models.TextField(blank=True)
    behind_frame_fr = models.TextField(blank=True)
    alt_en = models.CharField(max_length=300)
    alt_fr = models.CharField(max_length=300, blank=True)
    categories = models.ManyToManyField(Category, blank=True, related_name="photos")
    order = models.PositiveIntegerField(default=0)
    featured = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=[("draft", "Draft"), ("published", "Published")], default="draft")
    focal_x = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    focal_y = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    width = models.PositiveIntegerField(default=0, editable=False)
    height = models.PositiveIntegerField(default=0, editable=False)
    credit = models.CharField(max_length=120, default="MrSaintJ Photography")
    processing_status = models.CharField(max_length=12, default="pending", editable=False,
                                         choices=[("pending", "Pending"), ("ready", "Ready"), ("failed", "Failed")])
    processing_error = models.TextField(blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    publication_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    objects = PhotoQuerySet.as_manager()

    class Meta:
        ordering = ["order", "pk"]

    @property
    def title(self):
        return localized(self, "title")

    @property
    def caption(self):
        return localized(self, "caption")

    @property
    def alt(self):
        return localized(self, "alt")

    @property
    def behind_frame(self):
        return localized(self, "behind_frame")

    @property
    def is_public(self):
        return self.status == "published" and self.processing_status == "ready" and any(
            rendition.format == "jpeg" for rendition in self.renditions.all())

    def clean(self):
        if self.source and not self.source._committed:
            from .services.images import validate_source
            validate_source(self.source)
        if self.status == "published" and (not self.pk or self.processing_status != "ready"
                                           or not any(r.format == "jpeg" for r in self.renditions.all())):
            raise ValidationError({"status": "Upload and process a draft before publishing it."})

    def save(self, *args, **kwargs):
        previous = type(self).objects.filter(pk=self.pk).only("status", "processing_status").first() if self.pk else None
        changed = bool(self.source) and not self.source._committed
        if changed:
            self.processing_status = "pending"
            if previous and previous.status == "published" and previous.processing_status == "ready":
                self.publication_changed_at = timezone.now()
        fields = kwargs.get("update_fields")
        if (fields is None or "status" in fields) and previous and previous.status != self.status:
            self.publication_changed_at = timezone.now()
            if fields is not None:
                kwargs["update_fields"] = set(fields) | {"publication_changed_at", "updated_at"}
        elif not previous and self.status == "published":
            self.publication_changed_at = timezone.now()
        super().save(*args, **kwargs)
        if changed:
            from .services.images import process_photo
            process_photo(self)

    def __str__(self):
        return self.title_en


class PhotoRendition(models.Model):
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name="renditions")
    file = models.FileField(upload_to="photos/")
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    format = models.CharField(max_length=8, choices=[("webp", "WebP"), ("jpeg", "JPEG")])
    byte_size = models.PositiveIntegerField()

    class Meta:
        ordering = ["width"]
        constraints = [models.UniqueConstraint(fields=["photo", "width", "format"], name="unique_photo_rendition")]


class SiteSettings(models.Model):
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False,
                                                 validators=[MinValueValidator(1), MaxValueValidator(1)])
    brand = models.CharField(max_length=100, default="MrSaintJ Photography")
    photographer_name = models.CharField(max_length=100, default="Justin St-Laurent")
    location = models.CharField(max_length=120, default="Montr\u00e9al \u00b7 Qu\u00e9bec")
    hero_heading_en = models.CharField(max_length=100, default="Effort.\nIn focus.", help_text="Separate the two lines with a newline.")
    hero_heading_fr = models.CharField(max_length=100, default="L'effort.\nEn image.")
    tagline_en = models.CharField(max_length=160, default="The action. The people. The whole event.")
    tagline_fr = models.CharField(max_length=160, default="L'action. Les gens. L'\u00e9v\u00e9nement.")
    biography_en = models.TextField(blank=True)
    biography_fr = models.TextField(blank=True)
    approach_en = models.TextField(blank=True)
    approach_fr = models.TextField(blank=True)
    contact_intro_en = models.TextField(blank=True)
    contact_intro_fr = models.TextField(blank=True)
    services_heading_en = models.CharField(max_length=200, default=SERVICES_HEADING_EN)
    services_heading_fr = models.CharField(max_length=200, default=SERVICES_HEADING_FR, blank=True)
    services_intro_en = models.TextField(default=SERVICES_INTRO_EN)
    services_intro_fr = models.TextField(default=SERVICES_INTRO_FR, blank=True)
    services_cover_photo = models.ForeignKey(Photo, null=True, blank=True, on_delete=models.SET_NULL,
                                            related_name="services_index_covers")
    flickr_url = models.URLField(default="https://www.flickr.com/photos/194206904@N02/albums/72177720309211783/")
    instagram_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    public_email = models.EmailField(blank=True)
    cv = models.FileField(upload_to="cv/", blank=True)
    hero_photo = models.ForeignKey(Photo, null=True, blank=True, on_delete=models.SET_NULL, related_name="desktop_heroes")
    mobile_hero_photo = models.ForeignKey(Photo, null=True, blank=True, on_delete=models.SET_NULL, related_name="mobile_heroes")
    hero_focal_x = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    hero_focal_y = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    mobile_focal_x = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    mobile_focal_y = models.PositiveSmallIntegerField(default=38, validators=[MaxValueValidator(100)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "site settings"

    def clean(self):
        for field in ("hero_photo", "mobile_hero_photo", "services_cover_photo"):
            photo = getattr(self, field)
            if photo and not photo.is_public:
                raise ValidationError({field: "Choose a published photograph with ready renditions."})
        if self.cv and not self.cv._committed:
            self.cv.seek(0)
            if self.cv.size > 10 * 1024 * 1024 or self.cv.read(5) != b"%PDF-":
                raise ValidationError({"cv": "Upload a PDF no larger than 10 MiB."})
            self.cv.seek(0)

    def save(self, *args, **kwargs):
        self.singleton = 1
        super().save(*args, **kwargs)

    @property
    def hero_heading(self):
        return localized(self, "hero_heading")

    @property
    def photographer_lines(self):
        return self.photographer_name.split(" ", 1)

    @property
    def tagline(self):
        return localized(self, "tagline")

    @property
    def biography(self):
        return localized(self, "biography")

    @property
    def approach(self):
        return localized(self, "approach")

    @property
    def contact_intro(self):
        return localized(self, "contact_intro")

    @property
    def services_heading(self):
        return localized(self, "services_heading")

    @property
    def services_intro(self):
        return localized(self, "services_intro")

    def __str__(self):
        return self.brand


class StoryQuerySet(models.QuerySet):
    def public(self):
        return self.filter(status="published", cover_photo__in=Photo.objects.public())

    def prepared(self):
        return self.public().select_related("cover_photo").prefetch_related("cover_photo__renditions")


class Story(models.Model):
    slug = models.SlugField(unique=True)
    title_en = models.CharField(max_length=160)
    title_fr = models.CharField(max_length=160, blank=True)
    introduction_en = models.TextField()
    introduction_fr = models.TextField(blank=True)
    body_en = models.TextField(blank=True)
    body_fr = models.TextField(blank=True)
    kind = models.CharField(max_length=12, choices=[("collection", "Collection"), ("event", "Event story")], default="collection")
    cover_photo = models.ForeignKey(Photo, null=True, on_delete=models.SET_NULL, related_name="covered_stories")
    event_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=160, blank=True)
    assignment_en = models.TextField(blank=True)
    assignment_fr = models.TextField(blank=True)
    behind_frame_en = models.TextField(blank=True)
    behind_frame_fr = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    publication_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=[("draft", "Draft"), ("published", "Published")], default="draft")
    photos = models.ManyToManyField(Photo, through="StoryPhoto", related_name="stories")
    objects = StoryQuerySet.as_manager()

    class Meta:
        ordering = ["order", "pk"]
        verbose_name_plural = "stories"

    def clean(self):
        if self.status == "published" and (not self.cover_photo or not self.cover_photo.is_public):
            raise ValidationError({"cover_photo": "A published story needs a published, ready cover photograph."})

    def save(self, *args, **kwargs):
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        fields = kwargs.get("update_fields")
        if (fields is None or "status" in fields) and previous and previous.status != self.status:
            self.publication_changed_at = timezone.now()
            if fields is not None:
                kwargs["update_fields"] = set(fields) | {"publication_changed_at", "updated_at"}
        elif not previous and self.status == "published":
            self.publication_changed_at = timezone.now()
        super().save(*args, **kwargs)
        StorySlugRedirect.objects.filter(slug=self.slug).delete()
        if previous and previous.status == "published" and previous.slug != self.slug:
            StorySlugRedirect.objects.update_or_create(slug=previous.slug, defaults={"story": self})

    @property
    def title(self):
        return localized(self, "title")

    @property
    def introduction(self):
        return localized(self, "introduction")

    @property
    def body(self):
        return localized(self, "body")

    @property
    def assignment(self):
        return localized(self, "assignment")

    @property
    def behind_frame(self):
        return localized(self, "behind_frame")

    def __str__(self):
        return self.title_en


class StorySlugRedirect(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE)
    slug = models.SlugField(unique=True)


class StoryPhoto(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="sequence")
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    caption_en = models.TextField(blank=True)
    caption_fr = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["story", "photo"], name="unique_story_photo")]

    @property
    def caption(self):
        return localized(self, "caption") or self.photo.caption


class ServicePageQuerySet(models.QuerySet):
    def public(self, language=None):
        language = (language or get_language() or "en").split("-")[0]
        return self.filter(status="published").exclude(**{f"slug_{language}": ""}).exclude(
            **{f"title_{language}": ""}).exclude(**{f"introduction_{language}": ""})


class ServicePage(models.Model):
    key = models.SlugField(unique=True)
    slug_en = models.SlugField(unique=True)
    slug_fr = models.SlugField(blank=True)
    title_en = models.CharField(max_length=160)
    title_fr = models.CharField(max_length=160, blank=True)
    introduction_en = models.TextField()
    introduction_fr = models.TextField(blank=True)
    body_en = models.TextField(blank=True)
    body_fr = models.TextField(blank=True)
    coverage_en = models.TextField(blank=True, help_text="One coverage topic per line.")
    coverage_fr = models.TextField(blank=True)
    seo_title_en = models.CharField(max_length=160, blank=True)
    seo_title_fr = models.CharField(max_length=160, blank=True)
    seo_description_en = models.CharField(max_length=300, blank=True)
    seo_description_fr = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=[("draft", "Draft"), ("published", "Published")], default="draft")
    updated_at = models.DateTimeField(auto_now=True)
    publication_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    photos = models.ManyToManyField(Photo, through="ServicePhoto", related_name="services")
    stories = models.ManyToManyField(Story, through="ServiceStory", related_name="services")
    objects = ServicePageQuerySet.as_manager()

    class Meta:
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["slug_fr"], condition=~models.Q(slug_fr=""), name="unique_french_service_slug")]

    def available(self, language):
        return self.status == "published" and all(getattr(self, f"{field}_{language}") for field in ("slug", "title", "introduction"))

    def url(self, language=None):
        from django.urls import reverse
        from django.utils.translation import override
        language = (language or get_language() or "en").split("-")[0]
        with override(language):
            return reverse("service", args=[getattr(self, f"slug_{language}")])

    def save(self, *args, **kwargs):
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        fields = kwargs.get("update_fields")
        if (fields is None or "status" in fields) and previous and previous.status != self.status:
            self.publication_changed_at = timezone.now()
            if fields is not None:
                kwargs["update_fields"] = set(fields) | {"publication_changed_at", "updated_at"}
        elif not previous and self.status == "published":
            self.publication_changed_at = timezone.now()
        super().save(*args, **kwargs)
        for language in ("en", "fr"):
            slug = getattr(self, f"slug_{language}")
            ServiceSlugRedirect.objects.filter(language=language, slug=slug).delete()
            if previous and previous.available(language) and getattr(previous, f"slug_{language}") != slug:
                ServiceSlugRedirect.objects.update_or_create(language=language, slug=getattr(previous, f"slug_{language}"),
                                                            defaults={"service": self})

    @property
    def title(self):
        return localized(self, "title")

    @property
    def introduction(self):
        return localized(self, "introduction")

    @property
    def body(self):
        return localized(self, "body")

    @property
    def coverage(self):
        return [line.strip() for line in localized(self, "coverage").splitlines() if line.strip()]

    def __str__(self):
        return self.title_en


class ServiceOfferingQuerySet(models.QuerySet):
    def public(self, language=None):
        language = (language or get_language() or "en").split("-")[0]
        return self.filter(status="published").exclude(**{f"title_{language}": ""}).exclude(
            **{f"description_{language}": ""}).exclude(**{f"inquiry_label_{language}": ""})


class ServiceOffering(models.Model):
    key = models.CharField(max_length=40, choices=ServiceKind.choices, unique=True)
    title_en = models.CharField(max_length=160)
    title_fr = models.CharField(max_length=160, blank=True)
    description_en = models.TextField()
    description_fr = models.TextField(blank=True)
    inquiry_label_en = models.CharField(max_length=120)
    inquiry_label_fr = models.CharField(max_length=120, blank=True)
    cover_photo = models.ForeignKey(Photo, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="offering_covers")
    detail_page = models.ForeignKey(ServicePage, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="offerings")
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=[("draft", "Draft"), ("published", "Published")], default="draft")
    updated_at = models.DateTimeField(auto_now=True)
    publication_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    objects = ServiceOfferingQuerySet.as_manager()

    class Meta:
        ordering = ["order", "pk"]

    @property
    def title(self):
        return localized(self, "title")

    @property
    def description(self):
        return localized(self, "description")

    @property
    def inquiry_label(self):
        return localized(self, "inquiry_label")

    @property
    def inquiry_url(self):
        from urllib.parse import urlencode
        from django.urls import reverse
        return reverse("contact") + "?" + urlencode({"service": self.key})

    @property
    def detail_url(self):
        language = (get_language() or "en").split("-")[0]
        return self.detail_page.url(language) if self.detail_page and self.detail_page.available(language) else ""

    def clean(self):
        if self.cover_photo and not self.cover_photo.is_public:
            raise ValidationError({"cover_photo": "Choose a published photograph with ready renditions."})

    def save(self, *args, **kwargs):
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        fields = kwargs.get("update_fields")
        if (fields is None or "status" in fields) and ((previous and previous.status != self.status) or (not previous and self.status == "published")):
            self.publication_changed_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"publication_changed_at", "updated_at"}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title_en


class ServicePhoto(models.Model):
    service = models.ForeignKey(ServicePage, on_delete=models.CASCADE, related_name="photo_sequence")
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["service", "photo"], name="unique_service_photo")]


class ServiceStory(models.Model):
    service = models.ForeignKey(ServicePage, on_delete=models.CASCADE, related_name="story_sequence")
    story = models.ForeignKey(Story, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["service", "story"], name="unique_service_story")]


class ServiceFAQ(models.Model):
    service = models.ForeignKey(ServicePage, on_delete=models.CASCADE, related_name="questions")
    question_en = models.CharField(max_length=200)
    question_fr = models.CharField(max_length=200, blank=True)
    answer_en = models.TextField()
    answer_fr = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "pk"]

    @property
    def question(self):
        return localized(self, "question")

    @property
    def answer(self):
        return localized(self, "answer")


class ServiceSlugRedirect(models.Model):
    service = models.ForeignKey(ServicePage, on_delete=models.CASCADE)
    language = models.CharField(max_length=2, choices=settings.LANGUAGES)
    slug = models.SlugField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["language", "slug"], name="unique_service_redirect")]


class PartnerCredit(models.Model):
    display_name = models.CharField(max_length=100, unique=True)
    url = models.URLField(blank=True)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=False, help_text="Company credits are hidden unless explicitly enabled.")

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.display_name
