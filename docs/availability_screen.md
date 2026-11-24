# Weekly availability and employer-facing text

Open `/availability/` or choose **Availability** in the navigation. The screen
uses the existing weekly availability service: working windows after date
overrides, minus both one-time and recurring commitments. It adds no dependency,
database migration, stored report, or employer account.

## User flow

Choose a week using previous/next, **This week**, or **Week containing**. A
Monday–Sunday view shows confirmed available intervals as horizontal bars with
exact text ranges beneath them. Calendar and working-window links preserve the
selected week, so changing the schedule and returning gives a recalculated
result. Empty calendar space does not become availability without working hours.

The weekly total uses actual elapsed durations. Overnight intervals are split
at local midnight and appear in both affected weeks. Midnight at the end of a
date is labelled **24:00**. Every positive gap remains visible in the text,
including seconds and fractional seconds if present; minimum shift lengths and
travel buffers are not applied.

Use **Copy availability** to copy the readonly employer-facing text. The browser
writes to the clipboard only after that click and confirms success in a live
status message. If clipboard access is missing, insecure, or denied, the text is
selected and the screen asks the user to use their device's Copy action. It
does not falsely report success. Without JavaScript the button stays hidden;
the text remains selectable, and week navigation still works.

Example output:

```text
Work availability: 16 Nov 2026 – 22 Nov 2026
Time zone: America/Halifax

Mon 16 Nov: 08:00–10:00, 14:00–20:00
Tue 17 Nov: Unavailable
Wed 18 Nov: 20:00–24:00
Thu 19 Nov: 00:00–06:00
Fri 20 Nov: 08:00–20:00
Sat 21 Nov: Unavailable
Sun 22 Nov: 22:00–24:00
```

## Privacy and incomplete dates

`scheduling/availability_presentation.py` projects the calculation result into
immutable display days and slots. This projection contains no commitment
objects, titles, source names, or owner/account fields. The visual availability
content and copied text therefore omit private schedule details. The shared
navigation still shows the signed-in user's own account normally. The copy
formatter accepts only that display projection, rather than the database model
records used by the calculation service.

Dates withheld by unresolved clock issues are shown as **Needs review —
availability not confirmed**, with private review links to the appropriate
calendar or working-window screen. They are not called unavailable or offered
as confirmed hours. Other dates retain their confirmed intervals.

An incomplete week's copied text includes a **Draft** notice and the same
per-date **Needs review** markers. It may still be copied, with the uncertainty
explicit in the text. The copied text includes no cause, commitment title, or
review URL. Invalid working rules are not described as missing configuration.

The authenticated view derives ownership from the session, ignores forged owner
query parameters, validates canonical week dates, and sets `Cache-Control:
private, no-store`. It recalculates on each request. Copies previously sent to
an employer are not stored or updated by the application.

## Time and visual placement

Scheduling subtraction remains in `scheduling/availability.py`. The presentation
service converts the resulting UTC instants into Halifax labels and places each
bar by actual elapsed position inside that local date. Resolve the two midnight
instants independently: a DST date can have 23 or 25 elapsed hours. Axis marks
for local 00:00, 06:00, 12:00, 18:00, and 24:00 use those same actual positions.

Ordinary intervals use compact `HH:MM` labels. If an endpoint is in a repeated
hour, or an interval crosses an offset change, labels include the zone
abbreviation, for example `01:15 ADT–01:45 AST`. Seconds and fractional seconds
are retained when necessary instead of rounding a small positive gap away.
Confirmed totals also use UTC elapsed duration. Bar and axis percentages are
formatted with decimal points independently of the browser/Django locale.

The bars are decorative to assistive technology; headings, exact time ranges,
and unavailable/review states provide the complete textual result. The screen
retains the existing green identity, self-hosted font, responsive shell, and
reduced-motion behavior. Clipboard feedback uses a live status region.

## Files and verification

| File | Responsibility |
| --- | --- |
| `scheduling/availability_presentation.py` | Display projection, time labels, actual-duration positioning/totals, review flags, and employer text. |
| `scheduling/availability_views.py` | Authenticated, validated, private weekly GET endpoint. |
| `templates/scheduling/availability.html` | Week navigation, seven dated rows, review links, and readonly sharing text. |
| `static/js/availability.js` | Explicit clipboard copy, accurate success feedback, and text-selection fallback. |
| `tests/test_availability_screen.py` | Presentation, privacy, time boundaries, HTTP behavior, and query-count coverage. |

All **411 PostgreSQL tests pass**, including 28 new presentation/HTTP tests.
System, migration-drift, and whitespace checks pass. New coverage includes the
agreed subtraction example, no-window versus fully occupied states, account
isolation, omission of private titles/sources, incomplete draft text, DST day
durations and repeated-hour labels, overnight/week boundaries, positive
fractional-second gaps, selected-week links, fresh recalculation, unsupported
dates, timezone/locale independence, and bounded read queries.

The live Chromium journey passed actual clipboard success, missing and denied
clipboard fallbacks, privacy of copied text, navigation between calendar and
availability, recalculation after a schedule change, incomplete/draft copying,
repeated-hour labels, empty weeks, and JavaScript-disabled text/navigation.
Desktop (1440px), tablet (820px), phone (390px), and narrow-phone (320px) layouts
had no page overflow or JavaScript errors. Desktop/phone and incomplete-state
captures were inspected. Fixtures lived in a disposable database; browser tools,
runtime libraries, and captures remain under `/tmp`, outside project dependencies.
The manual Impeccable scan could not resolve Django's static stylesheet tag for
complete color coverage and flagged the already pinned Instrument Sans family;
the established font was retained and rendered captures were inspected.

The [proposed-shift screen](proposed_shift_screen.md) now checks offered hours
without saving them. Prepared demonstration data, source archive controls,
and one-time entry polish remain separate checklist items. REST APIs,
voice entry, and Google Calendar integration remain deferred.
