# Working schedules and availability services

The backend stores a person's willingness to work, then calculates availability
by subtracting their commitments. It uses the confirmed rules in
[project_spec.md](project_spec.md) and [database_design.md](database_design.md).
No new Python dependency is required. Migration `0004_working_availability`
adds four tables; existing commitments and recurring records are preserved.

## Service entry points

All database services require the current `owner`. The first version writes
working rules and overrides in `America/Halifax`; each header retains its zone.
The original backend increment added no browser forms. The
[working-window screens](working_window_screens.md) now configure weekly rules
and date overrides through these services. The [availability screen](availability_screen.md)
now provides visual weekly results and employer-facing text. The
[proposed-shift screen](proposed_shift_screen.md) calls `check_proposed_shift`
for a complete unsaved interval. REST routes remain separate work.

| Module and entry point | Behavior |
| --- | --- |
| `working_windows.set_working_schedule` | Set a complete weekly pattern from `effective_from`, using `WindowSpec` values. Initial setup may start in the past. Subsequent changes must be today or later. Preserve earlier revisions and supersede later plans. An empty list intentionally offers no weekly hours. |
| `working_windows.set_working_date_override` | Set the complete working hours for one `local_date`, using aware `Interval` values. Preserve its identity on updates. An empty list closes the whole date. |
| `working_windows.remove_working_date_override` | Delete an owned override by ID and restore the weekly pattern for that date. |
| `working_windows.working_windows_for_user` | Expand weekly windows and apply full-date overrides for an aware `[starts_at, ends_at)` query. Return UTC intervals, clock adjustments, and unresolved issues. |
| `availability.availability_for_user` | Subtract both one-time commitments and generated recurring occurrences; return available UTC intervals and review metadata. |
| `availability.weekly_availability_for_user` | Accept an anchor date and return Monday–Sunday availability grouped by Halifax date. Overnight intervals are split at local midnight for presentation. |
| `availability.check_proposed_shift` | Check every instant of an unsaved shift against working windows and commitments. Return conflicts, outside-window intervals, and completeness. |

Queries require positive, aware intervals of at most 366 elapsed days, away from
the extreme calendar boundaries. `WindowSpec.weekday` uses Monday=0 through
Sunday=6. `end_day_offset=1` permits an overnight window, including a full day
from 00:00 to the following 00:00. Multiple windows on a weekday are supported.
Exact duplicate rules are rejected; overlapping or touching windows are merged.

For example, from Django's shell with an existing authenticated user's model:

```python
from datetime import date, time
from scheduling.working_windows import WindowSpec, set_working_schedule
from scheduling.availability import weekly_availability_for_user

set_working_schedule(
    owner=user,
    effective_from=date(2026, 11, 16),
    windows=[WindowSpec(0, time(8), time(20))],
)
week = weekly_availability_for_user(owner=user, anchor=date(2026, 11, 16))
for day in week.days:
    print(day.local_date, day.intervals, day.complete)
```

With a class at 10:00–12:00 and protected study at 12:00–14:00, that Monday
offers 08:00–10:00 and 14:00–20:00. Without working windows or overrides,
availability is empty. Every positive remaining gap is retained.

## Why the calculation has separate stages

`scheduling/intervals.py` holds small UTC interval operations. `Interval`
validates aware endpoints and positive elapsed duration, then normalizes to UTC.
Merging produces a sorted union, and subtraction advances a cursor through each
working interval, retaining the gaps between occupied intervals. Strict overlap
boundaries allow one interval to begin exactly when another ends.

`scheduling/working_windows.py` owns dated weekly rules and overrides. Expand
windows using their original start date and revision; include a date margin to
find overnight carry-in. A Sunday window can still finish Monday after its
revision ends. Replace each overridden date's entire interval, including that
incoming portion, with the override's explicit intervals. Only then subtract
commitments in `scheduling/availability.py`.

The availability service calls the existing recurrence generator, so it inherits
future-effective edits, cancellation, rescheduling across query boundaries,
series-ending rules, and preserved archived-source commitments. It does not
store generated occurrences or availability reports. `working_windows` on an
availability result means willingness before commitment subtraction; `available`
means the remaining usable intervals.

## History, validation, and simultaneous writes

Working revisions use half-open date periods. An all-future change closes the
previous revision at the selected date and creates a successor atomically.
Explicit date overrides survive these regular-pattern edits. Earlier rules
are preserved; explicit date overrides may correct past dates.

The owner row is the stable lock parent for working-schedule and override
writes, including their first creation when no child row exists yet. This
serializes cooperating writes. PostgreSQL also prevents overlapping revision
periods for one owner with an exclusion constraint. Same-row checks enforce
valid weekdays, offsets, local ordering, and positive override intervals.

Override intervals must lie inside their header's complete local date; their
end may equal the next midnight. This joined rule is validated by the service.
Represent overnight one-off willingness with an override on each affected date.
The service accepts explicit aware instants, allowing a deliberate choice of
the second repeated hour. It merges overlapping override intervals before
storing them. Direct ORM writes bypass these service-level rules.

## Daylight saving and incomplete dates

Both endpoints use the existing resolver and the revision's stored policies:
move missing times forward by the actual gap and use the first repeated time.
Retain adjustment metadata for presentation. Calculate durations and subtract
intervals in UTC; resolve both local midnights independently. A date can have
23 or 25 elapsed hours.

An invalid resolved working interval produces a working issue. Availability
withholds all affected dates until an explicit date override resolves that
working rule. An invalid recurring commitment likewise withholds its affected
dates, including overnight carry-in; a working override cannot clear a
commitment issue. Correct or cancel the occurrence through the recurring service.
Other dates may still offer availability, and weekly results expose completeness
per date as well as for the whole query.

`check_proposed_shift(...).is_available` is true only when the result is complete,
there are no commitment conflicts, and no part lies outside working windows.
Its `outside_working_windows` field describes window coverage independently of
commitment conflicts. A review issue prevents a successful check even when
those two fields are empty. Checks never create commitments.

## Verification and remaining integration

The PostgreSQL tests cover the agreed subtraction example, multiple/overlapping
windows and commitments, minute-long gaps, Sunday-to-Monday boundaries, dated
revisions, empty/nonempty overrides, ownership, archived sources, recurring
changes and exceptions, DST clocks and elapsed durations, review withholding,
shift checks without saves, bounded query counts, transaction rollback,
concurrent writes, database constraints, and migration preservation.
All 261 tests pass on PostgreSQL, including 72 new tests for this increment.
Django's system check and migration-drift check also pass.

Apply the new migration to the application database with
`uv run python manage.py migrate` once its PostgreSQL service is running.
Development verification used a separate temporary PostgreSQL cluster because
the installed service was stopped; it did not apply migrations to the user's
application database.

The [one-time save-warning service](conflict_services.md) now checks both
one-time and recurring commitments, as does the proposed-shift checker. Shared
affected-date calculation lives in `scheduling/intervals.py`; all schedule-write
services now reuse the owner lock in `scheduling/locking.py`.
Recurring-write conflict review and forms are now available through the
[recurring workflow](recurring_workflow.md), with a visible 12-month preview
and signed confirmation. Working-window forms and availability display/copying
are implemented. Prepared demo data remains in the
[development checklist](development_checklist.md).
