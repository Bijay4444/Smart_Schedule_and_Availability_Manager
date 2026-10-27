"""Commitment writes and overlap checks shared by the browser and future APIs."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .models import Commitment, CommitmentSource


class ConflictingCommitments(Exception):
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__("This commitment overlaps your existing commitments.")


def find_conflicts(*, owner, starts_at, ends_at, exclude_pk=None):
    """Strict inequalities allow one commitment to start as another ends."""
    conflicts = Commitment.objects.filter(
        source__owner=owner, starts_at__lt=ends_at, ends_at__gt=starts_at
    ).select_related("source")
    if exclude_pk is not None:
        conflicts = conflicts.exclude(pk=exclude_pk)
    return conflicts


def commitments_for_user(*, owner):
    conflicts = find_conflicts(
        owner=owner,
        starts_at=OuterRef("starts_at"),
        ends_at=OuterRef("ends_at"),
        exclude_pk=OuterRef("pk"),
    )
    return (
        Commitment.objects.filter(source__owner=owner)
        .select_related("source")
        .annotate(has_conflict=Exists(conflicts))
    )


@transaction.atomic
def save_commitment(*, commitment, owner, confirm_conflicts=False):
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
    conflicts = list(
        find_conflicts(
            owner=owner,
            starts_at=commitment.starts_at,
            ends_at=commitment.ends_at,
            exclude_pk=commitment.pk,
        )
    )
    if conflicts and not confirm_conflicts:
        raise ConflictingCommitments(conflicts)

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
