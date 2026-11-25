# Smart Schedule — final six-minute presentation

Open [index.html](index.html) in a browser. This standalone presentation embeds
its font, screenshots, QR code, styles and scripts, so presenting requires no
internet connection or running Django server. The live-demo links need internet.

The ten slides retain the previous presentation's **Open Hours** warm-green
design. The original [progress presentation](../seminar-progress/index.html)
remains unchanged. This final version briefly recaps that report, then shows
the completed scheduling workflows, deployment and CI/CD.

## Six-minute delivery

[speaker-notes.md](speaker-notes.md) contains the 656-word spoken script. Target
**5:50**, leaving ten seconds for transitions or a short pause. Rehearse with the
timer: the script allows time to explain the diagrams without rushing.

| Slide | Speaking window | Topic |
| --- | --- | --- |
| 1 | 0:00–0:20 | From a calendar to a deployed product |
| 2 | 0:20–0:55 | Brief recap of the earlier report |
| 3 | 0:55–1:35 | Complete recurring scheduling workflows |
| 4 | 1:35–2:20 | Working windows, availability and sharing |
| 5 | 2:20–2:55 | Check an offered shift before accepting |
| 6 | 2:55–3:30 | Reliability and verification |
| 7 | 3:30–4:05 | Docker and the Azure deployment |
| 8 | 4:05–4:45 | GitHub Actions CI/CD |
| 9 | 4:45–5:20 | A demo other people can use |
| 10 | 5:20–5:50 | Delivered outcome and next iteration |

Actual screenshots provide the demonstration within the time limit. A live
walkthrough is optional: pre-login and use slide 9's 35-second window if desired.

## Presentation controls

- **Right / Space / Page Down:** next slide. **Left / Page Up:** previous.
- **Home / End:** first / last slide. Mouse wheel and swipe also navigate.
- **F:** fullscreen. **T:** start/pause the timer. **R:** reset it.
- **P / N:** open the private presenter window with the script, timing, next
  slide and synchronized controls. Allow popups for this file if prompted.
- Move the pointer to reveal the bottom controls.
- **E:** edit slide text directly. **Escape:** finish editing. Changes autosave
  to local browser storage. **Ctrl+S / Cmd+S** while editing downloads an updated
  standalone HTML file. These edits do not regenerate the separate notes or PDF.

Share only the original **Smart Schedule — Final Seminar** window/tab. Keep
**Smart Schedule — Private Presenter** private. For a projector, use an extended
display and move the audience window onto it. Entire-screen sharing or display
mirroring also shows any visible presenter window.

The [ten-page PDF](smart-schedule-final.pdf) is a widescreen static backup without
animations, editing or speaker notes. Browser Print → Save as PDF also works;
enable background graphics.

## Evidence and status boundaries

The content reflects the project state reviewed on **24 November 2026**:

- [Previous presentation and its recorded 189-test status](../seminar-progress/README.md)
- [Project specification](../../docs/project_spec.md) and [development checklist](../../docs/development_checklist.md)
- [Proposed-shift workflow](../../docs/proposed_shift_screen.md)
- [Current Azure VM status](../../docs/azure_vm_status.md)
- [CI/CD implementation and recorded 565-test verification](../../docs/ci_cd.md)
- [Actual GitHub Actions workflow](../../.github/workflows/ci-cd.yml)
- [First successful automated deployment](https://github.com/Bijay4444/Smart_Schedule_and_Availability_Manager/actions/runs/45514354911)

The 565 tests are the latest recorded full PostgreSQL suite, with one opt-in
Docker integration check skipped there and run separately in CI. The application
suite was not rerun for this presentation-only change. Slide checks below verify
the presentation itself.

The availability example is now implemented. It uses the fictional demo week
**23–29 November 2026**: Monday's 08:00–20:00 working window minus class
10:00–12:00 and study 12:00–14:00 leaves 08:00–10:00 and 14:00–20:00.
[assets/manifest.json](assets/manifest.json) records capture URLs and the actual
Monday result. Screenshots were captured on 24 November locally (25 November UTC).

The public site is [schedule.khadkabijay.com.np](https://schedule.khadkabijay.com.np/).
Guest credentials, intentionally displayed on the closing slide, are
`schedule_demo` / `DemoSchedule!2026`. This shared account contains fictional
data and has no admin privileges; visitors may change its schedule. Captured
images preserve the baseline for this talk.

Google Calendar integration and natural-language entry are future work. The
Azure setup uses one VM, with no automatic failover. Pre-deployment backups on
the VM do not constitute automated off-VM disaster recovery.

## Refreshing and verifying the deck

These scripts use temporary presentation tooling, without adding application
dependencies. With Python, `uv`, Playwright and Chromium available:

```bash
# Optional: refresh public guest screenshots and the QR code.
uv run --with playwright --with qrcode python presentations/final-seminar/capture_demo.py

# Rebuild the self-contained HTML after changing slide markup or notes.
python presentations/final-seminar/build_deck.py

# Check the deck and regenerate the PDF.
uv run --with playwright python presentations/final-seminar/check_slides.py
```

Set `SLIDES_BROWSER_PATH` to use an existing Chromium executable. Otherwise the
checker uses Playwright's managed browser; install it if needed with
`uv run --with playwright playwright install chromium`. The capture script uses
the existing workstation browser by default; on another machine set the path.
The builder reads the unchanged previous deck and the installed skill's full
`viewport-base.css` to preserve the fixed 1920×1080 stage.

The browser checks cover offline asset loading, all ten slides at desktop
1280×720 and phone 390×844 sizes, 16:9 scaling, text fit and panel overlap,
navigation, private presenter notes, two-window synchronization, popup blocking,
the six-minute timer, edit persistence, portable HTML export and a ten-page
widescreen PDF. Verification screenshots go to `/tmp/smart-final-seminar-checks`.
Capturing screens signs in only as the public guest; the shift check does not
save a commitment.

Created using the [frontend-slides skill](https://github.com/zarazhangrui/frontend-slides),
installed at `/home/bijay/.codex/skills/frontend-slides`. Colors are defined in
`:root`, and `.reveal` controls entrance animations. Instrument Sans is embedded
from the previous deck; its [font license](FONT-LICENSE.txt) is included.
