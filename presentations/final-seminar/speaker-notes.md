# Smart Schedule — final six-minute seminar

Ten slides, a target finish of **5:50**, and a ten-second buffer. This is a
speaker-led recap and progress report. The HTML deck contains the same script
in its private presenter view. Screenshots provide an offline fallback; a live
app walkthrough is optional, not required to finish within six minutes.

| Slide | Speaking window | Topic |
| --- | --- | --- |
| 1 | 0:00–0:20 | From a calendar to a deployed product |
| 2 | 0:20–0:55 | Brief recap of the earlier report |
| 3 | 0:55–1:35 | Complete recurring scheduling workflows |
| 4 | 1:35–2:20 | Working windows, calculated availability and sharing |
| 5 | 2:20–2:55 | Check an offered shift before accepting |
| 6 | 2:55–3:30 | Software reliability and verification |
| 7 | 3:30–4:05 | Docker and the Azure deployment |
| 8 | 4:05–4:45 | GitHub Actions CI/CD |
| 9 | 4:45–5:20 | A live demo other people can use |
| 10 | 5:20–5:50 | Delivered outcome and next iteration |

## 1. From a calendar to a deployed product · 20 seconds

Smart Schedule started with a simple question: when can I actually work? In my
previous presentation, I showed a working calendar. For this final milestone,
that calendar has become a complete scheduling workflow, deployed online and
updated through an automated pipeline.

## 2. Brief recap · 35 seconds

The original problem was balancing classes, multiple jobs and personal time.
Last time, private accounts, one-time commitment management and the weekly
calendar were working. The recurring engine existed, but its editing forms
and availability workflow were still next steps. The key distinction remains:
an empty calendar does not automatically mean someone is willing to work.
The progress since then is connecting those pieces into a usable decision.

## 3. Complete recurring workflows · 40 seconds

Users can now create a weekly commitment, change its hours from a future date,
or move or cancel just one occurrence. In the demo, Job A changes from nine
to one, to ten to two, starting November thirtieth. Earlier weeks retain their
original hours. Before a recurring change is saved, the app shows a dated
review and flags conflicts. Overnight commitments and daylight-saving choices
are handled in the scheduling services, rather than scattered through views.

## 4. Calculated availability · 45 seconds

Availability was still a planned calculation in my previous talk. Users now
set working windows, including date-specific overrides, and the app subtracts
one-time and recurring commitments. The same Monday example now works: a
working window from eight to eight, a class from ten to twelve, and study from
twelve to two leave eight to ten and two to eight. The employer-facing text
contains only dates and available hours, so private reasons for being busy
are not shared. Users can copy this result directly.

## 5. Check an offered shift · 35 seconds

The shift checker answers: can I accept this particular offer? It checks the
whole interval against commitments and working windows. A Monday offer from
eleven to eleven-thirty conflicts with the class. Hours outside a working
window are reported separately. Checking does not save anything. If a clock
change makes a date uncertain, the app asks for review instead of confidently
reporting that time as available.

## 6. Reliability and verification · 35 seconds

The earlier deck reported one hundred and eighty-nine tests. The latest full
PostgreSQL suite passed five hundred and sixty-five. These cover account
isolation, recurring history, overnight boundaries and daylight-saving changes.
A separate Docker rehearsal checks HTTPS, login, secure forms, persistence and
backup restoration. The value is not just a larger count: it is evidence that
the workflow handles cases that a basic calendar can easily miss.

## 7. Deployment architecture · 35 seconds

The app now has separate development and production settings and is packaged
with Docker. On one Azure Ubuntu virtual machine, Caddy handles HTTPS,
Gunicorn serves Django, and PostgreSQL keeps schedules in persistent storage.
My custom domain points to that server. This simple architecture fits the
university demonstration and student credit. Backups are supported, but the
app and database share a server; I am not claiming high availability.

## 8. CI/CD · 40 seconds

GitHub Actions now tests pull requests and automatically deploys successful
pushes to the main branch. The pipeline builds and rehearses a Docker image,
then deploys that exact tested image. Before migrations, it takes a database
backup. It verifies the app and public HTTPS address before reporting success.
Azure access uses OpenID Connect, and the runner's temporary SSH firewall rule
is removed afterward. The first complete automated deployment has already passed.

## 9. A demo other people can use · 35 seconds

The result is something other people can try, rather than a project that only
runs on my laptop. The live demo contains fictional classes, job shifts and
protected personal time. A non-admin guest can inspect the week, generate
availability and check an offer. Private accounts remain separate. Actual
screenshots are included here, so this presentation still works if the room's
internet connection is unreliable.

## 10. Delivered outcome · 30 seconds

The original promise was a practical answer to when I can actually work.
Users can now plan a week, check an offer and share available hours, and I
can deploy updates by pushing tested code. Google Calendar integration and
natural-language entry remain future work. You can try the guest account
using the link or QR code. Thank you.

## Rehearsal and evidence notes

- Use **T** to start/pause the six-minute timer; aim to finish by **5:50**.
- **P** opens private presenter notes. Share only the audience window/tab.
- The availability example is now implemented, unlike the earlier report.
- The 565-test figure is the latest verified full suite, not a performance or
  accuracy score. The separate Docker rehearsal is an additional check.
- The 189-test figure comes from the previous presentation's recorded status.
- Baseline screenshots use the fictional demo week **23–29 November 2026**.
- Site: <https://schedule.khadkabijay.com.np/>. Guest: `schedule_demo` /
  `DemoSchedule!2026`. The account is shared; use fictional data only.
- If you choose a live walkthrough, pre-login before the talk and use slide 9's
  35-second window. Otherwise present the embedded screenshot without switching.
- If behind, shorten slide 6 to the current test count and Docker rehearsal,
  and explain only the main branch of the CI/CD diagram on slide 8.
- Do not describe Google Calendar sync, natural-language entry, high
  availability or automated off-VM backups as implemented features.
