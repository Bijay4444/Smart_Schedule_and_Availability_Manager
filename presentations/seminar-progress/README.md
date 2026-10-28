# Smart Schedule — seminar progress presentation

Open [index.html](index.html) in a browser. It is a standalone, offline HTML
presentation: its CSS, JavaScript, font, and app screenshot are embedded. No
Django server or internet connection is needed.

The six slides use the selected **Open Hours** warm-green design. They cover
the problem, project idea, intended availability calculation, current progress,
technical approach, and next steps. The intended audience is a live seminar,
with short slide text and explanations in the speaker script.

## Three-minute delivery

Read [speaker-notes.md](speaker-notes.md) while rehearsing. The script is about
356 words, with a target finish of **2:55** and five seconds for transitions.
Speaking pace varies; rehearse once with the timer and use the shorter technical
explanation in the notes if needed. This deck is a progress report with a static
app screenshot, so a live application walkthrough is unnecessary.

| Slide | Target time | Topic |
| --- | --- | --- |
| 1 | 0:00–0:20 | The scheduling problem |
| 2 | 0:20–0:45 | The project idea |
| 3 | 0:45–1:20 | Planned availability example |
| 4 | 1:20–2:05 | Working features and current progress |
| 5 | 2:05–2:35 | Architecture and technical challenges |
| 6 | 2:35–2:55 | Next steps and closing |

## Presenting and editing

- **Arrow keys / Space / Page Down:** next slide. Left / Page Up: previous.
- **Home / End:** first / last slide. Swipe or use the mouse wheel to navigate.
- **F:** fullscreen. Browser fullscreen commands also work.
- **T:** start/pause the elapsed timer. **R:** reset it. The timer does not advance slides.
- **N:** show/hide notes. Notes appear on the current screen; close them before
  projecting, or keep the Markdown script on another device.
- Move the pointer to reveal the bottom controls; they fade out automatically.
- **E**, or hover/click the upper-left corner: edit slide text. Changes autosave
  locally where browser storage is available. **Escape** finishes editing.
- While editing, **Ctrl+S / Cmd+S** downloads an updated standalone HTML file.
  After edits, review the slide layout. Notes and PDF are separate artifacts.
- Colors are set in `:root`; `.reveal` controls the short entrance animations.
  The 1920×1080 canvas scales as a whole, preserving 16:9 on every screen.

[smart-schedule-progress.pdf](smart-schedule-progress.pdf) is the six-page
widescreen backup. It contains static slides without animations, editing, or
speaker notes. Browser Print → Save as PDF also works; enable background graphics.

## Evidence and status boundaries

Content reflects the local working tree reviewed on 2026-10-27, including
uncommitted weekly-calendar and styling work:

- [Project specification](../../docs/project_spec.md)
- [Development checklist](../../docs/development_checklist.md)
- [Weekly calendar implementation and verification](../../docs/weekly_calendar.md)
- [Scheduling terminology](../../GLOSSARY.md)

The availability example is explicitly **planned behavior**. Working windows,
availability calculation, sharing, recurring forms, and combined save-conflict
checks remain upcoming. The recurring backend and calendar overlap indicators
already exist. Google Calendar and natural-language entry are later ideas.

The **189 PostgreSQL tests passed** statement is the latest recorded application
verification in those project documents; the application suite was not rerun for
this presentation-only task. The screenshot comes from the existing frontend
review captures and shows fictional sample data, including a fictional account.

## Presentation verification

`check_slides.py` uses a temporary Playwright environment, without adding any
application dependency. It verifies desktop and phone stage geometry, text fit,
embedded assets, keyboard/wheel/swipe navigation, URL slide selection, speaker
notes, timer pause/reset, local edit persistence, portable HTML export, and a
six-page 16:9 PDF. It does not access Django or PostgreSQL.

With Playwright and Chromium available:

```bash
uv run --with playwright python presentations/seminar-progress/check_slides.py
```

This regenerates the PDF and writes screenshots under `/tmp/smart-seminar-checks`.
The initial run reused browser tooling already installed in `/tmp`; no project
dependencies changed. If needed on a new machine, install Chromium with
`uv run --with playwright playwright install chromium` first.

Created using the requested
[frontend-slides skill](https://github.com/zarazhangrui/frontend-slides),
installed at `/home/bijay/.codex/skills/frontend-slides`.
Instrument Sans is embedded from the project's existing font; its SIL Open Font
License is included in [FONT-LICENSE.txt](FONT-LICENSE.txt).
