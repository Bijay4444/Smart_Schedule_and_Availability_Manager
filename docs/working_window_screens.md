# Working-window configuration screens

Open `/working-windows/` or choose **Working windows** in the main navigation.
These screens configure willingness to work, before commitments are subtracted.
They do not label those windows as final work availability. No new dependency
or migration is added; the tables come from migration 0004.

## Weekly patterns

Choose **Set weekly windows**, select an effective date, and add rows containing
a weekday, start time, end time, and optional **Ends the following day** choice.
Multiple rows can share a weekday. Exact duplicates are rejected; distinct
overlapping windows remain valid and are merged by the calculation service.

The editor copies the complete pattern active on the selected date. Saving
calls `set_working_schedule` with the full submitted pattern. Earlier schedules
stay intact; later planned weekly patterns are superseded from that date.
Initial setup may describe the past, while later general changes must start
today or later. The screen explains this rule and displays schedule history.

To stop weekly working windows, remove the rows and select **No weekly working
windows from this date**. Empty rows alone do not silently clear the schedule.
An already saved empty pattern is prefilled with that choice selected.
An overnight window started under the previous pattern can still finish after
the effective date; the dated preview uses the existing service's carry-in rule.

## Full-date overrides

Choose **Override one date**, or use an individual date's link in the preview.
An override replaces the whole local date, including hours carried in from an
overnight weekly window. Enter one or more same-date intervals, or select
**Unavailable for work all day** with no intervals. Intervals and the all-day
closure choice cannot be submitted together without correction.

An interval may finish at the **following midnight (24:00)**. For an overnight
one-off working period, enter the appropriate intervals on both dates. Each
date's bounds are calculated independently, so a full-date override can contain
23 or 25 elapsed hours at a daylight-saving transition.

The clock-change options allow choosing the second repeated hour for either
endpoint. Missing times move forward by the transition gap; repeated times use
the first occurrence by default. Successful saves explain any clock adjustment
in feedback and show the resulting zoned hours. Invalid resolved intervals are
field errors and leave existing records unchanged.

Use **Edit date** to replace an existing override without changing its identity.
The date is fixed on that route. **Restore weekly windows** shows a confirmation
form; its confirmed POST removes the override and reinstates the normal pattern,
including any overnight carry-in. A GET never removes an override.

## Overview and preview

The overview shows the weekly pattern for a chosen date, dated overrides,
history/planned changes, and a Monday–Sunday working-window preview. It clearly
states that commitments have not been subtracted. The preview applies date
overrides and clips overnight portions to each displayed date.

Invalid resolved weekly intervals flag their affected dates for review instead
of showing a complete set of hours. **Correct this date** opens a date override.
Missing/repeated clock choices are displayed with their actual zoned endpoints.
An empty weekday in the regular pattern says **No windows start this day**;
that wording preserves the possibility of overnight carry-in.

## Implementation and learning notes

| File | Responsibility |
| --- | --- |
| `scheduling/working_forms.py` | Header forms, time-row formsets, duplicate detection, and safe row deletion. |
| `scheduling/working_views.py` | Authentication, owner-filtered override routes, form feedback, and redirects to named local routes. |
| `scheduling/working_windows.py` | Existing atomic writes/expansion, owned read helpers, and override clock-to-instant resolution. |
| `static/js/working-windows.js` | Add formset rows and update the management count without a reload; announce the new row and focus its first control. |
| `templates/scheduling/working_*.html` | The overview, editor, and restoration confirmation, using the existing shell, tokens, and form patterns. |

Django formsets represent a variable number of time rows. The management form
tracks their count; the server limits a submission to 100 rows and validates
all posted values. Marking a row for removal excludes it from the replacement
pattern. Posted rows are not seeded from database initial values, which avoids
unchanged extra forms being mistaken for empty rows.

The **Add another window** button also works without JavaScript: its POST
preserves entered values, adds a blank row, and performs no write. Existing
weekly/override write services retain their owner lock, transactions, date
history rules, interval merging, and validation. No scheduling calculations
were moved into views, and private ownership is derived from the session.

## Verification and remaining scope

The PostgreSQL suite passes **383 tests**, including 50 new screen/service
tests. Coverage includes multiple/overnight windows, empty patterns, effective
dates and history, explicit full-date closure, restoration of carry-in, DST
elapsed time and choices, invalid clock ordering, formset tampering, ownership,
CSRF, safe redirects, no-JavaScript row addition, and bounded read queries.
System, migration-drift, and whitespace checks pass.

Chromium passed weekly setup, dynamic row addition/removal, a future-effective
edit, date closure/edit/restoration, the second repeated hour, invalid DST input,
and no-JavaScript add/save. Desktop (1440px), tablet (820px), phone (390px), and
narrow-phone (320px) layouts had no page overflow or JavaScript errors. Desktop
and phone captures were inspected. Test accounts and records lived in a
disposable database; temporary browser tooling/captures stay under `/tmp`.

Migration 0004 must be applied before using these screens on an application
database. The user subsequently reported applying that migration; verification
of these increments uses disposable databases and does not change application
data.

The [availability screen](availability_screen.md) now displays the resulting
weekly hours and provides employer-facing text. The
[proposed-shift screen](proposed_shift_screen.md) checks offered hours through
the existing [availability services](availability_services.md) without saving.
