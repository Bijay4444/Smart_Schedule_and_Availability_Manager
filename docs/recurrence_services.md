# Recurring schedule services

The recurring backend is implemented in `scheduling/recurrence.py`. Local clock
resolution is isolated in `scheduling/time_resolution.py`. Neither module needs
a new dependency or migration. Browser forms and conflict preflight remain the
next integration increment; recurring writes are not exposed by routes or admin.

## Entry points

Every database operation takes the current `owner`. Object IDs are looked up
through that owner, rather than trusting model objects supplied by a caller.

| Service | Behavior |
| --- | --- |
| `create_series` | Create the series, initial revision, and at least one distinct weekday atomically. Accept `starts_on`, optional inclusive `ends_on`, local clocks, `end_day_offset` 0/1, and an IANA zone. New series require an active owned source. |
| `revise_series` | Replace the regular pattern from `effective_from`, applying the new clocks and weekday selection to all future dates. Keep earlier portions and all explicit exceptions. |
| `end_series` | Shorten the lifetime using an exclusive `ends_before` original-start-date cutoff. Preserve stored revisions/exceptions. Never reopen or extend the lifetime. |
| `cancel_occurrence` | Cancel one original date; replace a prior reschedule if present. Repeated cancellation keeps the same exception identity. |
| `reschedule_occurrence` | Suppress the original and store a complete replacement with an owned source, title, and explicit aware instants. This allows a deliberate choice of the second repeated clock time. |
| `occurrences_for_user` | Calculate whole intervals overlapping an aware, positive `[starts_at, ends_at)` range of at most 366 elapsed days. Return an `OccurrenceResult`, without storing generated instances. |
| `resolve_local_time` | Convert a naive local datetime and IANA zone into a valid aware local datetime plus metadata explaining any automatic choice. No database access. |

Monday is weekday 0; Sunday is 6. An overnight rule has `end_day_offset=1`.
Pass Python `date`/`time` values for local rules and aware `datetime` values for
actual intervals; future forms parse input before calling these services.
An inclusive last Sunday permits its occurrence to finish on Monday. A query
returns the whole occurrence in both affected weeks; the calendar later clips
its visible portions. Touching endpoints do not overlap a query.

## Revision and exception behavior

Future-effective edits and series-ending cutoffs must be today or later in the
series' original zone. Creation may record an existing schedule with an earlier
start date. This protects earlier schedules from accidental all-future edits;
explicit one-off corrections remain possible for original dates inside the
series lifetime.

An all-future edit supersedes any later planned regular revisions. If the edit
lands inside an existing revision, close that revision at the edit date. If it
lands exactly on an existing future boundary, replace the rule starting there.
Preserve the earlier portions in either case. Successors inherit the previous
DST policies. Changing the source, original zone, or lifetime is not part of
`revise_series`.

Exception identity is `(series_id, original_start_date)`, even when its actual
replacement moves into another week. A new exception must target a selected
weekday in an effective revision. An existing exception remains editable when
a later pattern removes that weekday. Ending the parent lifetime suppresses
exceptions by original date, even if their actual interval is later. Conversely,
a replacement whose original date precedes the cutoff can still occur after it.

Archived sources retain occupied time. Reschedules may keep the series' original
archived source or their existing archived replacement source; a new source
assignment requires an active source. Ownership is checked on both the series
and replacement source.

Writes use atomic transactions. Source assignment locks the source before the
series. Revision, ending, and exception writes share a lock on the stable series
row, including when no exception exists yet. That serializes cooperating writes;
the PostgreSQL range exclusion is an additional defense against overlapping
regular revisions. See [Django row locking](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#select-for-update).

## Clock resolution and incomplete results

Try both fold values, round-trip each through UTC, and retain candidates whose
local clock labels match. One distinct instant is normal; two indicate a
repeated time; zero indicate a gap. Choose the earlier instant for a repeat.
For a gap, use the forward round-trip, shifting by the actual offset change.
This preserves minutes and supports half-hour changes and skipped dates.
This is the application policy built on [ZoneInfo](https://docs.python.org/3.13/library/zoneinfo.html)
and [PEP 495](https://peps.python.org/pep-0495/), not a built-in validator.

`ResolvedTime` includes the requested clock label, the resulting zoned value,
and an adjustment of `gap_shift_forward`, `fold_first`, or `None`. Occurrences
retain endpoint metadata so the frontend can explain the choice. Actual interval
ordering and durations use UTC; a Halifax 22:00–06:00 shift can last seven or
nine elapsed hours across DST while preserving the entered clocks.

The query returns:

- `occurrences`: immutable records with identity, source/title, UTC endpoints,
  resolution metadata, and a replacement flag.
- `issues`: original dates whose resolved intervals are zero-length or reversed,
  with endpoint metadata for review.
- `complete`: false when any issue is present. Issues affect their local date(s),
  including overnight carry-in. Future availability calculations must check this
  and must not offer affected dates as complete.

A one-off reschedule or cancellation can resolve an issue. The existing one-time
browser forms continue to reject ambiguous/missing input until frontend controls
are connected to this resolver.

Regular generation includes a small nominal-date margin for offsets, overnight
ends, and skipped dates, then filters by actual UTC overlap. Original-key
exceptions suppress the regular occurrence even when the replacement is outside
the query. A separate actual-interval query finds replacements moved in from any
original date, including from a parent whose lifetime is outside the query.
Related rows are prefetched to avoid a separate query for each occurrence.

## Verification and next integration

The complete PostgreSQL suite passes 170 tests. Recurrence coverage includes
atomic creation and rollback, earlier-week preservation, all-future edits,
exception persistence, moves across weeks, inclusive last overnight occurrences,
end cutoffs, archival, ownership, UTC boundaries, DST, and bounded query counts.
Concurrent future edits and duplicate cancellations run on separate database
connections. Resolver tests also cover Lord Howe's half-hour transition and
Apia's skipped date.

The raw-insert exclusion test accepts only an exclusion violation or PostgreSQL's
specific deadlock-abort code, and requires exactly one committed row. The latter
was observed when competing raw inserts waited on tentative index entries.
The service tests require both edits/cancellations to complete through the parent
lock and do not catch deadlock failures. PostgreSQL resolves a detected deadlock
by aborting a transaction; see its [locking documentation](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS).

Next, connect recurring and one-time occupied intervals to conflict checks and
confirmation, then expose recurring forms and visible clock-resolution/review
messages. The current recurring write services enforce domain integrity; they
do not perform conflict preflight or claim that an infinite future series is
conflict-free. Working windows, availability, and the weekly calendar follow in
the [development checklist](development_checklist.md).
