# Recurring entry, review, and editing

Recurring commitments can now be created and maintained through the signed-in
application. Open `/recurring/`, use **Add recurring** on the calendar, or open
an occurrence's calendar details. The existing green editor and responsive
patterns are retained; no application dependency or database migration is added.

## User flow

Create a series with an owned active source, title, selected weekdays, first
date, optional inclusive last start date, and local start/end times. **Ends the
following day** permits overnight rules. The first submission shows a review;
it does not save the series. Review the checked date range, clock choices, and
conflicts, acknowledge them, then save.

The user selected a **12-month conflict preview** for open-ended series on
2026-11-05. Creation checks from the first date; future edits check from their
effective date. A shorter finite lifetime shortens the preview. Longer finite
or open-ended schedules explicitly state that dates after the preview are not
checked. This is a warning preview, not a promise about every future occurrence.
Calendar conflicts and availability continue to calculate any requested dates
from the current schedule. A final included overnight instance is checked for
its full duration, including the following date.

Repeated overlaps are grouped by the counterpart commitment. Show the count and
first actual overlap, with every remaining date expandable. Confirmation signs
the complete result, including dates inside those collapsed groups.

**Change future hours** chooses a date and replaces all regular rules from that
date. Earlier revisions and explicit exceptions are preserved. **End recurrence**
stops original occurrence dates on/after the cutoff, including replacements
whose original dates meet that cutoff. These existing domain rules remain in
`scheduling/recurrence.py`.

Calendar details offer **Change this occurrence** and **Cancel this occurrence**,
using the stable original date even after a move. The change form accepts actual
replacement dates/times, an owned source, and a title. A replacement gets a full
finite-interval review and can conflict with other occurrences of its own series.
Cancellation and ending require a confirmation POST; GET never changes data.
The recurring list shows regular schedule history and one-off changes, including
cancelled occurrences that no longer have a calendar block.

## Why review uses a transaction and signed token

`scheduling/recurring_workflow.py` is the browser's write boundary. It wraps the
existing creation/revision/replacement services:

1. Acquire the shared owner lock through the underlying write service.
2. Stage the requested change inside an atomic transaction.
3. Generate actual occurrences and compare them with one-time and recurring
   commitments. Include internal overlaps between occurrences of the new series.
4. Build the preview and a digest of the inputs, owner, action, checked dates,
   actual occurrences, conflicts, clock adjustments, and review issues.
5. Without a matching confirmation, raise `ReviewRequired`. This rolls back the
   entire staged write, including closed revisions and exception changes.
6. On final submission, stage and calculate again under the owner lock. Commit
   only if the acknowledgement and signed digest match the current result.

Tokens expire after one hour. Forged/expired tokens, changed inputs, another
owner's token, or newly changed conflicts return a fresh review with the
acknowledgement cleared. Tokens contain a digest, not private commitment text.
Creation normalizes the transient staged series identity so PostgreSQL sequence
advancement after rollback cannot invalidate an otherwise unchanged review.
Generated instances and reviews are not stored in additional tables.

`save_recurring_series(owner=..., values=..., series_id=None, review_token=None,
confirmed=False)` handles creation or a future-effective revision.
`save_occurrence_change` handles a finite replacement. The lower-level recurrence
services remain useful for controlled fixture/setup operations; browser views
always call the reviewed workflow for additions or changes that occupy time.

Conflict inspection reuses the recurrence generator and finite-interval chunking
in `scheduling/conflicts.py`. Replacements are checked over their entire actual
duration. Source archival and original-date ending rules therefore retain the
same meaning as calendar and availability calculations.

## Daylight-saving review and correction

Regular rules retain the stored automatic policies: shift missing clock times
forward by the transition gap and choose the first repeated clock time. Reviews
show actual zoned endpoints on adjusted dates. Invalid resolved intervals appear
as review issues. They may be acknowledged to record the real schedule, but
availability continues withholding their affected dates until corrected.

The occurrence change form uses the same resolver. It reports automatic clock
choices before confirmation and offers explicit **second repeated hour** options
for start/end. Those options are rejected when the entered clock is not repeated.
The resulting replacement stores explicit aware instants. Calendar review notices
link directly to changing or cancelling the affected occurrence.

`recurring_forms.py` parses and validates input; `recurring_views.py` supplies
authentication, owner-filtered object lookups, form feedback, and navigation.
Scheduling rules and writes stay in services. All write routes retain Django's
CSRF protection, and redirects only use validated week dates and local named
routes. The selected week survives review, confirmation, and cancellation.

## Verification and remaining work

Tests cover staged rollback, confirmation, stale/forged/expired/cross-owner
tokens, unchanged history/exceptions until confirmation, one-time/recurring/self
overlaps, overnight endings, DST choices/issues, private routes and lists,
source forgery, CSRF, cancellation/ending, and stable original-date calendar links.
The full suite also retains the existing database, concurrency, availability,
calendar, and one-time workflow tests.

Verification: **333 PostgreSQL tests pass**, including 42 new recurring-workflow
tests. Django's system check, migration-drift check, and whitespace check pass.
The Chromium journey passed at 1440px, 820px, 390px, and 320px widths with no
page overflow or JavaScript errors. Desktop and phone captures were visually
inspected after grouping repeated warnings. The Impeccable source scan could
not resolve Django's static stylesheet tag, so its color coverage is incomplete;
its Instrument Sans warning was retained as an existing, explicitly pinned font.

The live browser journey uses a disposable database and fictional account. It
covers create/review/confirm, selected-week return, future edits, one-off changes,
cancellation, ending, and responsive layouts. Temporary tooling, runtime
libraries, and captures are kept under `/tmp`; the application database is not
changed. The new screens reuse current CSS tokens and the shared shell.

Working-window configuration now has its own [screens](working_window_screens.md).
Availability display and copying now have their own [screen](availability_screen.md).
Prepared demo data and the one-time form's easy following-day option remain in
the [development checklist](development_checklist.md). The one-time form still
uses explicit dates and rejects ambiguous/missing local clock inputs; automatic
DST correction in this increment applies to recurring rules and their overrides.
