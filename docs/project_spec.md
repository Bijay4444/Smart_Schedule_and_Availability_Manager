# Smart Schedule and Availability Manager

Status: scope interview complete. Scheduling behavior, first-version scope,
and the eight-hour demonstration allocation are agreed. Development has begun
with the increments described below. The user confirmed the
[database design](database_design.md) in DB18; implementation follows that
data-preserving migration plan.

## Current implementation status

The initial project includes a Python 3.13 environment, locked dependencies,
Django settings and entry points, a standard-session login/logout flow, a
protected home page, and an extensible user model with its initial migration.
The local PostgreSQL server is installed, the application database is created,
and migrations through the recurring database foundation are applied. Tests now
use a disposable PostgreSQL database to verify the actual schema. Scheduling
now includes user-owned commitment sources, one-time commitment create/edit/delete
screens, overnight dates, overlap warnings with explicit confirmation, and
persistent conflict indicators. Source archival and protected references retain
existing commitments. Recurring series, dated revisions, weekdays, and exceptions
are stored in the new tables, with PostgreSQL revision-period exclusions.
The 189-test PostgreSQL suite passes, including migration preservation and
concurrent writes. Recurring services now support creation, future edits,
ending, one-off exceptions, and bounded occurrence generation with DST metadata
and review issues. A prior live HTTP check passed the existing workflow and
archived-source correction. The weekly calendar is now available at `/week/`,
with source colors, overnight portions, date-to-form entry, details, visible
overlap indicators, and a phone agenda. Chromium checks passed at desktop,
phone, and tablet sizes. Conflict-save integration, recurring forms, working
windows, and availability remain future increments.
See the [recurrence service guide](recurrence_services.md) for architecture,
the [calendar guide](weekly_calendar.md) for the frontend,
the [development checklist](development_checklist.md) for task status, and
[README.md](../README.md) for setup and verification.

## Problem and purpose

Students and people working multiple jobs need to combine classes, shifts, and
personal commitments before deciding when they can work. A clear weekly schedule
and calculated availability should help them avoid accepting overlapping shifts
and give employers useful availability without exposing private commitments.

The first users are the developer, who balances student and work commitments,
and the developer's wife, who balances two jobs. Each person has a separate
account and private schedule. Employers do not need accounts.

## Agreed workflows

1. Primary: generate realistic work availability for a selected week.
2. Supporting: check whether a proposed shift conflicts with existing commitments.
3. Supporting: see commitments together in a visual weekly view.

Work availability is calculated only inside the user's working windows, after
subtracting commitments. Empty calendar space is not automatically work
availability. Study and personal time can be protected as commitments.

For example, a Monday working window of 08:00–20:00, a class at 10:00–12:00,
and protected study time at 12:00–14:00 leave work availability of 08:00–10:00
and 14:00–20:00. A commitment ending exactly when another begins does not
overlap it. Travel buffers and minimum shift lengths are deferred; every
positive-length available interval is displayed.

See [GLOSSARY.md](../GLOSSARY.md) for domain terminology.

## First demonstration

The user's latest estimate is a class demonstration in approximately two weeks,
with about four hours available per week: roughly eight hours of personal
development and learning time. This supersedes the earlier one-week estimate.
The exact presentation date remains unconfirmed.
The first milestone is a working demonstration, followed by incremental
improvements; it is not the final submission.

The presentation has a three-minute limit. Its focus is one clear outcome:
turning a schedule of classes, multiple jobs, and personal commitments into
work availability that can be given to an employer.

Run the demonstration locally on the developer's laptop. The desktop weekly
calendar is the main presentation, with a usable phone layout. Public hosting
is deferred.

### Agreed first-version feature scope

- Authentication with private schedules for individual users.
- Manually create, edit, and delete commitments.
- Both one-time and weekly recurring commitments from the first version.
- Both one-time and weekly recurring overnight commitments, including work shifts.
- Configure working windows.
- A visual weekly schedule as a central part of the interface.
- Previous/next week navigation and clicking a day to open a commitment form.
- Color coding for commitments and subtle, smooth animations.
- Identify scheduling conflicts and check a proposed shift.
- Generate weekly work availability and display it visually.
- Copy a simple text availability list to share with an employer, without
  including private commitment details.

