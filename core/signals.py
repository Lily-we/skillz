from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Candidate


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_candidate_for_new_user(sender, instance, created, **kwargs):
    if created:
        Candidate.objects.get_or_create(user=instance)
