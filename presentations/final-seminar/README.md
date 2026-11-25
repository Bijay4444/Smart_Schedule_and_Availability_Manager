# Smart Schedule — final six-minute presentation

Open [index.html](index.html) in a browser. The standalone deck embeds its fonts,
images, QR code, styles and scripts. Presenting the slides needs no internet or
running Django server; links to the hosted demo still need internet.

The **eleven slides** preserve the existing **Open Hours** warm-green design.
They now cover the read-only chatbot, deterministic availability answers,
Google/GitHub signup, and short-screen logout access alongside scheduling,
Azure deployment and CI/CD. The earlier [progress deck](../seminar-progress/index.html)
is unchanged.

## Six-minute delivery

The [speaker notes](speaker-notes.md) contain the 677-word script, also embedded in
the private presenter window. Target **5:50**, leaving ten seconds for transitions.
One chatbot slide was added and other sections shortened to retain six minutes.

| Slide | Speaking window | Topic |
| --- | --- | --- |
| 1 | 0:00–0:15 | From calendar to a product you can ask |
| 2 | 0:15–0:40 | Brief recap |
| 3 | 0:40–1:15 | Recurring schedules and history |
| 4 | 1:15–1:55 | Calculated and shareable availability |
| 5 | 1:55–2:20 | Check an offered shift |
| 6 | 2:20–3:05 | Read-only schedule chatbot |
| 7 | 3:05–3:35 | Reliability and verification status |
| 8 | 3:35–4:05 | Azure deployment architecture |
| 9 | 4:05–4:45 | GitHub Actions CI/CD |
| 10 | 4:45–5:25 | Google/GitHub signup and readiness |
| 11 | 5:25–5:50 | Outcome and next iteration |

Use screenshots for the timed presentation. An optional live walkthrough requires
rehearsal and must fit the same time allowance. Do not spend the talk configuring
OAuth apps, creating API keys, or waiting for free-model quota.

## Controls and PDF

- **Right / Space / Page Down:** next. **Left / Page Up:** previous.
- **Home / End:** first/last. Mouse wheel and swipe also navigate.
- **F:** fullscreen. **T:** start/pause timer. **R:** reset timer.
- **P / N:** private presenter window with script, timing and synchronized controls.
- **E:** edit text. **Escape:** finish. **Ctrl+S / Cmd+S** while editing downloads
  a portable HTML copy. Browser edits do not update the separate notes or PDF.

Share only the **Smart Schedule — Final Seminar** window. Keep the **Private
Presenter** window private. Allow popups if the presenter window is blocked.

The [eleven-page PDF](smart-schedule-final.pdf) is a widescreen static backup;
animations and presenter controls remain in the HTML version. The refreshed deck
uses a new browser-storage version so old inline edits cannot overwrite this update.

## Evidence and readiness

Reviewed **25 November 2026**:

- [Scheduling scope](../../docs/project_spec.md), [chatbot architecture and limitations](../../docs/chat_assistant.md),
  and [social authentication setup](../../docs/social_auth.md).
- Latest full local test run: **596 passed, 4 skipped, 2 failures**. Both failures
  are deployment checks blocked by this WSL environment's Docker integration.
  The slide does not imply the current local run or release is fully green.
- The chatbot and OAuth changes are implemented locally. The chatbot uses Groq
  Free-tier tool calling for broader questions. Common availability requests use
  Python date resolution and report formatting without a model request. It is
  read-only; model interpretation, internet access and quota remain limitations.
- Google/GitHub signup requires provider registration, private credentials,
  deployment and live-provider rehearsal. No successful live OAuth is claimed.
- [Azure deployment record](../../docs/azure_vm_status.md), [CI/CD evidence](../../docs/ci_cd.md),
  and the [earlier successful Actions run](https://github.com/Bijay4444/Smart_Schedule_and_Availability_Manager/actions/runs/45514354911)
  establish the existing hosted scheduling baseline. They do not establish that
  today's local additions have been deployed.

The scheduling screenshots retain their original public baseline for the fictional
week **23–29 November 2026**. The availability diagram remains the implemented
Monday example: 08:00–20:00 working window minus class 10:00–12:00 and study
12:00–14:00 leaves 08:00–10:00 and 14:00–20:00.

The new chat image is the local app showing an actual scheduling-service answer
from the fictional local demo account, which can differ from the public baseline.
The new login image uses placeholder provider settings solely to display the real
configured-provider UI. It contains no credentials or successful authorization.
[assets/manifest.json](assets/manifest.json) records both the older production
captures and the distinct local update sources. Temporary local session writes
were rolled back; capturing these additions called no LLM and changed no schedules.

The public demo remains [schedule.khadkabijay.com.np](https://schedule.khadkabijay.com.np/).
The displayed guest login is `schedule_demo` / `DemoSchedule!2026`: intentionally
public, non-admin, shared fictional data. Use it as the fallback until social
signup is configured and deployed. Google Calendar integration, voice, and
confirmed natural-language schedule changes remain future work. The single-VM
setup has no automatic failover or automated off-VM disaster recovery.

## Refresh and verify

Presentation tooling stays separate from application dependencies:

```bash
# Optional: refresh the older production screenshots and QR code.
uv run --with playwright --with qrcode python presentations/final-seminar/capture_demo.py

# Refresh new local images: requires migrated local DB + fictional schedule_demo.
# Uses placeholder OAuth settings for the UI preview; never calls a model.
uv run --with playwright python presentations/final-seminar/capture_local_updates.py

# Rebuild the embedded assets/notes, then verify and export PDF.
python presentations/final-seminar/build_deck.py
uv run --with playwright python presentations/final-seminar/check_slides.py
```

Use `SLIDES_BROWSER_PATH` for an existing Chromium executable, or install
Playwright's browser with `uv run --with playwright playwright install chromium`.
Chromium also needs its Linux runtime libraries; this workspace's verification
used temporary libraries under `/tmp/schedule-browser-libs/extracted` via
`LD_LIBRARY_PATH`. That path is environment-specific and is not a presentation
runtime dependency. The final standalone HTML and PDF need none of this tooling.

Checks cover all eleven slides at 1280×720 and 390×844, offline asset loading,
fixed 16:9 scaling, text fit, panel/caption overlap, navigation, presenter sync,
timer, editing and portable export. The PDF is checked for eleven widescreen
pages. Screenshots are saved to `/tmp/smart-final-seminar-checks` for visual review.

Updated using the [Frontend Slides skill](https://github.com/zarazhangrui/frontend-slides),
installed at `/home/bijay/.codex/skills/frontend-slides`. The deck embeds Instrument
Sans with its [font license](FONT-LICENSE.txt). The previous deck's complete
fixed-stage base CSS remains included.