The full demonstration journey is: sign in, enter commitments and working
windows, see the week, check an offered shift, generate availability, and copy
it. The user accepted the acceptance scenarios below and invited additional
relevant cases. The agreed initial demonstration allocation below prioritizes
a complete useful workflow within the available personal development time.

### Agreed eight-hour demo allocation

Preserve the agreed first-version features above. The allocation changes when
they appear in the demonstration, not the scheduling behavior they require.

Prioritize a working journey through login, simple commitment entry, a colored
weekly view, calculated availability, and copying employer-facing text.
One-time entries, weekly recurrence, and overnight commitments remain part of
this journey because they are needed for the first users' real schedules.

Use prepared sample users, commitment sources, and working windows for the
presentation. Their complete configuration screens can follow. Use Django's
existing authentication facilities; custom registration and password-recovery
flows are outside this demo allocation.

Keep the proposed-shift checking service covered by tests; its dedicated
interactive screen can follow the core demo if time is short. Complete source
management, richer editing screens, and animation polish follow the working
core. Any conflicting-commitment save action exposed in the demo still needs
the agreed explicit warning.

The table is a planning allowance for guided development and learning, not a
guarantee of implementation time. Setup trouble or unresolved defects take
priority over optional polish.

| Session | Personal time allowance | Intended outcome |
| --- | --- | --- |
| 1 | 2 hours | Local project/database setup, basic login, and the initial commitment data model. |
| 2 | 2 hours | Recurrence, overnight handling, availability and shift-check services, meaningful tests, and sample data. |
| 3 | 2 hours | Simple commitment entry, source colors, week navigation, and the weekly availability display. |
| 4 | 2 hours | Copyable availability, privacy and end-to-end checks, fixes, and presentation rehearsal. |

Retain the full acceptance checklist as the first-version target and identify
which checks are demonstrated through the interface versus service tests at
this milestone. Describe a feature as implemented only after it is verified.

### Three-minute presentation walkthrough

Start with the local app running, already signed in, and the prepared schedule
loaded. Use sample commitments for classes, two employers, and personal time.
Include a prepared Sunday-to-Monday overnight commitment. Rehearse the journey
so setup and account entry do not consume presentation time.

| Time | What to show or explain |
| --- | --- |
| 00:00–00:20 | State the problem: combining classes, jobs, and personal time to answer an employer's availability request. |
| 00:20–00:45 | Show the weekly calendar and explain the source colors and protected personal time. |
| 00:45–01:25 | Add one commitment and show it on the calendar; identify an existing weekly recurring commitment. |
| 01:25–02:05 | Generate the resulting work availability and copy the employer-facing text. Explain that availability is working windows minus commitments. |
| 02:05–02:30 | Navigate the prepared overnight example to show that both affected weeks contain the appropriate part of the commitment. |
| 02:30–02:50 | Briefly explain the Django frontend, scheduling services, and tested edge cases; name voice entry and calendar integration as later work. |
| 02:50–03:00 | Allow time for transitions or a brief closing sentence. |

The main demonstration success is visible schedule input producing correct,
shareable availability. Account privacy and the wider edge-case checklist are
verified during development; the presentation does not need to walk through
every test or screen. If rehearsal runs long, shorten the explanation while
preserving the input-to-availability journey.

### Agreed scheduling behavior

- Working windows repeat weekly, allow multiple windows per weekday, and can
  continue overnight. A day without its own working window offers no work
  availability unless an overnight window from the previous day continues into
  it. With no configured working windows at all, availability is empty.
- Weekly recurrence uses selected weekdays, a start date, an optional end date,
  and fixed start/end times. The database review revises the earlier
  whole-series-only editing scope: earlier weeks retain their schedule, changes
  can take effect from a chosen date for future weeks, and one-off occurrence
  changes and cancellations are required. Explicit one-off reschedules survive
  later changes to the regular hours. An all-future edit affects every selected
  weekday. Ending a series stops occurrences, including one-off replacements,
  whose original start date is on/after the cutoff. Past one-time entries can
  still be explicitly corrected or deleted; an immutable audit log is not required.
