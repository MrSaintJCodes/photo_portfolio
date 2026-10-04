import hashlib
import io
import logging
import warnings

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from portfolio.models import Photo, PhotoRendition


logger = logging.getLogger(__name__)
# Some camera JPEGs carry MPO auxiliary frames; only their primary photo is rendered.
ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}


def validate_source(source):
    try:
        if source.size > settings.PHOTO_MAX_BYTES:
            raise ValidationError(f"Photographs must be smaller than {settings.PHOTO_MAX_BYTES // (1024 * 1024)} MiB.")
        source.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                if image.format not in ALLOWED_FORMATS:
                    raise ValidationError("Upload a JPEG, PNG, or WebP photograph.")
                if image.width * image.height > settings.PHOTO_MAX_PIXELS:
                    raise ValidationError(f"Photographs must be no larger than {settings.PHOTO_MAX_PIXELS // 1_000_000} megapixels.")
                image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError("This photograph could not be decoded safely.") from exc
    finally:
        source.seek(0)


def normalized_image(source):
    source.seek(0)
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original)
        image.load()
        profile = original.info.get("icc_profile")
        if profile:
            try:
                image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                                  ImageCms.createProfile("sRGB"), outputMode="RGB")
            except (ImageCms.PyCMSError, OSError, ValueError):
                logger.warning("Invalid colour profile; using decoded RGB values.")
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        image.info.clear()
        return image


def process_photo(photo):
    previous_files = set(photo.renditions.values_list("file", flat=True))
    previously_ready = photo.processing_status == "ready"
    Photo.objects.filter(pk=photo.pk).update(processing_status="pending", processing_error="")
    new_files = []
    try:
        with photo.source.open("rb") as source:
            validate_source(source)
            digest = hashlib.file_digest(source, "sha256").hexdigest()[:16]
            image = normalized_image(source)
        long_edge = max(image.size)
        edges = sorted({edge for edge in settings.PHOTO_RENDITION_EDGES if edge < long_edge} | {long_edge})
        renditions = []
        storage = storages["default"]
        for edge in edges:
            copy = image.copy()
            copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            for fmt in ("webp", "jpeg"):
                output = io.BytesIO()
                copy.save(output, format=fmt.upper(), quality=95,
                          **({"optimize": True, "progressive": True, "subsampling": 0} if fmt == "jpeg" else {"method": 6}))
                content = output.getvalue()
                scene = slugify(photo.title_en)[:64] or "photograph"
                identifier = photo.flickr_id or str(photo.identifier)
                key = f"photos/{photo.identifier}/{digest}-v3/{scene}-{identifier}-{copy.width}.{fmt}"
                if not storage.exists(key):
                    key = storage.save(key, ContentFile(content))
                    new_files.append(key)
                renditions.append(PhotoRendition(photo=photo, file=key, width=copy.width,
                                                height=copy.height, format=fmt, byte_size=len(content)))
        with transaction.atomic():
            photo.renditions.all().delete()
            PhotoRendition.objects.bulk_create(renditions)
            changes = {"width": image.width, "height": image.height, "processing_status": "ready", "processing_error": ""}
            if previous_files != {rendition.file.name for rendition in renditions}:
                changes["updated_at"] = timezone.now()
            if photo.status == "published" and (not previously_ready or "updated_at" in changes):
                changes["publication_changed_at"] = timezone.now()
            Photo.objects.filter(pk=photo.pk).update(**changes)
        photo.refresh_from_db()
        return True
    except Exception as exc:
        for key in new_files:
            try:
                storages["default"].delete(key)
            except OSError:
                logger.exception("Could not clean an incomplete rendition.")
        changes = {"processing_status": "failed", "processing_error": str(exc)[:2000]}
        if photo.status == "published" and previously_ready:
            changes["publication_changed_at"] = timezone.now()
        Photo.objects.filter(pk=photo.pk).update(**changes)
        photo.refresh_from_db()
        logger.exception("Photo processing failed for %s", photo.identifier)
        return False
