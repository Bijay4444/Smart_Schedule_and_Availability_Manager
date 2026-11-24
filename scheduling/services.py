"""Commitment writes and overlap checks shared by the browser and future APIs."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .conflicts import find_conflicts, inspect_conflicts, mark_recurring_conflicts
from .locking import lock_schedule_owner
from .models import Commitment, CommitmentSource


class ConflictingCommitments(Exception):
    def __init__(self, conflicts, issues=()):
        self.conflicts = conflicts
        self.issues = issues
        super().__init__("Review the scheduling warnings before saving this commitment.")


def commitments_for_user(*, owner):
    conflicts = find_conflicts(
        owner=owner,
        starts_at=OuterRef("starts_at"),
        ends_at=OuterRef("ends_at"),
        exclude_pk=OuterRef("pk"),
    )
    commitments = (
        Commitment.objects.filter(source__owner=owner)
        .select_related("source")
        .annotate(has_conflict=Exists(conflicts))
    )
    return mark_recurring_conflicts(owner=owner, commitments=commitments)


@transaction.atomic
def save_commitment(*, commitment, owner, confirm_conflicts=False):
    lock_schedule_owner(owner)
    # The source lock serializes assignment with source archival.
    source = CommitmentSource.objects.select_for_update().filter(
        pk=commitment.source_id, owner=owner
    ).first()
    if source is None:
        raise PermissionDenied
    previous = None
    if commitment.pk:
        previous = Commitment.objects.select_for_update(of=("self",)).filter(
            pk=commitment.pk, source__owner=owner
        ).first()
        if previous is None:
            raise PermissionDenied
    if source.archived_at and (previous is None or previous.source_id != source.pk):
        raise ValidationError({"source": "Choose an active source for a new assignment."})

    commitment.full_clean()
    check = inspect_conflicts(
        owner=owner,
        starts_at=commitment.starts_at,
        ends_at=commitment.ends_at,
        exclude_pk=commitment.pk,
    )
    if (check.conflicts or check.issues) and not confirm_conflicts:
        raise ConflictingCommitments(list(check.conflicts), check.issues)

    commitment.save()
    return commitment


@transaction.atomic
def archive_source(*, source_id, owner):
    """Retire a source without deleting or cancelling any occupied time."""
    source = CommitmentSource.objects.select_for_update().filter(
        pk=source_id, owner=owner
    ).first()
    if source is None:
        raise PermissionDenied
    if source.archived_at is None:
        source.archived_at = timezone.now()
        source.save(update_fields=["archived_at"])
    return source
