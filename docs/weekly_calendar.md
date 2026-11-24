# Weekly calendar

Open `/week/` after signing in, or choose **Your week** in the navigation.
The homepage also links to it. `?week=2026-10-26` selects a week; any valid date
normalizes to its Monday. Previous/next and This week links work without JavaScript.
The display zone is America/Halifax.

The calendar shares the application's navigation, typography, and controls with
all other pages. See [frontend_style.md](frontend_style.md) for the app-wide
Impeccable-guided style pass.

## What is implemented

- A compact Monday–Sunday **Week board** by default, with stable source colors,
  explicit times, wrapping titles, and daily commitment counts. Commitments stack
  in time order; empty hours occupy no space and cards have no internal scroll.
- A **Time grid** option (`?view=timeline`) retains proportional duration and
  hourly comparisons. Switching layouts preserves the selected week, and
  previous/next/This week navigation preserves the selected layout.
- The board uses dated rows with two commitment columns at tablet/narrow desktop
  widths, and a single-column daily agenda on phones. The optional time grid
  scrolls inside its frame on desktop/tablets and uses a daily agenda on phones.
- A weekly commitment/overlap summary and direct work-availability link. Short,
  overlapping commitments remain full-width in the board; the time grid retains
  side-by-side lanes. Dense weeks still take vertical space rather than hiding
  commitments behind a fixed-height calendar.
- One-time commitments, regular recurring occurrences, and moved replacements.
  Cancellations and ended-series occurrences follow the recurrence service.
- Overnight portions on both dates and in both displayed weeks when applicable.
- Side-by-side lanes and overlap indicators for visible commitments, including
  one-time/recurring overlaps. Touching endpoints are not conflicts.
- Select a day to prefill a one-time entry with that date. Saving or cancelling
  returns to the selected week. Existing edit links also preserve that week.
- Select a commitment to open full details, including an edit link for one-time
  entries. Details use native HTML popovers, with Escape/outside dismissal.
- Visible automatic DST choices and a review notice when an interval is invalid.
- Reduced-motion support, keyboard links/buttons, labelled calendar sections,
  and a skip-to-content link.

Calendar details now link to reviewed recurring editing and one-off changes,
and review notices link to correction/cancellation. See
[recurring_workflow.md](recurring_workflow.md). The one-time save warning checks both one-time and recurring
commitments; see [conflict_services.md](conflict_services.md). The calendar's read-only
overlap indicators include recurring commitments too. This calendar does not
calculate work availability or describe empty space as available for work.
Working-window [configuration screens](working_window_screens.md) are implemented.
The [availability screen](availability_screen.md) now provides visual available
hours and employer-facing copy text; its calendar link preserves the selected
week. It uses the [availability calculation backend](availability_services.md).

## How the frontend fits Django

`scheduling/calendar.py` is the presentation service. It combines an owner-filtered
one-time query with `occurrences_for_user`, marks visible overlaps, clips actual
intervals into daily portions, and allocates lanes. Views only parse the request,
call the service, and render `templates/scheduling/week.html`. Domain writes
continue through the existing commitment service and form.

Actual UTC elapsed minutes determine block placement within each local date.
Day boundaries are resolved separately, so the fall-back Sunday has 25 hours
and the spring-forward Sunday has 23. Each column has its own local-clock labels;
the repeated hour appears twice. Displayed endpoints include ADT/AST to distinguish
ambiguous labels in details; compact blocks omit repeated zone labels when both
endpoints use the same zone. Invalid resolved intervals appear as review issues instead of
being presented as an empty, complete day.

CSS switches the same semantic day/block markup between the compact board,
optional desktop timeline, and phone agenda. The view only selects a known
layout from the query string; scheduling calculations remain in the presentation
service. Unknown layout values fall back to the board. Hour labels are rendered
only for the time grid. The small `static/js/calendar.js` script only scrolls
that optional desktop timeline toward the earliest commitment, with a daytime
default. Entry, navigation, details, layout selection, and all schedule content
work without it. No React, Node build, new application dependency, or migration
was introduced. Edit/create return links retain the week and return to the
default board.

The [calendar research](weekly_calendar_research.md) compares this approach with
FullCalendar and Django date-picker widgets. A new library is unnecessary for
removing empty-hour rows; this change retains the existing recurrence, overnight,
conflict, ownership, and clock-change behavior.

The browser-created temporary sample account and all its records are removed
after verification. Screenshots contain fictional sample data rather than a
user's private schedule.

## Verification

### Compact board polish (22 November 2026)

- 91 PostgreSQL tests pass across weekly calendar, one-time views, and recurring
  workflows. Four additional calendar tests cover the default board without hour
  rows, optional grid/navigation, unknown layout fallback, and short/conflicting/
  overnight commitments.
- Chromium checks passed at 1440, 1280, 1024, 820, 390, and 320px widths with no
  page overflow or scrolling inside board cards. At 1440 × 1000, the demo week's
  13 commitments fit together in the viewport (board height about 540px).
- Details, Escape dismissal, recurring edit links, layout switching, previous/
  next week, selected-date form prefill, and no-JavaScript layout/details passed.
- Desktop, tablet, and phone captures were visually inspected. Browser tooling
  and screenshots stay under `/tmp`; no project browser dependency was added.
- Empty weeks, clock-review notices, 23/25-hour dates, long unbroken labels, and
  reduced-motion rendering passed browser checks. Checked board labels and
  colored-card text had a minimum computed contrast ratio of 5.38:1.
- The Impeccable scan reported only a font warning for the established Instrument
  Sans family, which was retained to match the application.

### Original calendar implementation

- 189 PostgreSQL tests pass, including 19 new calendar tests for ownership,
  malformed dates, recurrence, overnight boundaries, overlap lanes, DST,
  source archival, escaping, form prefill, and safe return navigation.
- Chromium checked at 1440px desktop, 390px phone, and 820px tablet widths.
- Browser flow: login, open the week, choose a date, save a commitment, return
  to that week, open details, and navigate previous/next.
- Browser checks also cover overnight carry-in, a 25-hour day, overlap display,
  reduced motion, no page overflow, and navigation/details with JavaScript disabled.

See the [development checklist](development_checklist.md) for the remaining backend
and frontend increments, and the [recurrence guide](recurrence_services.md) for
the rules behind generated occurrences.
