# Check a proposed shift

Sign in and open `/check-shift/`, choose **Check a shift**, or follow the offered
shift link from a selected availability week. Enter the start and end date/time,
then select **Check shift**. For an overnight offer, use the following end date.
The form checks an offer; it does not create a commitment, reserve the time, or
change working windows. Check again after changing your saved schedule.

## Reading the result

- **Available for this shift:** every instant is covered by working windows,
  no commitments overlap, and the calculation is complete.
- **Not available for the full shift:** the complete calculation found a
  commitment conflict, hours outside working windows, or both.
- **Needs review — availability not confirmed:** a schedule time could not
  form a valid resolved interval. Review links lead to the relevant working
  hours or calendar date. Known overlaps remain visible. Unresolved working
  hours must be corrected before treating their coverage as final.

Commitment conflicts and uncovered intervals are listed separately. Commitment
titles and sources appear only inside the signed-in user's private checker;
they are never added to employer-facing availability text. Each conflicting
commitment links to the affected calendar week. No working windows means the
entire offered shift is outside working windows, even if the calendar is empty.
Adjacent boundaries do not conflict. Travel buffers and minimum shift lengths
remain deferred.

The start and end can cross midnight or a week boundary. The existing service
accepts at most 366 elapsed days and rejects invalid or extreme calendar dates;
the form displays those errors without calculating a result. The checker reads
one-time commitments, recurring revisions, cancellations, moved-in replacements,
and commitments from archived sources through the existing availability service.

## Halifax clock changes

All inputs and results use `America/Halifax`, independently of the active device
or Django display timezone. Missing times move forward by the clock-change gap.
Repeated times default to their first occurrence. Expand **Clock-change options**
to select the second occurrence for either endpoint. Selecting a second hour
on an ordinary time produces a correction message, rather than silently ignoring
the choice. Clock notes explain every automatic or explicit adjustment.

Validation compares actual UTC instants. First 01:45 ADT to second 01:15 AST is
a positive half-hour shift despite the decreasing clock labels. A spring-forward
resolution that leaves zero or negative elapsed time is rejected. Results show
zone abbreviations and preserve input seconds/fractions when present.

## Architecture and learning notes

| File | Responsibility |
| --- | --- |
| `scheduling/shift_forms.py` | Parse local form inputs, use the shared clock resolver, validate the bounded interval, and explain clock choices. |
| `scheduling/shift_presentation.py` | Call the existing shift-check service once, then project its result into local labels and corrective links. |
| `scheduling/shift_views.py` | Require login, bind the form, pass the authenticated owner, and render a private, non-cacheable response. |
| `templates/scheduling/proposed_shift.html` | Server-render inputs, separate result reasons, review links, and clear/current-schedule feedback. |
| `tests/test_shift_screen.py` | Test the browser-facing contract, privacy, no writes, query bounds, and DST behavior. |

The calculation remains in `scheduling/availability.py`; the view contains no
overlap or subtraction logic. The screen does not need a model or a saved report:
each submitted form recalculates from the current schedule. It ignores forged
owner/source POST fields and uses only the signed-in owner. POST uses Django
CSRF protection, and rendered checker pages use
`Cache-Control: private, no-store`.

The UI extends the existing editor composition, green palette, self-hosted
Instrument Sans, and shared controls. Native form submission and expandable
clock options work without JavaScript. A fragment target takes a successful
submission to its answer; validation errors retain the entered values for
correction. Availability-week links prefill a date, and **Clear** resets the form.

## Verification

All **451 PostgreSQL tests pass**, including 40 new checks for authentication,
private owner reads, forged-owner rejection, unsaved model snapshots, CSRF,
selected-date links, invalid dates and durations, no-window and split-window
coverage, strict overlap boundaries, recurring/archived/moved/cancelled
commitments, overnight carry-in and date overrides, unresolved working and
commitment clocks, first/second repeated hours, spring-forward validation,
fractional seconds, timezone independence, and bounded read queries.
Django system checks, migration drift, and whitespace checks pass.

Chromium verifies available offers, separate conflict/outside results, long
titles, unresolved-date links, repeated-hour choices, invalid options, correction
and clear, availability navigation, recalculation after a schedule change, and
no-JavaScript checking. Captures cover 1440px, 820px, 390px, and 320px widths.
The manual template detector reports no findings; its static Django-template
scan does not prove full computed-style coverage, so rendered captures are
reviewed as well. Fictional fixtures use a disposable database, which is removed
after the browser run. No new dependency, migration, or application-data change
is required.

Source archive controls, one-time entry polish, prepared demo fixtures, and the
final rehearsal remain on the [development checklist](development_checklist.md).
REST APIs, voice entry, and Google Calendar integration remain deferred.
