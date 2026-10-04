import hashlib
import io
import json
import logging
import warnings
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
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
        ImageOps.exif_transpose(original, in_place=True)
        image = original
        profile = original.info.get("icc_profile")
        if profile:
            try:
                image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                                  ImageCms.createProfile("sRGB"), outputMode="RGB")
            except (ImageCms.PyCMSError, OSError, ValueError):
                logger.warning("Invalid colour profile; using decoded RGB values.")
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image if image.mode == "RGBA" else image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            if rgba is not original:
                rgba.close()
            if image is not original:
                image.close()
            image = background
        else:
            # A colour-profile conversion already returns an independent RGB image.
            if image is original or image.mode != "RGB":
                image = image.convert("RGB")
        image.info.clear()
        return image


def rendition_key(photo, digest, width, fmt):
    scene = slugify(photo.title_en)[:64] or "photograph"
    identifier = photo.flickr_id or str(photo.identifier)
    return f"photos/{photo.identifier}/{digest[:16]}-v3/{scene}-{identifier}-{width}.{fmt}"


def prepared_renditions(photo, digest, directory, storage, new_files):
    root = Path(directory) / str(photo.flickr_id)
    bundle = json.loads((root / "manifest.json").read_text())
    if bundle["source_sha256"] != digest:
        # Owner-uploaded replacements must be rendered from their own original.
        return None
    renditions = []
    for entry in bundle["renditions"]:
        path = root / entry["file"]
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Invalid prepared rendition path.")
        if path.stat().st_size != entry["byte_size"]:
            raise ValueError("Incomplete prepared rendition.")
        key = rendition_key(photo, digest, entry["width"], entry["format"])
        if storage.exists(key) and storage.size(key) != entry["byte_size"]:
            storage.delete(key)
        if not storage.exists(key):
            with path.open("rb") as file:
                key = storage.save(key, File(file))
            new_files.append(key)
        renditions.append(PhotoRendition(photo=photo, file=key, width=entry["width"],
                                        height=entry["height"], format=entry["format"],
                                        byte_size=entry["byte_size"]))
    if not renditions or {rendition.format for rendition in renditions} != {"jpeg", "webp"}:
        raise ValueError("Prepared photographs require JPEG and WebP renditions.")
    return renditions, (bundle["width"], bundle["height"])


def process_photo(photo, *, rendition_dir=None):
    previous_files = set(photo.renditions.values_list("file", flat=True))
    previously_ready = photo.processing_status == "ready"
    Photo.objects.filter(pk=photo.pk).update(processing_status="pending", processing_error="")
    new_files = []
    image = None
    try:
        storage = storages["default"]
        with photo.source.open("rb") as source:
            validate_source(source)
            digest = hashlib.file_digest(source, "sha256").hexdigest()
            prepared = prepared_renditions(photo, digest, rendition_dir, storage, new_files) if rendition_dir else None
            if prepared is None:
                image = normalized_image(source)
        if prepared is not None:
            renditions, dimensions = prepared
        else:
            dimensions = image.size
            long_edge = max(dimensions)
            edges = sorted({edge for edge in settings.PHOTO_RENDITION_EDGES if edge < long_edge} | {long_edge})
            renditions = []
            for edge in edges:
                copy = image if edge == long_edge else image.copy()
                try:
                    if copy is not image:
                        copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                    for fmt in ("webp", "jpeg"):
                        with io.BytesIO() as output:
                            copy.save(output, format=fmt.upper(), quality=95,
                                      **({"optimize": True, "progressive": True, "subsampling": 0} if fmt == "jpeg" else {"method": 6}))
                            content = output.getvalue()
                        key = rendition_key(photo, digest, copy.width, fmt)
                        if not storage.exists(key):
                            key = storage.save(key, ContentFile(content))
                            new_files.append(key)
                        renditions.append(PhotoRendition(photo=photo, file=key, width=copy.width,
                                                        height=copy.height, format=fmt, byte_size=len(content)))
                finally:
                    if copy is not image:
                        copy.close()
        with transaction.atomic():
            photo.renditions.all().delete()
            PhotoRendition.objects.bulk_create(renditions)
            changes = {"width": dimensions[0], "height": dimensions[1], "processing_status": "ready", "processing_error": ""}
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
    finally:
        if image is not None:
            image.close()
