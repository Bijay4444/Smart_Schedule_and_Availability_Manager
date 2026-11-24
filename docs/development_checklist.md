# Incremental development checklist

The [project specification](project_spec.md) defines behavior. This checklist
tracks implementation and evidence. Finish a usable increment and its tests
before marking it complete. The local three-minute demonstration remains the
first delivery target.

## 1. Project and authentication — complete

- [x] Python 3.13, Django, PostgreSQL driver, and locked dependencies.
- [x] Local PostgreSQL database and initial migrations.
- [x] Standard-session login, POST logout, and protected home page.
- [x] Extensible user model and admin.
- [x] Nine authentication tests pass on SQLite and PostgreSQL.

## 2. One-time commitment workflow — complete

- [x] User-owned commitment sources with a name and stable color.
- [x] One-time commitments with explicit start/end dates and overnight support.
- [x] Database constraints and helpful form validation for invalid intervals.
- [x] Source creation and a private, color-coded commitment list.
- [x] Commitment creation, editing, and deletion with confirmation.
- [x] Overlap service with strict boundaries and explicit conflicting-save warning.
- [x] Ownership checks on lists, forms, services, and individual object routes.
- [x] Read-only admin inspection; commitment changes use the warning workflow.
- [x] Tests for overnight entries, DST input, conflicts, CRUD, and isolation.
- [x] PostgreSQL migration applied; auth and scheduling tests pass.

Completion: a signed-in user can create a source and manage their one-time
commitments at `/commitments/`, including an overnight shift, without accessing
another user's records. This is a list/form increment; it is not yet the weekly
calendar or availability generator.

Verification: 60 tests passed on SQLite and PostgreSQL. The live HTTP journey
also passed: login, source creation, overnight commitment creation, overlap
warning/confirmation, editing, deletion, and logout. Its temporary account and
records were removed. The local server was restarted with automatic reload.

Implementation notes:

- Ownership follows `User → CommitmentSource → Commitment`; the commitment
  table does not duplicate the source's owner. Querysets and source choices
  are restricted to the signed-in user, with a further ownership check in the
  write service.
- `scheduling/services.py` owns overlap checks and confirmed saves. The overlap
  rule is `existing.starts_at < candidate.ends_at` and
  `existing.ends_at > candidate.starts_at`, so touching endpoints are allowed.
- Confirmed overlapping commitments keep a warning badge on both list entries.
- Model validation and a database check both require a positive interval.
  Aware instants are compared in UTC so the repeated fall-back hour is handled
  by actual elapsed time. Forms reject ambiguous/nonexistent local clock inputs;
  explicit DST-resolution controls remain part of the time/recurrence work.
- Scheduling admin pages are read-only to preserve the application warning
  workflow. Superusers have the usual privileged inspection access; other
  staff see only their own records when granted view permission.

See Django's [time-zone documentation](https://docs.djangoproject.com/en/6.1/topics/i18n/timezones/)
for the distinction between stored instants and local form/display times.

## 3. Weekly recurrence

Database design was confirmed in DB18. The storage foundation and recurring
services, recurring conflict review, and recurring entry/editing forms are complete.

- [x] Source archival state and protected references preserve existing data.
- [x] Recurring series, dated revisions, weekdays, and exception tables.
- [x] PostgreSQL revision exclusion, payload checks, and migration-preservation tests.
- [x] Apply migrations locally and compare existing records before/after.
- [ ] User-facing source archive controls (archive service is implemented).
- [x] Atomic recurring creation with first revision and selected weekdays.
- [x] Selected weekdays, local clocks, start date, optional inclusive end (service).
- [x] Occurrence expansion service for a bounded date range.
- [x] Include previous-day overnight occurrences and week-boundary overlaps.
- [x] Final occurrence may finish after the recurrence end date.
- [x] Future-effective schedule changes preserve earlier weeks.
- [x] Support one-off reschedules and cancellations; explicit one-off changes
  survive general future-effective schedule changes.
- [x] One-time save warnings and persistent list indicators include both
  one-time and recurring commitments, with explicit acknowledgement of conflicts
  or unresolved recurring clock-review dates.
- [x] Conflict preflight for recurring creation, future edits, and replacements
  before exposing their write forms.
- [x] Tests for date limits, touching boundaries, DST, and recurring overnight shifts.
- [x] Automatic daylight-saving resolution with metadata and review issues;
  shift missing times forward and choose the first repeated time.
- [x] Recurring create/edit/end and one-off change forms with ownership checks.
- [x] Display DST resolution and review messages with one-off override controls.
- [x] An easy "ends the following day" option for recurring rules.
- [ ] An easy "ends next day" option on the one-time entry form (explicit dates work).

Foundation verification: 103 tests passed on PostgreSQL, including a migration
from the legacy schema and competing revision inserts on separate connections.
The local application database has migrations 0002/0003 applied; comparison of
legacy users, sources, and commitments before/after found no changes. Django's
system check and migration-drift check pass. The live HTTP journey passed login,
overnight CRUD, conflict warning/confirmation, archived-source choices and
correction, and logout; its temporary records were removed. A private database
backup was taken before migration.