- Work availability is one personal pool shared across employers. Retired
  sources must preserve past and future commitments through archiving. Already
  scheduled shifts keep blocking time until cancelled or their series is ended.
- Recurring schedules and working windows need effective dates to preserve
  earlier weeks. Date-specific working availability replaces the entire local
  date, including overnight carry-in. An override with no intervals makes that
  date unavailable for work.
- Commitment entry includes explicit start and end dates and an easy
  "ends next day" option. For weekly recurrence, the selected weekday identifies
  when an occurrence starts. A final Sunday occurrence may finish Monday after
  the series end date; its full duration still blocks time.
- A proposed shift is available only if its entire duration fits within working
  windows and it overlaps no commitments. Checking a shift does not save it.
- Shift checks distinguish commitment conflicts from time outside working windows.
- Touching interval boundaries do not conflict. Travel time is not yet included.
- The first version uses America/Halifax time, with displayed weeks running
  Monday through Sunday. Daylight-saving handling is automatic: missing times
  shift forward by the transition gap, and repeated times use the first
  occurrence. Show the chosen result and allow a date-specific override. Only
  invalid resolved intervals require review. Store policies with schedule
  revisions to preserve earlier behavior. The current one-time forms still
  reject these inputs until the new resolver is implemented. Adaptive time zones
  remain a future improvement. See [the database design](database_design.md).
- Overnight commitments must block time on both affected dates, including when
  they cross a displayed week boundary. This applies to one-time commitments
  as well as recurring commitments. A one-time Sunday 22:00–Monday 06:00 shift
  must appear in both weekly views and block Monday morning availability.
- Users can save overlapping commitments after an explicit warning. Conflicts
  remain visible so the saved schedule can represent an existing real conflict.
- Availability includes all positive-length gaps inside working windows; it does
  not claim that a gap is long enough for an employer to offer a shift.

### Agreed frontend direction

The user requested Impeccable guidance for the whole application, covering every
existing template. Shared navigation, typography, controls, forms, feedback,
and responsive patterns are documented in [frontend_style.md](frontend_style.md).
The current pass retains the green identity and uses self-hosted Instrument Sans.

The weekly calendar supports previous/next navigation and opening a commitment
form by clicking a day. Stable colors distinguish commitment sources such as
classes, Job A, Job B, and personal time; labels accompany those colors.
Include subtle, smooth animations that respect the device's reduced-motion
preference. Drag-to-create and drag-to-reschedule interactions are deferred
from the first version.

### Learning and delivery approach

The developer has Django/backend experience and wants to learn frontend work.
They have used HTML/CSS and JavaScript, but have not built a React application.
The project is developed individually.

Start with Django templates, Bootstrap, and focused JavaScript. Make the weekly
view and entry workflow usable while learning layout, interactions, and frontend
feedback. A separate React frontend is not part of the agreed first version.

