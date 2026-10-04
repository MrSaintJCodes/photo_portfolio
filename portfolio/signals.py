from django.db.models.signals import m2m_changed, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import (Category, Photo, ServiceFAQ, ServiceOffering, ServicePage, ServicePhoto, ServiceStory,
                     SiteSettings, Story, StoryPhoto)


@receiver(pre_delete, sender=Photo)
@receiver(pre_delete, sender=Story)
@receiver(pre_delete, sender=ServicePage)
@receiver(pre_delete, sender=ServiceOffering)
def removed_public_content(sender, instance, using, **kwargs):
    public = instance.is_public if sender is Photo else (
        instance.status == "published" and (sender in (ServicePage, ServiceOffering) or instance.cover_photo and instance.cover_photo.is_public))
    now = timezone.now()
    if public:
        SiteSettings.objects.using(using).update(updated_at=now)
        if sender is Photo:
            Story.objects.using(using).filter(photos=instance).update(updated_at=now)
            ServicePage.objects.using(using).filter(photos=instance).update(updated_at=now)
        elif sender is Story:
            ServicePage.objects.using(using).filter(stories=instance).update(updated_at=now)
    elif instance.publication_changed_at:
        # Retain the last removal time when a previously public draft is deleted.
        SiteSettings.objects.using(using).filter(updated_at__lt=instance.publication_changed_at).update(
            updated_at=instance.publication_changed_at)


@receiver(pre_delete, sender=ServicePhoto)
@receiver(pre_delete, sender=StoryPhoto)
@receiver(pre_delete, sender=ServiceStory)
@receiver(pre_delete, sender=ServiceFAQ)
def removed_public_relation(sender, instance, using, **kwargs):
    if sender in (ServicePhoto, StoryPhoto):
        public = instance.photo.is_public
    elif sender is ServiceStory:
        public = instance.story.status == "published" and instance.story.cover_photo and instance.story.cover_photo.is_public
    else:
        public = instance.active
    if public:
        model, identifier = (Story, instance.story_id) if sender is StoryPhoto else (ServicePage, instance.service_id)
        model.objects.using(using).filter(pk=identifier).update(updated_at=timezone.now())


@receiver(m2m_changed, sender=Photo.categories.through)
def changed_public_categories(sender, instance, action, reverse, using, **kwargs):
    if action in {"pre_remove", "pre_clear", "post_add"}:
        identifiers = kwargs.get("pk_set")
        if action != "pre_clear" and not identifiers:
            return
        if reverse:
            photos = instance.photos.public()
            if identifiers is not None:
                photos = photos.filter(pk__in=identifiers)
            public = instance.active and photos.exists()
        else:
            categories = instance.categories.filter(active=True) if action == "pre_clear" else Category.objects.filter(pk__in=identifiers, active=True)
            public = instance.is_public and categories.exists()
        if public:
            SiteSettings.objects.using(using).update(updated_at=timezone.now())