Recurring-service increment verification: 170 PostgreSQL tests passed at that stage.
New coverage includes the agreed overnight/DST/history/exception scenarios,
failure rollback after closing a revision, simultaneous future edits and
duplicate cancellations, private reads/writes, non-hour clock changes, skipped
dates, and bounded query counts. No migration or new dependency was needed.
See [recurrence_services.md](recurrence_services.md) for interfaces, design
reasoning, and the remaining conflict/frontend integration boundary.

One-time conflict integration now reuses generated occurrences, including
archived sources, revisions, and moved/cancelled exceptions. Long candidates
are checked in bounded chunks. List checks batch nearby intervals and retain
incomplete-review indicators. A common owner lock serializes one-time,
recurring, and working-schedule writes, preventing simultaneous one-time saves
from both missing a conflict. No new migration or dependency was added.
See [conflict_services.md](conflict_services.md) for the implementation,
tests, and remaining recurring-write preflight boundary.

Conflict-integration verification: all 291 PostgreSQL tests pass, including 30
new tests. Django's system check, migration-drift check, and whitespace check
pass. HTTP tests verify recurring warning/confirmation, rejected edits, retained
badges/review notices, and privacy. Separate-connection tests verify competing
one-time saves and the common lock with uncommitted recurring creation. The
temporary test cluster was stopped after verification; application data remains
unchanged.

Recurring workflow now adds a signed review before creation, future edits, or
one-off replacement saves. The user confirmed a visible 12-month preview for
open-ended series; final included overnight occurrences retain their full
duration. Matching reviews are recalculated under the owner lock; staged changes
roll back on review. Calendar details/review notices link to occurrence changes
and cancellation. See [recurring_workflow.md](recurring_workflow.md) for the
interfaces, token freshness, history preservation, and frontend journey.

Recurring-workflow verification: all 333 tests pass on isolated PostgreSQL,
including 42 new tests. System, migration-drift, and whitespace checks pass.
Chromium passed the full recurring create/review/save, future-edit, one-off
reschedule/cancel, end, and selected-week return flow. Desktop, tablet, phone,
and narrow-phone captures passed overflow checks; desktop/phone review captures
were inspected. Repeated overlap warnings group their dates without losing
the complete signed result. The application database and existing data remain
unchanged. Temporary browser tooling and libraries are outside the repository.

## 4. Working windows and availability — backend and configuration screens complete

- [x] Weekly working windows, multiple per weekday, and overnight windows.
- [x] Effective dates preserve earlier working windows; support date-specific
  working availability replacing the entire local date, including overnight carry-in.
- [x] Merge occupied intervals and subtract them from working windows.
- [x] No windows means no availability; retain all positive-length gaps.
- [x] Proposed-shift service checks both window coverage and conflicts without saving.
- [x] Tests cover the acceptance examples in the project specification.
- [x] Weekly working-window configuration with multiple/overnight rows and effective dates.
- [x] Full-date override creation/editing, explicit all-day closure, and confirmed restoration.
- [x] Private dated window preview, DST choices/review links, and history display.
- [x] Add/remove rows, including adding and saving without JavaScript.

The backend adds working revisions/windows and full-date overrides in migration
0004. Reads include recurring exceptions and archived-source commitments.
Invalid DST intervals withhold affected dates and expose review metadata;
working overrides can resolve working-rule issues. Concurrent writes serialize
on the owner row, with PostgreSQL revision exclusions as additional protection.
See [availability_services.md](availability_services.md) for interfaces,
calculation reasoning, and verification. Working-window forms and availability
display/sharing are implemented. Migration 0004 was tested in temporary
PostgreSQL, and the user subsequently reported applying the application migration.

Verification: all 261 tests pass on isolated PostgreSQL 18, including 72 new
working-availability/schema/migration tests and the previous 189 tests. Django's
system check, migration-drift check, and whitespace check pass. The application
database was not changed, and no new dependency was added.

Working-screen verification: all 383 PostgreSQL tests pass, including 50 new
screen/service tests. System, migration-drift, and whitespace checks pass.
Chromium passed multi-window/overnight entry, dynamic row addition/removal,
future-effective editing/history, date closure/edit/restoration, DST second-hour
choices, invalid clock input, and no-JavaScript add/save. Desktop, tablet, phone,
and narrow-phone layouts passed overflow checks; desktop/phone captures were
inspected. No dependency, migration, or application-data change was added.
See [working_window_screens.md](working_window_screens.md) for the implementation
and the existing migration requirement.

## 5. Weekly frontend and sharing

- [x] Monday–Sunday visual calendar with previous/next and Today navigation.
- [x] Stable source colors and labels; overnight portions on both affected dates.
- [x] Click a day to open an entry form with that date; return to the selected week.
- [x] Full commitment details with one-time editing from the calendar.
- [x] Calendar indicators for visible one-time and recurring overlaps.
- [x] Show DST choices and unresolved interval review issues.
- [x] Display work availability and copy employer-facing text without private details.
- [x] Explicit incomplete/draft text, clipboard-denial fallback, and selectable text without JavaScript.
- [x] Read-only proposed-shift screen, separate conflicts/outside-window results,
  unresolved-date review links, overnight intervals, and explicit DST choices.
