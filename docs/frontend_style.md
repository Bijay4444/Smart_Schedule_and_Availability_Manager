# App-wide frontend style

The shared interface covers every existing application template: sign-in,
overview, weekly calendar, commitment list, source entry, commitment entry/edit,
and deletion confirmation. The scheduling behavior remains defined in
[project_spec.md](project_spec.md).

## Shared implementation

`templates/base.html` owns the application shell: persistent desktop navigation,
compact phone navigation, active-page state, account controls, timezone context,
skip link, and feedback messages. Each page fills the content and breadcrumb
blocks. Signed-out users receive the simpler authentication shell.

`static/css/app.css` owns the visual tokens and reusable patterns. The existing
green identity is retained, with white working surfaces on a lightly tinted
background. Reuse these tokens instead of choosing new values for each screen:

| Token | Value | Use |
| --- | --- | --- |
| `--ink` | `#20372f` | Primary text. |
| `--muted` | `#53685d` | Secondary text and supporting labels. |
| `--accent` | `#315c52` | Primary actions and selected navigation. |
| `--accent-hover` | `#24483f` | Primary-action hover state. |
| `--accent-soft` | `#e9f1eb` | Selected-navigation background. |
| `--canvas` | `#f5f7f4` | Workspace background. |
| `--surface` | `#ffffff` | Forms and working surfaces. |
| `--line` | `#dce4dc` | Structural borders and dividers. |
| `--danger` | `#a53737` | Destructive actions. |
| `--radius` | `12px` | Main surface corners. |
| `--control-radius` | `7px` | Buttons and inputs. |

Instrument Sans is self-hosted under `static/fonts/`, with its SIL Open Font
License and source information alongside it. It supplies one type family for
headings, labels, controls, and data. Main desktop headings use 30px, form
headings 26px, and phone headings 24px. Dates/times use tabular numerals. Text
and layout reflow for long names and labels.

`templates/components/icon.html` supplies the shared SVG icon vocabulary;
decorative icons are hidden from assistive technology. Controls keep a text or
accessible name. `templates/components/form_field.html` supplies consistent
labels, help text, error IDs, and field-error presentation.

## Page patterns

- Page headings group the title, short description, and relevant actions.
- Editors use one bounded form surface, a return link, and a consistent action
  row. Date/time fields sit side by side on desktop and stack on phones.
- The commitment list uses rows within one surface, with source labels, dates,
  full time ranges, and explicit edit/delete controls.
- Delete confirmation names the record and keeps the destructive action distinct
  from keeping it. Errors and overlap warnings retain the existing recovery and
  confirmation behavior.
- Calendar blocks show the title before compact times. Detail popovers retain
  full dates, zone labels, source, overlap information, and one-time editing.
  When endpoint zones differ, the compact block also retains both zone labels.

Below 1024px, desktop navigation becomes a compact top navigation. Below 768px,
forms stack and the calendar becomes a day-by-day agenda. Intermediate calendar
widths scroll inside the calendar frame. Interaction transitions use 160ms;
reduced-motion preferences disable transitions and animation.

## Impeccable installation and use

