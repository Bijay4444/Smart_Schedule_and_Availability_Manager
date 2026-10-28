# Weekly calendar

Open `/week/` after signing in, or choose **Your week** in the navigation.
The homepage also links to it. `?week=2026-10-26` selects a week; any valid date
normalizes to its Monday. Previous/next and Today links work without JavaScript.
The display zone is America/Halifax.

The calendar shares the application's navigation, typography, and controls with
all other pages. See [frontend_style.md](frontend_style.md) for the app-wide
Impeccable-guided style pass.

## What is implemented

- Monday–Sunday desktop time grid with stable source colors and text labels.
- A stacked daily agenda on phones; tablets can scroll the grid horizontally
  inside its frame without overflowing the whole page.
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

Recurring editing forms and conflict-save integration remain separate work.
The existing save warning checks one-time commitments; the calendar's read-only
overlap indicators include recurring commitments too. This calendar does not
calculate work availability or describe empty space as available for work.
Working windows, availability calculation, and sharing remain on the checklist.

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

CSS switches the same semantic day/block markup between the desktop timeline
and phone agenda. The small `static/js/calendar.js` script only scrolls the
desktop viewport toward the earliest commitment, with a daytime default. Entry,
navigation, details, and all schedule content work without it. No React, Node
build, new application dependency, or migration was introduced.

The browser-created temporary sample account and all its records are removed
after verification. Screenshots contain fictional sample data rather than a
user's private schedule.

## Verification

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
