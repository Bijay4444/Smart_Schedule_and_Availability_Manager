# Weekly calendar presentation research

Researched 2026-11-22. Documentation only; no UI, dependency, or scheduling
behavior changes. Sources below are official project documentation or repositories.

## Recommendation

Use a **compact native week overview by default**, with commitments stacked in
Monday–Sunday day columns on desktop and a daily agenda on phones. Offer the
existing proportional hourly view as an explicit **Timeline** option. This is a
design recommendation, not a measured usability result.

The current problem is the presentation of empty hours, rather than missing
calendar calculations. The existing stylesheet allocates `0.9px` per minute:
a normal 24-hour day uses 1,296px before padding, inside a shorter scrolling
viewport. Auto-scrolling changes the initial position without reducing that
height. The phone stylesheet already renders the same commitments as cards
without empty-hour rows. See [the current CSS](../static/css/app.css),
[calendar script](../static/js/calendar.js), and [calendar guide](weekly_calendar.md).

This approach adds no dependencies, keeps the existing Django presentation
service, and directly addresses the reported scrolling. A compact layout loses
proportional gap/duration comparison, which is why retaining the optional
timeline matters. Busy weeks will still need vertical space; no design should
hide commitments to promise a fixed-height week.

## Options compared

| Option | Effect on scrolling and readability | Fit here |
| --- | --- | --- |
| Native compact week / daily agenda | Cards use content height; empty hours take no space. Times must be explicit because card position no longer indicates clock time. | Recommended first change; reuse the existing daily portions, labels, conflict flags, and details. |
| FullCalendar `dayGridWeek` | Day cells replace the vertical time axis; closer to a compact week overview. Duration and gaps are less apparent. | Best library option if a reusable calendar UI is desired. [DayGrid docs](https://fullcalendar.io/docs/daygrid-view). |
| FullCalendar `listWeek` | A vertical commitment list for the week; eliminates empty-hour rows but a busy week remains long. | Useful agenda option, especially on phones; less effective for comparing seven days side by side. [List docs](https://fullcalendar.io/docs/list-view). |
| FullCalendar `timeGridWeek` | Days remain side by side against a vertical time axis. Switching libraries alone therefore retains the current scrolling tradeoff. | Useful optional timeline, rather than the solution to this complaint. [TimeGrid docs](https://fullcalendar.io/docs/timegrid-view). |
| Django form date-picker package | Improves choosing a date/time inside a form; does not display a person's week of commitments. | Does not solve this request. See package distinctions below. |

FullCalendar supports bounded displayed hours through `slotMinTime` and
`slotMaxTime`; these determine actual visible limits. `scrollTime` only chooses
the initial scroll position. A fixed daytime range could exclude this project's
overnight shifts, so any such implementation would need a visible way to reveal
all hours and must never silently conceal a commitment. [Minimum time](https://fullcalendar.io/docs/slotMinTime),
[maximum time](https://fullcalendar.io/docs/slotMaxTime), and
[initial scroll](https://fullcalendar.io/docs/scrollTime).

## FullCalendar dependencies, assets, and licensing

The official documentation currently identifies **v7.1.5**, released November
12, 2026. Its vanilla JavaScript integration works through script tags and a
downloadable ZIP, so Django templates can use locally hosted assets without
React or a Node build. The v7 global example includes the standard JS bundle,
theme JS, skeleton CSS, theme CSS, and palette CSS. Pin a version and place the
required files under Django static assets instead of relying on a CDN during a
local demonstration. Older v6 snippets use different paths and asset conventions.
[Vanilla integration](https://fullcalendar.io/docs/vanilla-js),
[v7 migration guide](https://fullcalendar.io/docs/upgrading-from-v6).

The standard bundle includes DayGrid, TimeGrid, List, interaction, and MultiMonth.
Standard is MIT licensed, including commercial use, with copyright headers
retained. FullCalendar's horizontal resource **Timeline** view is Premium and
has separate licensing; it is unnecessary for a personal weekly calendar.
Here, “Timeline” can simply name this project's existing vertical hourly view.
[Plugin index](https://fullcalendar.io/docs/plugin-index),
[license](https://fullcalendar.io/license),
[Premium features](https://fullcalendar.io/docs/premium).

A library integration would still require project code for source labels,
conflict/review metadata, entry and edit links, details, responsive view choice,
and a server-rendered fallback. Keep recurrence, overlap detection, ownership,
and availability calculations in existing services; pass resolved dated
occurrences to the renderer. Do not duplicate recurrence rules in browser code.
Use `America/Halifax` explicitly: FullCalendar defaults to the browser's zone,
while its current named-zone support provides consistent display across browsers.
Its date callbacks need careful interpretation because native `Date` objects
do not acquire the calendar's named zone. [Time-zone documentation](https://fullcalendar.io/docs/timeZone).

## What “Django calendar widget” means

Django defines a widget as the HTML rendering and submitted-value extraction
for a form input. This differs from a weekly schedule renderer.
[Django widget documentation](https://docs.djangoproject.com/en/6.0/ref/forms/widgets/).

- **django-flatpickr** supplies date, time, datetime, and range input widgets.
  It could improve commitment forms separately, but adds a Python wrapper and
  browser picker assets without replacing `/week/`.
  [Official repository](https://github.com/monim67/django-flatpickr).
- **django-bootstrap-datepicker-plus** likewise targets form inputs. Its setup
  requires jQuery, Bootstrap assets, and form media, adding machinery unrelated
  to this calendar presentation issue.
  [Official getting-started guide](https://django-bootstrap-datepicker-plus.readthedocs.io/en/latest/Getting_Started.html).
- **django-scheduler** is a full calendaring application with recurring events,
  exceptions, APIs, and calendar views. Its bundled FullCalendar view uses
  FullCalendar 6 and CDN assets. Adopting it would overlap the project's existing
  scheduling domain and require integration work beyond a display change; using
  FullCalendar directly would be the narrower library choice.
  [Official repository](https://github.com/llazzaro/django-scheduler).

These sources establish package purpose, not verified compatibility with this
repository's exact Django/Python versions. No package was installed or tested.

## Requirements for a later implementation

Retain previous/next/Today navigation, clickable dates, source colors plus text,
explicit times, accessible details, recurring editing links, overnight
continuations, and visible conflicts/review notices. Preserve Halifax zone
labels and distinguish repeated-hour endpoints. Keep empty days visible and
label them “No commitments”; empty space must not be described as work
availability. These requirements come from the [project spec](project_spec.md),
[glossary](../GLOSSARY.md), and [existing calendar contract](weekly_calendar.md).

A future change should verify sparse and busy weeks, short/overlapping blocks,
overnight carry-in across weeks, 23/25-hour days, review issues, keyboard/details
flows, no-JavaScript navigation, and desktop/tablet/phone widths. This research
does not establish that any replacement library reproduces the existing DST
timeline semantics; that needs a focused prototype and regression checks.