[Impeccable](https://github.com/pbakaus/impeccable) 4.8.0 is installed user-wide at
`~/.agents/skills/impeccable`, from repository revision
`d34c87e1a00989ae8dbdd7f6b30b70f23319e860`. Its launcher is executable and its
engine's project-context command ran successfully. The skill supplies design
guidance; Django templates and shared CSS render the interface.

This pass applied its existing-interface layout, typography, polish, responsive,
and craft-floor guidance. In a subsequent Codex turn, use `$impeccable` with a
scoped request, such as `polish the commitment form`. The installation does not
add a project Python package or a Node build step. Automatic edit hooks were
not installed; the manual detector was used for this pass.

The Impeccable source scan returned no markup findings but warned that it could
not resolve Django's `{% static %}` stylesheet URL. Its CSS coverage was therefore
incomplete. Rendered-browser verification supplemented it; the scan is not
reported as proof that all CSS rules passed.

## Verification

- The full PostgreSQL suite passes 189 tests after the template updates.
- Every page was captured before and after at 1440px and 390px widths.
- Browser flows cover sign-in, selected-date entry/save, week return/navigation,
  detail popovers and Escape, edit/delete, invalid intervals, and explicit overlap
  confirmation. Tablet and JavaScript-disabled calendar paths also passed.
- Browser checks verified local-font loading, rendered text contrast against
  computed surface colors, no page overflow, 320px layouts, and long unbroken
  commitment/source labels. These are focused checks, not a full accessibility
  conformance certification.
- Browser fixtures use a temporary sample account and remove its records after
  each run. Screenshots contain fictional data.

The implementation keeps scheduling calculations in the existing service layer.
Future screens should extend this shell and these patterns while the remaining
backend and frontend tasks follow [the checklist](development_checklist.md).

## Recurring editor extension

Recurring entry/revision, ending, and one-off changes/cancellation extend the
existing editor and row patterns. Weekdays use a labelled fieldset, and the
following-day and repeated-hour choices use labelled native checkboxes. Review
keeps its date range and limitation explicit. Repeated conflicts show a count
and first example, with remaining dates in native expandable details.

The live recurring journey passed at desktop, tablet, phone, and narrow-phone
widths without page overflow or JavaScript errors. Desktop and phone review
captures were inspected. All 333 PostgreSQL tests pass. Impeccable's manual scan
still could not resolve the Django static tag for CSS color coverage and warned
about the already pinned Instrument Sans family; the agreed font was retained.
Temporary browser tooling/libraries and captures stay under `/tmp`. See
[recurring_workflow.md](recurring_workflow.md) for service and browser evidence.

## Working-window screen extension

The working-window overview, time-row editor, and override restoration form
reuse the shell, green identity, Instrument Sans, and shared form controls.
Weekday patterns and date overrides use distinct sections; the dated preview
explicitly shows willingness before commitments. The phone navigation scrolls
within its own row to accommodate the new working-window link.

Variable time rows use labelled fieldsets and native controls. Adding a row
announces it and focuses the first field; the server also supports row addition
and saving without JavaScript. All-day closure and empty weekly patterns require
an explicit state choice. Date overrides offer following-midnight and repeated-
hour controls, with field errors for invalid resolved intervals.

All 383 PostgreSQL tests pass. Chromium checks passed 1440px, 820px, 390px, and
320px layouts, the complete working-window workflow, and JavaScript-disabled
forms. Desktop and phone captures were inspected. The manual Impeccable scan
again could not resolve Django's static stylesheet tag for color coverage and
flagged the already pinned Instrument Sans family; that font was retained.
See [working_window_screens.md](working_window_screens.md) for evidence and limits.

## Availability display and sharing

The availability screen extends the existing weekly navigation and green
identity. Seven dated rows use actual-duration bars and complete text ranges;
the bars are hidden from assistive technology. Day-specific axes preserve
23/25-hour dates, and repeated-hour labels distinguish ADT from AST. Phone
layouts stack the same content without changing the calculation or hiding gaps.

The sharing surface uses a readonly, selectable textarea with explicit clipboard
copy and live status feedback. Missing or denied clipboard access selects the
text without claiming success. The button stays hidden without JavaScript;
the server-rendered text and navigation remain functional. Incomplete dates
retain an explicit review state, including a draft notice in the copied text.

All 411 PostgreSQL tests pass. Chromium checks passed actual copying, privacy,
fallbacks, refreshed results, incomplete/DST/empty states, no-JavaScript use,
and 1440px/820px/390px/320px layouts without page overflow or JavaScript errors.
Rendered desktop, phone, and incomplete-state captures were inspected. The
manual detector retained its known Django static-tag color-coverage limitation
and existing pinned-font warning. See [availability_screen.md](availability_screen.md).

## Proposed-shift checker

The shift checker extends the existing editor surface and shared form controls.
Its two native date/time controls stay in one column on desktop and phones.
Its answer follows the inputs with separate commitment conflicts and uncovered
hours, so users can distinguish the reasons an offer does not fit. Incomplete
calculations use a review heading and dated corrective links. Native expandable
clock options expose second-hour choices without adding JavaScript. Result
labels include the date and zone and preserve seconds when needed.

The answer's fragment target supports navigation after a form submission;
validation errors retain inputs, and Clear returns to the empty form. Long
private commitment titles wrap inside the existing mobile editor. The shell,
font, palette, and tokens retain the incumbent visual identity. All 451 tests
pass; browser evidence and architecture are recorded in
[proposed_shift_screen.md](proposed_shift_screen.md).

## Short-screen account access and social sign-in

Desktop navigation scrolls independently while the account footer stays inside
`100dvh`. Below 741px viewport height, the decorative sidebar note is hidden to
reserve space for account controls. The compact phone header is preserved.
Google/GitHub sign-in forms use existing button, card, color and typography rules;
only configured providers appear. See [social sign-in setup](social_auth.md).
