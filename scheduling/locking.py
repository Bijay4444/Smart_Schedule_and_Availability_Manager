"""Stable lock shared by cooperating schedule writers."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied


def lock_schedule_owner(owner):
    """Call inside an atomic transaction, before locking sources or series.

    The user exists even before the first schedule row. Serializing writes for
    one owner prevents simultaneous saves from both checking an empty schedule.
    """
    if owner.pk is None or not get_user_model().objects.select_for_update().filter(pk=owner.pk).exists():
        raise PermissionDenied
