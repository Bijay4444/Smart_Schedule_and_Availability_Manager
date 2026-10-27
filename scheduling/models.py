from datetime import UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


def validate_time_zone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError("Choose a valid IANA time zone, such as America/Halifax.")


class CommitmentSource(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="commitment_sources",
    )
    name = models.CharField(max_length=80)
    color = models.CharField(
        max_length=7,
        default="#315c52",
        validators=[
            RegexValidator(
                regex=r"\A#[0-9a-fA-F]{6}\Z",
                message="Choose a color in #RRGGBB format.",
            )
        ],
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="source_name_unique_per_owner"
            )
        ]

    def __str__(self):
        return self.name


class Commitment(models.Model):
    """One-time occupied interval; ownership is inherited from its source."""

    source = models.ForeignKey(
        CommitmentSource, on_delete=models.PROTECT, related_name="commitments"
    )
    title = models.CharField(max_length=160)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        ordering = ["starts_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="commitment_end_after_start",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        for field in ["starts_at", "ends_at"]:
            value = getattr(self, field)
            if value and timezone.is_naive(value):
                errors[field] = "Enter a time with a time zone."
        if errors:
            raise ValidationError(errors)

        # UTC compares actual instants even when the fall-back clock repeats an hour.
        if (
            self.starts_at
            and self.ends_at
            and self.ends_at.astimezone(UTC) <= self.starts_at.astimezone(UTC)
        ):
            raise ValidationError(
                {"ends_at": "End must be after start. For an overnight shift, choose the next date."}
            )

    def __str__(self):
        return self.title


class RecurringSeries(models.Model):
    """Stable identity; revisions define its hours and exceptions target its dates."""

    source = models.ForeignKey(
        CommitmentSource, on_delete=models.PROTECT, related_name="recurring_series"
    )
    time_zone = models.CharField(max_length=64, validators=[validate_time_zone])
    starts_on = models.DateField()
    ends_before = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_before__isnull=True)
                | models.Q(ends_before__gte=models.F("starts_on")),
                name="series_lifetime_not_reversed",
            )
        ]


class SeriesRevision(models.Model):
    """A local-clock rule valid in a half-open date period."""

    class GapPolicy(models.TextChoices):
        SHIFT_FORWARD = "shift_forward", "Move forward by the clock change"

    class FoldPolicy(models.TextChoices):
        FIRST = "first", "First occurrence of a repeated time"

    series = models.ForeignKey(
        RecurringSeries, on_delete=models.PROTECT, related_name="revisions"
    )
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    title = models.CharField(max_length=160)
    start_time = models.TimeField()
    end_time = models.TimeField()
    end_day_offset = models.PositiveSmallIntegerField(default=0)
    dst_gap_policy = models.CharField(
        max_length=20, choices=GapPolicy, default=GapPolicy.SHIFT_FORWARD
    )
    dst_fold_policy = models.CharField(
        max_length=20, choices=FoldPolicy, default=FoldPolicy.FIRST
    )

    class Meta:
        ordering = ["effective_from", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(effective_until__isnull=True)
                | models.Q(effective_until__gt=models.F("effective_from")),
                name="revision_positive_date_period",
            ),
            models.CheckConstraint(
                condition=models.Q(end_day_offset__in=[0, 1]),
                name="revision_valid_day_offset",
            ),
            models.CheckConstraint(
                condition=models.Q(end_day_offset=1)
                | models.Q(end_time__gt=models.F("start_time")),
                name="revision_positive_local_interval",
            ),
            models.CheckConstraint(
                condition=models.Q(dst_gap_policy="shift_forward"),
                name="revision_valid_gap_policy",
            ),
            models.CheckConstraint(
                condition=models.Q(dst_fold_policy="first"),
                name="revision_valid_fold_policy",
            ),
            ExclusionConstraint(
                name="series_revision_periods_do_not_overlap",
                expressions=[
                    ("series", RangeOperators.EQUAL),
                    (
                        models.Func(
                            "effective_from", "effective_until", models.Value("[)"),
                            function="DATERANGE", output_field=DateRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.effective_from and self.effective_until:
            if self.effective_until <= self.effective_from:
                errors["effective_until"] = "End date must follow the effective date."
        for field in ["start_time", "end_time"]:
            value = getattr(self, field)
            if value and value.tzinfo is not None:
                errors[field] = "Enter a local clock time without a UTC offset."
        if (
            self.start_time and self.end_time and not errors
            and self.end_day_offset == 0 and self.end_time <= self.start_time
        ):
            errors["end_time"] = "End must follow start, or select the following day."
        if errors:
            raise ValidationError(errors)


class RevisionWeekday(models.Model):
    revision = models.ForeignKey(
        SeriesRevision, on_delete=models.CASCADE, related_name="weekdays"
    )
    weekday = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "weekday"], name="weekday_unique_per_revision"
            ),
            models.CheckConstraint(
                condition=models.Q(weekday__gte=0, weekday__lte=6),
                name="revision_weekday_in_range",
            ),
        ]


class OccurrenceException(models.Model):
    class Kind(models.TextChoices):
        CANCEL = "cancel", "Cancellation"
        RESCHEDULE = "reschedule", "Reschedule"

    series = models.ForeignKey(
        RecurringSeries, on_delete=models.PROTECT, related_name="exceptions"
    )
    original_start_date = models.DateField()
    kind = models.CharField(max_length=12, choices=Kind)
    replacement_source = models.ForeignKey(
        CommitmentSource, on_delete=models.PROTECT, null=True, blank=True,
        related_name="replacement_exceptions",
    )
    replacement_title = models.CharField(max_length=160, null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["series", "original_start_date"],
                name="exception_unique_per_original_date",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="cancel", replacement_source__isnull=True,
                        replacement_title__isnull=True,
                        starts_at__isnull=True, ends_at__isnull=True,
                    )
                    | (
                        models.Q(
                            kind="reschedule", replacement_source__isnull=False,
                            replacement_title__isnull=False,
                            starts_at__isnull=False, ends_at__isnull=False,
                        )
                        & ~models.Q(replacement_title="")
                        & models.Q(ends_at__gt=models.F("starts_at"))
                    )
                ),
                name="exception_payload_matches_kind",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        for field in ["starts_at", "ends_at"]:
            value = getattr(self, field)
            if value and timezone.is_naive(value):
                errors[field] = "Enter a time with a time zone."
        if (
            self.starts_at and self.ends_at and not errors
            and self.ends_at.astimezone(UTC) <= self.starts_at.astimezone(UTC)
        ):
            errors["ends_at"] = "End must follow start."
        if self.replacement_source_id and self.series_id:
            # Invalid foreign keys already have field errors from full_clean().
            try:
                source_owner = self.replacement_source.owner_id
                series_owner = self.series.source.owner_id
            except (CommitmentSource.DoesNotExist, RecurringSeries.DoesNotExist):
                pass
            else:
                if source_owner != series_owner:
                    errors["replacement_source"] = "Choose a source belonging to the series owner."
        if errors:
            raise ValidationError(errors)
