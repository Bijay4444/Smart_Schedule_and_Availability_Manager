# Smart Schedule — final six-minute seminar

Eleven speaker-led slides, a **5:50** speaking target, and a ten-second buffer.
The HTML deck embeds the same script in its private presenter window. Existing
production captures and new local captures provide an offline demonstration.

| Slide | Speaking window | Topic |
| --- | --- | --- |
| 1 | 0:00–0:15 | From calendar to a product you can ask |
| 2 | 0:15–0:40 | Brief recap |
| 3 | 0:40–1:15 | Recurring schedules and history |
| 4 | 1:15–1:55 | Calculated and shareable availability |
| 5 | 1:55–2:20 | Check an offered shift |
| 6 | 2:20–3:05 | Read-only schedule chatbot |
| 7 | 3:05–3:35 | Reliability and honest verification status |
| 8 | 3:35–4:05 | Azure deployment architecture |
| 9 | 4:05–4:45 | GitHub Actions CI/CD |
| 10 | 4:45–5:25 | Google/GitHub signup and readiness |
| 11 | 5:25–5:50 | Delivered outcome and next iteration |

## 1. From calendar to a product you can ask · 15 seconds

Smart Schedule started with a simple question: when can I actually work? The
project now combines a scheduling workflow, an online deployment, and a new
conversational interface for getting quick answers.

## 2. Brief recap · 25 seconds

The original problem was balancing classes, multiple jobs and personal time.
Last time, private accounts and a weekly calendar were working, while availability
was still planned. Those pieces now form a usable workflow. The key distinction
remains: an empty calendar does not automatically mean someone is willing to work.

## 3. Recurring schedules and history · 35 seconds

Users can now create weekly commitments, change future hours, or move or cancel
one occurrence. In the demo, Job A changes from nine to one, to ten to two, starting
November thirtieth. Earlier weeks retain their original hours. Before saving, the
app reviews dated conflicts. Overnight commitments and daylight-saving choices
are handled in scheduling services, keeping these rules out of Django views.

## 4. Calculated availability · 40 seconds

Users set working windows and date-specific overrides. The app subtracts one-time
and recurring commitments. The original Monday example now works: a window from
eight to eight, a class from ten to twelve, and study from twelve to two leave
eight to ten and two to eight. Employer-facing text contains dates and available
hours without private commitment details. Users can copy this result directly.

## 5. Check an offered shift · 25 seconds

The shift checker asks whether the whole offer fits. Monday eleven to eleven-thirty
conflicts with a class. Hours outside working windows are reported separately.
Checking never saves the shift. If a clock change makes a date uncertain, the
result asks for review rather than claiming availability.

## 6. Read-only schedule chatbot · 45 seconds

The newest workflow is asking a question without opening several pages. A chat
panel and a full chat page share conversation context. Broader questions use a
Groq free-tier model with read-only scheduling tools. Early testing exposed
unnecessary clarification and incorrect weekday labels. I moved common date
resolution and availability formatting into Python. Next week now means the next
Monday through Sunday, and weekdays, intervals and totals come from scheduling
services. The screenshot shows a real calculated report. The assistant cannot
change schedules, and model requests still depend on internet and free quota.

## 7. Reliability and verification · 30 seconds

The latest local suite recorded five hundred and ninety-six passing tests. Four
were skipped, and two deployment checks failed because this WSL environment lacks
a working Docker integration. New tests cover OAuth signup, session privacy, and
the chatbot date regressions. Earlier CI and Docker rehearsal evidence remains
recorded separately. These counts are test evidence, not a claim of perfect AI
accuracy or a fully green current deployment.

## 8. Deployment architecture · 30 seconds

The scheduling app is deployed on an Azure Ubuntu virtual machine. Caddy handles
HTTPS, Gunicorn serves Django, and PostgreSQL stores schedules in persistent
volumes. Separate settings support local and production environments. This
single-server design fits the demonstration. Backups are supported, but there
is no automatic failover, and the new local features still need deployment.

## 9. CI/CD · 40 seconds

GitHub Actions tests pull requests and deploys successful pushes to main. It builds
and rehearses a Docker image, then deploys that exact tested image. Before
migrations, it takes a database backup. It checks application health and public
HTTPS before reporting success. Azure access uses OpenID Connect, and temporary
SSH firewall access is removed afterward. The linked run records an earlier
successful deployment; it does not claim today's uncommitted additions are live.

## 10. Social signup and readiness · 40 seconds

Demo participants should be able to create their own account. Google and GitHub
OAuth signup are now implemented alongside password login. A first provider
sign-in creates a private account; returning identities reuse it. Accounts are
not automatically merged just because emails match. The screenshot is a local
preview with both providers configured. Public use still requires registering
the provider apps, setting credentials, deploying the release, and rehearsing
real sign-ins. Until then, the shared fictional guest account remains the demo
fallback. Sign out also stays reachable on short laptop screens.

## 11. Delivered outcome · 25 seconds

Users can plan a week, check an offer and share available hours. The new assistant
shortens the route to that information, while social signup prepares the app for
individual demo accounts. Google Calendar integration, voice, and confirmed
natural-language schedule changes remain future work. The QR code opens the
hosted scheduling demo. Thank you.

## Rehearsal and evidence notes

- Start the timer with **T** and finish by **5:50**. Open private notes with **P**.
- Share only the audience window. The PDF is the static eleven-page backup.
- New chatbot and social-login images are local captures, not production evidence.
  The login image enables dummy provider settings solely to show the real UI;
  it does not represent a completed live OAuth authorization.
- The chat screenshot uses the fictional local `schedule_demo` account for
  23 November 2026. Its answer is produced by the actual Python scheduling service.
- Previous production screenshots retain their original 23–29 November baseline.
- Latest recorded suite: **596 passed, 4 skipped, 2 Docker/WSL failures**.
- Hosted demo: <https://schedule.khadkabijay.com.np/>. Public guest:
  `schedule_demo` / `DemoSchedule!2026`. Shared account; fictional data only.
- For a live demo, pre-login. Do not rely on unconfigured OAuth or unrehearsed free
  API quota during the six-minute talk. Static screenshots require no internet.
- Do not claim that social signup accesses Google Calendar, that the chatbot can
  edit schedules, or that this feature update has already been deployed.
