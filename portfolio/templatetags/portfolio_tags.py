from django import template
from portfolio.services.content import rendition_data

register = template.Library()


@register.inclusion_tag("components/picture.html")
def photo_picture(photo, sizes="(min-width: 900px) 33vw, (min-width: 600px) 50vw, 100vw", eager=False):
    return {"image": rendition_data(photo), "sizes": sizes, "eager": eager}


@register.inclusion_tag("components/picture.html")
def hero_picture(photo):
    aspect = photo.width / photo.height if photo.height else 1
    sizes = f"(max-width: 360px) {max(360, round(340 * aspect * 1.09))}px, (max-width: 600px) {max(600, round(380 * aspect * 1.09))}px, 109vw"
    return {"image": rendition_data(photo), "sizes": sizes, "eager": True}
