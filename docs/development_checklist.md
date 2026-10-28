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
services are complete; conflict integration and the frontend remain in progress.

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
- [ ] Conflict checks include one-time and recurring commitments.
- [x] Tests for date limits, touching boundaries, DST, and recurring overnight shifts.
- [x] Automatic daylight-saving resolution with metadata and review issues;
  shift missing times forward and choose the first repeated time.
- [ ] Recurring create/edit/end and one-off change forms with ownership checks.
- [ ] Display DST resolution and review messages with one-off override controls.
- [ ] An easy "ends next day" entry option.

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

## 4. Working windows and availability

- [ ] Weekly working windows, multiple per weekday, and overnight windows.
- [ ] Effective dates preserve earlier working windows; support date-specific
  working availability replacing the entire local date, including overnight carry-in.
- [ ] Merge occupied intervals and subtract them from working windows.
- [ ] No windows means no availability; retain all positive-length gaps.
- [ ] Proposed-shift service checks both window coverage and conflicts without saving.
- [ ] Tests cover the acceptance examples in the project specification.

## 5. Weekly frontend and sharing

- [x] Monday–Sunday visual calendar with previous/next and Today navigation.
- [x] Stable source colors and labels; overnight portions on both affected dates.
- [x] Click a day to open an entry form with that date; return to the selected week.
- [x] Full commitment details with one-time editing from the calendar.
- [x] Calendar indicators for visible one-time and recurring overlaps.
- [x] Show DST choices and unresolved interval review issues.
- [ ] Display work availability and copy employer-facing text without private details.
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

## 6. Demo readiness

- [ ] Prepared sample accounts, sources, working windows, and commitments.
- [ ] Include classes, two employers, protected personal time, and an overnight shift.
- [ ] Verify privacy and the full accepted service-test checklist.
- [ ] Verify the running PostgreSQL-backed app through its main user journey.
- [ ] Rehearse the three-minute walkthrough and reserve time for transitions.

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
