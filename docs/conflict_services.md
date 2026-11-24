# Conflict warnings for one-time saves

One-time add/edit now checks both stored one-time commitments and generated
recurring occurrences before saving. The existing warning/confirmation screen
shows their actual dates and times. The commitment list retains overlap badges
against both kinds; the weekly calendar already shows both sides of an overlap.
This increment adds no dependency or migration.

## Service interfaces

`scheduling.conflicts.inspect_conflicts(owner=..., starts_at=..., ends_at=...,
exclude_pk=...)` accepts aware positive intervals and returns a `ConflictCheck`:

- `conflicts`: overlapping `Commitment` and `Occurrence` records, sorted by time.
- `issues`: recurring dates whose automatic DST resolution needs review.
- `complete`: false when those issues affect the candidate's dates.

`exclude_pk` excludes only the one-time record being edited. A recurring
occurrence has a separate `(series_id, original_start_date)` identity, even if
its series ID happens to equal that one-time primary key.

`scheduling.services.save_commitment` checks ownership, archived-source rules,
model validation, and the combined conflict result inside one transaction.
Without confirmation, conflicts or review issues raise `ConflictingCommitments`
with `.conflicts` and `.issues`; no record is created or changed. The existing
`confirm_conflicts=True` explicitly acknowledges those warnings and allows saving.
The check runs again for every save, including confirmed requests.

`commitments_for_user` now returns an evaluated list with `has_conflict` and
`conflict_check_complete` on each one-time record. It retains the SQL annotation
for one-time overlaps and adds recurring information in batches. These values
are calculated from current schedules, so cancellation or rescheduling updates
the indicators on the next request.

The existing `find_conflicts` import from `scheduling.services` remains a
low-level one-time queryset helper, supporting SQL `OuterRef` expressions for
annotations. Use `inspect_conflicts` for a complete one-time/recurring warning
result. A commitment save is independent of working windows: record actual
obligations even outside preferred working hours. To check whether an offered
shift fits both working windows and commitments, use
`availability.check_proposed_shift` instead.

## Recurrence, time, and query limits

The service reuses `occurrences_for_user`, preserving revision history, selected
weekdays, cancellations, moves between weeks, archived-source commitments, and
series-ending cutoffs. A final Sunday overnight occurrence still warns about
Monday overlaps. Strict inequalities allow touching boundaries. UTC comparison
distinguishes the two repeated hours on a fall-back date.

The recurrence generator limits each query to 366 elapsed days. One-time
commitments can span longer periods, so conflict inspection splits their full
duration into supported chunks and deduplicates occurrences/issues by identity.
It checks the entire candidate interval rather than using an arbitrary future
preview horizon. Calendar-limit validation is retained from the generator;
unsupported legacy list entries stay readable with an incomplete-check flag.

For list indicators, nearby commitment intervals share a bounded query. Widely
separated commitments get separate queries, avoiding expansion through years
with no listed commitments. Overlaps and issues returned for gaps inside a
batch are matched back to each individual commitment. Related recurrence rows
are prefetched, so query count does not grow per generated occurrence or per
listed record within one batch.

## Review warnings and simultaneous writes

An invalid DST interval is an incomplete check, not a proven conflict or a clean
result. The form names the recurring commitment and original date and requires
explicit acknowledgement. Acknowledgement permits recording the real obligation;
it does not repair the recurrence. The list retains a review message, and the
availability service continues withholding affected dates until the occurrence
is corrected or cancelled. Shared affected-date calculation lives in
`scheduling/intervals.py` so conflict checks and availability agree.

`scheduling/locking.py` provides a common owner-row lock. One-time saves, recurring
creation/revision/ending/exception writes, and working-schedule writes acquire it
inside atomic transactions. The order is owner, then source when assigning one,
then series/commitment. This prevents two simultaneous one-time saves under
different sources from both checking an empty schedule. It also prevents a
one-time save from inspecting a half-finished recurring transaction. Different
owners remain independent. Source archival retains its source lock and never
waits for the owner, avoiding an inverted lock order. Direct ORM writes bypass
these service guarantees.

## Verification and remaining scope

Regression coverage includes service and HTTP warning/confirmation flows,
unchanged records after rejected edits, persistent indicators, account privacy,
archival, cancellation/rescheduling, future revisions, final overnight instances,
repeated clocks, unresolved DST issues, long-interval chunking/deduplication,
bounded list queries, and simultaneous writes on separate database connections.
All 291 tests pass on isolated PostgreSQL, including 30 new tests for this
increment. Django's system check, migration-drift check, and whitespace check
pass. HTTP verification uses Django's test client; no new live browser check
was performed. The application database was not changed.

The lower-level recurring write services remain integrity operations. The new
[recurring workflow](recurring_workflow.md) wraps them for browser writes with
staged rollback and signed review. Creation/future edits use the confirmed
12-month preview, explicitly displaying unchecked later dates; one-off changes
check the entire actual replacement. Recurring HTML routes are exposed through
that workflow. REST APIs remain deferred.