The user chose the latest stable Django release. AGENTS.md records the verified
version and remains the source for the technology stack. Django's
[official download page](https://www.djangoproject.com/download/) and
[Python compatibility table](https://docs.djangoproject.com/en/6.1/faq/install/)
were checked on 2026-10-25 and rechecked during initial setup. Installed
dependency versions are recorded in `uv.lock`.

Scheduling logic belongs in service modules; external integrations remain
separate from that logic.

Standalone commitment and availability REST APIs are deferred until after the
class demonstration. Initial Django pages call scheduling services directly.
Later APIs must use Django REST Framework and can reuse those services.

## Agreed follow-up direction

Reduce the effort needed to maintain a schedule, aiming for entry that feels
as straightforward as writing on a calendar or paper.

The first enhancement after the core demonstration is speech/natural-language
entry: interpret a request into a draft commitment that the user confirms before
saving. Scheduling services, rather than the LLM, calculate conflicts and
availability. The speech provider, model, cost, and access mechanism have not
been selected. Spoken answers may follow if useful.

Google Calendar integration is deferred from the first version. Import versus
synchronization behavior still needs design.

Adaptive time-zone support is also a future improvement. The first version's
display zone is Halifax. Changing a display zone in the future must preserve
the original commitment schedule. Availability is recalculated from the current
schedule on request; copies previously shared with employers are not stored in
this version.

## Remaining external facts

- The exact presentation date and course-specific rubric remain unverified.
  The local syllabus is [grad_seminar_syllabus.pdf](grad_seminar_syllabus.pdf),
  but its contents have not been extracted. No course requirement is inferred
  from the filename or from another course's chat.

## Unconfirmed backlog from the initial checklist

These are ideas retained from the initial document, not commitments for the
first demonstration or the next increment:

- CSV import/export and XML import/export.
- Employer-specific work rules and preferences.
- Travel buffers and minimum work durations beyond agreed availability rules.
- Hosting/deployment, including Azure.
- Statistics, dashboards, and notifications.

## Verification plan

Once behavior is agreed, test the scheduling services with concrete examples
covering recurrence, overlapping commitments, and availability subtraction.
Include touching boundaries, overnight commitments, and overnight commitments
crossing the displayed week boundary, for both one-time and recurring entries.
Include the last overnight occurrence of a series, the confirmed daylight-saving
policy and positive elapsed intervals, all positive-length available gaps, and warning before saving
a conflicting commitment. A proposed-shift check must verify both working-window
coverage and conflicts without saving the shift.
Verify account privacy and the visual demonstration journey. The user accepted
the original acceptance scenarios below; additional edge cases are derived from
the agreed rules. These are expected outcomes, not completed test results.

### Agreed first-version acceptance scenarios

| Scenario | Expected behavior |
| --- | --- |
| Monday working window 08:00–20:00; class 10:00–12:00; study 12:00–14:00 | Availability is 08:00–10:00 and 14:00–20:00. |
| Check Monday 09:00–11:00 | Reports a class conflict and leaves the saved schedule unchanged. |
| Check Monday 20:00–22:00 | Reports time outside working windows and leaves the saved schedule unchanged. |
| One-time Sunday 22:00–Monday 06:00 commitment | Both weekly views show the affected portion; Monday availability excludes 00:00–06:00. |
| Weekly Sunday overnight series ends on a Sunday | Its final occurrence still finishes on Monday and blocks that time. |
| A commitment ends exactly as another starts | No overlap is reported. |
| Save an overlapping commitment | An explicit warning precedes saving; the saved conflict stays visible. |
| Copy availability for an employer | Copies available intervals without private commitment titles. |
| Sign in as a second user | The first user's commitments and availability remain private. |

### Additional checks derived from agreed behavior

| Scenario | Expected behavior |
| --- | --- |
| No working windows configured | Availability is empty. |
| Monday windows 08:00–12:00 and 16:00–20:00, with no commitments | Both intervals appear; 12:00–16:00 is not offered. |
| Friday working window 22:00–Saturday 06:00; commitment Saturday 01:00–03:00 | Availability is Friday 22:00–Saturday 01:00 and Saturday 03:00–06:00, presented on the affected dates. |
| A working window continues into a day with no separately configured window | The continuing portion is still eligible for availability calculation. |
| Two commitments overlap within a working window | Availability excludes their combined occupied time without duplicate available intervals. |
| A 30-minute available interval remains | It is displayed without claiming to meet an employer's minimum shift length. |
| Check a shift entirely within a working window and without conflicts | Reports available and leaves the saved schedule unchanged. |
| A Halifax time is missing or repeated at a daylight-saving transition | Shift missing times forward by the gap; choose the first repeated time. Show the resolution and allow an override. If the resulting interval is invalid, request review. |
| Navigate weeks and click a day | The displayed week changes and the entry form uses the selected date. |
| Two commitments have the same source | They use the same source color and readable labels. |
| Device requests reduced motion | Animation respects that preference. |