- [x] Phone agenda layout, date validation, and reduced-motion support.
- [x] Subtle calendar entrance and hover transitions respecting reduced motion.
- [x] Install Impeccable and apply shared styling to every existing app template:
  navigation, typography, icons, controls, forms, lists, and confirmation/error states.

Weekly-frontend verification: 189 tests pass on PostgreSQL. Chromium checks
passed desktop (1440px), phone (390px), and tablet (820px), including date-to-form
entry/save, week return/navigation, full details, overnight/DST, overlaps, and
JavaScript-disabled navigation/details. Temporary browser tooling and library
copies stayed under `/tmp`; no application dependency or migration was added.
The sample account and all its records were removed. See
[weekly_calendar.md](weekly_calendar.md) for architecture and remaining boundaries.

App-wide style verification: all existing templates were captured before/after
on desktop and phone, with tablet and narrow-phone checks. Browser workflows
covered entry/edit/delete, overlap confirmation, validation, popovers, and
JavaScript-disabled calendar navigation. Text contrast and local-font loading
were checked in the browser. Impeccable's source scan had incomplete CSS coverage
because of Django static tags; see [frontend_style.md](frontend_style.md) for the
installation, shared patterns, and evidence.

Availability-screen verification: all 411 PostgreSQL tests pass, including 28
new presentation/HTTP tests. System, migration-drift, and whitespace checks pass.
Chromium passed actual clipboard copy, missing/denied clipboard fallback,
private-detail-free text, week/calendar links, refresh after schedule changes,
incomplete/draft text, DST repeated-hour labels, empty weeks, and no-JavaScript
navigation/text. Desktop, tablet, phone, and narrow-phone overflow checks passed;
rendered desktop/phone/review-state captures were inspected. No dependency or
migration was added. See [availability_screen.md](availability_screen.md).

Proposed-shift screen verification: all 451 PostgreSQL tests pass, including 40
new form/presentation/HTTP tests. System, migration-drift, and whitespace checks
pass. Chromium checks cover available shifts, conflicts and uncovered hours,
unresolved dates, clock choices, correction/clear, navigation, refreshed checks,
and JavaScript-disabled forms at desktop, tablet, phone, and narrow-phone sizes.
No dependency, migration, or application-data change was added. See
[proposed_shift_screen.md](proposed_shift_screen.md).

## 6. Demo readiness

- [x] Prepared sample accounts, sources, working windows, and commitments.
- [x] Include classes, two employers, protected personal time, and an overnight shift.
- [ ] Verify privacy and the full accepted service-test checklist.
- [ ] Verify the running PostgreSQL-backed app through its main user journey.
- [ ] Rehearse the three-minute walkthrough and reserve time for transitions.

Demo-seed verification: all 479 PostgreSQL tests pass, including 28 new seed
tests. The command creates four ordinary demo accounts with main, private,
empty, and DST/review scenarios. Tests check expected availability/conflicts,
exceptions, future history, overnight boundaries, scope of reset, unchanged
reruns, preserved manual passwords/data, username collisions, and rollback.
Chromium passed all four logins, current/future calendars, the phone calendar,
share text/short gaps, working-window pages, four proposed shifts, and separate
private/empty/DST states. No new dependencies or migrations were added.
The command was also run against the configured application database, loading
the 16–22 November 2026 demo set while preserving other accounts. The final
presentation rehearsal and its full live workflow remain separate work. See
[demo_data.md](demo_data.md) for the feature-by-feature manual walkthrough.

REST APIs, voice/LLM entry, Google Calendar integration, adaptive time zones,
and public hosting remain follow-up work.

## Database design review — complete

The user requested a requirements and schema review before further development.
Existing completed increments remain available; the review may identify schema
changes to make through data-preserving migrations.

- [x] Document the current schema and identify implementation assumptions.
- [x] Confirm shared availability, source preservation, future-effective edits,
  one-off anomalies, and stable schedules across display-timezone changes.
- [x] Confirm live availability without saved reports, preserved explicit
  exceptions, single-occurrence cancellation, date-specific working availability,
  and archive behavior that retains existing future commitments.
- [x] Draft an ER diagram and field catalog.
- [x] Confirm full-date override precedence, all-weekday future edits, explicit
  series-ending behavior, and correction/deletion of past one-time entries.
- [x] Settle automatic daylight-saving defaults for missing and repeated times.
- [x] Settle product requirements affecting ownership, recurrence, working
  windows, time zones, history, and source retirement.
- [x] Review the proposed ER diagram, fields, relationships, and constraints.
- [x] Walk through concrete scheduling, archival, exception, timezone, and
  privacy scenarios in the design; future implementation tests remain pending.
- [x] Confirm shared understanding and a data-preserving migration plan (DB18).

See [database_design.md](database_design.md) for the interview and design record.
