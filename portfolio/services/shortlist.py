import uuid

from portfolio.models import Photo


MAX_SHORTLIST = 12


def public_selection(values):
    if not isinstance(values, list) or len(values) > MAX_SHORTLIST:
        raise ValueError("A shortlist must contain at most 12 photo identifiers.")
    try:
        identifiers = list(dict.fromkeys(uuid.UUID(value) for value in values if isinstance(value, str)))
        if any(not isinstance(value, str) for value in values):
            raise ValueError()
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid photo identifier.") from exc
    photos = {photo.identifier: photo for photo in Photo.objects.prepared().filter(identifier__in=identifiers)}
    return [photos[identifier] for identifier in identifiers if identifier in photos]
