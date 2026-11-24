# Demo data and feature walkthrough

## Hosted guest account

Open [Smart Schedule](https://schedule.khadkabijay.com.np/accounts/login/) and use
**`schedule_demo` / `DemoSchedule!2026`**. These guest credentials are intentionally
shareable. This ordinary account has no staff status, superuser flag or permissions.
It has five fictional sources, five one-time commitments and six recurring series,
plus working windows and overrides. Its baseline is **23–29 November 2026** in
Halifax time; [open that week](https://schedule.khadkabijay.com.np/week/?week=2026-11-23)
after login to reproduce the initial sample. Recurring rules also demonstrate
future revisions and exceptions.

The account is shared: visitors' edits are visible to other visitors. Use fictional
data only. Other users' schedules and the private owner account are separate.
Only this one demo account was created on Azure, using the existing fixture
builder and scheduling services. The other three accounts below are local test
fixtures. Rerunning the provisioning operation preserves existing guest edits;
no automatic reset is configured. A cloud reset should explicitly target the
guest account; the normal local seed command manages all four test accounts.

## Local fixture setup

The seed command creates four fictional, ordinary user accounts and schedules
for testing the implemented features. It has been run against the local
application database for the week **16–22 November 2026**. Existing personal
accounts and schedules were preserved.

```bash
uv run python manage.py seed_demo
```

Run migrations first on a fresh database. The command prints the demo week,
future-change dates, login credentials, links, and expected outcomes. First use
defaults to the current Monday–Sunday week in Halifax. It retains that week on
later runs, so the same checklist stays usable. All sample names begin with
**Demo ·**. Passwords below are for fictional local accounts with no admin access.

| Username | What to test |
| --- | --- |
| `schedule_demo` | Classes, two employers, personal time, one-time/recurring commitments, conflicts, working windows, exceptions, history, and availability. |
| `schedule_demo_other` | Account privacy, a separate Monday shift, and a fully occupied Friday. |
| `schedule_demo_empty` | First-use/empty states and entering your own sample data. |
| `schedule_demo_dst` | Spring/fall clock changes, review links, draft copying, and repeated-hour choices. |

The initial password for all four is **`DemoSchedule!2026`**. Sign out before
switching accounts. Use the login page at <http://127.0.0.1:8000/accounts/login/>.
Use your existing superuser for admin inspection; the seed does not create one.

## Repeating or restoring the dataset

Running `seed_demo` again preserves every existing demo account's schedule,
password, and manual edits. It prints the original baseline checklist; results
can differ after you edit the schedule. Missing demo accounts can be recreated.
To restore the starting point after experimenting:

```bash
uv run python manage.py seed_demo --reset
```

`--reset` removes manual schedule edits **only in these marked demo accounts**,
restores the seed password, and restores their ordinary-user status. It leaves
other accounts alone. A real account with a reserved demo username is never
claimed or overwritten, even with `--reset`; the command stops without changes.
The operation is atomic, so a failure rolls back the complete run.

To choose another demonstration week:

```bash
uv run python manage.py seed_demo --reset --week 2026-11-16
```

Any date in a week selects its Monday. `--week` accepts canonical dates in
2007–2099, matching the contemporary Halifax DST rules used by these fixtures.
Changing an existing dataset's week requires `--reset`. Future-effective edits
are placed on the later of the next demo Monday or the next actual Halifax
Monday, preserving the services' rule against changing past schedule history.
The printed report always gives the resulting dates. If the main account was
deleted after its planned change became historical, use `--reset` to rebuild it.

The dates below describe the initial **16 November 2026** dataset. For a different
week, use the dated links printed by the command instead.

## Main account: `schedule_demo`

| Feature | Open or do this | Expected result |
| --- | --- | --- |
| Weekly calendar and source colors | [16–22 Nov week](http://127.0.0.1:8000/week/?week=2026-11-16) | Classes, Job A, Job B, and Personal have distinct labeled colors. Previous/next navigation and commitment details work. |
| One-time commitments | [Commitment list](http://127.0.0.1:8000/commitments/) | Protected study, training, errands, an archived handover, and an overnight shift are listed. Edit/delete any sample, then reload the calendar/availability. |
| Saved conflicts | Open Wednesday 18 Nov | Weekly class 10:00–12:00 overlaps training 11:00–13:00. The training retains a conflict badge. |
| Warning before saving | Add a commitment on Monday 16 Nov, 11:00–11:30 | The class conflicts. No save occurs until you explicitly acknowledge the warning. Check that the resulting overlap remains marked. |
| Recurring create/review | [Recurring commitments](http://127.0.0.1:8000/recurring/), add a Monday class | Review the dated preview, then confirm. An open-ended series checks a visible 12-month range. |
| Weekly working windows | [Working windows](http://127.0.0.1:8000/working-windows/?date=2026-11-16) | Multiple windows on Thursday, an overnight Sunday window, two dated revisions, and date overrides are present. |
| Availability subtraction | [Availability](http://127.0.0.1:8000/availability/?week=2026-11-16) | Monday is **08:00–10:00 and 14:00–20:00**: the 08:00–20:00 window minus class and protected study. |
| Employer text | Copy availability and paste into a text editor | Only dates, times, and the timezone appear. No commitment titles, source names, or username. Manual selection also works. |
| Empty date override | Thursday 19 Nov in working windows/availability | The entire date is closed for work although Job A still occupies time. Remove its override through confirmation to restore its normal split windows. |
| Multiple custom windows | Saturday 21 Nov | The override is 10:00–14:00 and 15:00–17:00. Commitments leave **10:00–11:00, 12:00–12:30, and 15:00–17:00**. The 30-minute gap remains. Edit the override to test recalculation. |
| Recurring cancellation | Wednesday 18 Nov | Protected personal time at 17:00–18:00 is cancelled for this date only; later Wednesdays retain it. |
| One-off reschedule | Wednesday 18 Nov | Tuesday's Job A shift has moved to Wednesday 14:00–16:00. The ordinary Tuesday occurrence is absent. |
| Future-effective edits | [23–29 Nov week](http://127.0.0.1:8000/week/?week=2026-11-23) | Job A's regular hours become 10:00–14:00, Job B's become 17:00–21:00, and Monday's working window changes to 09:00–19:00. Earlier weeks retain their old rules. |
| Exceptions survive future edits | Wednesday 25 Nov | An exception created before the general revision still runs 14:00–16:00. Its original Tuesday 24 Nov occurrence is replaced. |
| Finite overnight recurrence | Sunday 22 Nov and Monday 23 Nov | The final recurring occurrence starts 22:00 Sunday and ends 06:00 Monday, even though its last allowed start date is Sunday. |
| One-time overnight | Same two dates/weeks | A separate one-time shift runs Sunday 23:00–Monday 02:00. It is visible in both weekly views and conflicts with the recurring overnight shift. |
| Overnight carry-in at week start | Monday 16 Nov | The previous Sunday's recurring shift remains occupied until 06:00. |
| Full-date replacement of carry-in | [Monday 30 Nov](http://127.0.0.1:8000/working-windows/?date=2026-11-30) | An empty override closes the whole date, including the Sunday working window's 00:00–06:00 carry-in. Restoring the weekly pattern restores those hours. |
| End a series | Job A's details, then [7–13 Dec week](http://127.0.0.1:8000/week/?week=2026-12-07) | The series stops occurrences whose original date is on/after 7 Dec. Earlier dates remain. Test ending another sample from a future date through the form. |
| Archived sources | Former employer in list/forms | Its Tuesday handover and Saturday recurring shift still block availability. Existing entries can be corrected, but the archived source is unavailable for new assignments. Archive buttons remain a separate unfinished feature. |

Use future dates for further all-future edits or series endings; the app
intentionally rejects changes that would rewrite past recurring history.

### Proposed-shift examples

Open [Check a shift](http://127.0.0.1:8000/check-shift/?date=2026-11-16).
Use Monday **16 November 2026** for each of these:

| Offered hours | Expected result |
| --- | --- |
| 08:00–10:00 | Available; touching the class's 10:00 start does not overlap. |
| 10:30–11:30 | Commitment conflict; entirely inside working windows. |
| 07:00–09:00 | Outside working windows 07:00–08:00; no commitment overlap. |
| 07:00–11:00 | Both outside-window hours and a class conflict. |

Checking does not create a commitment. Accepting a shift remains a separate
manual commitment entry. After editing the schedule, check again for fresh results.

## Other and empty accounts

In `schedule_demo_other`, Monday has a private **09:00–10:00** commitment.
Its Monday availability is **08:00–09:00 and 10:00–17:00**. This commitment must
not appear in `schedule_demo`'s calendar or remove its 09:00–10:00 availability.
Friday 20 Nov has working windows **09:00–17:00** occupied by a full-day shift,
so it offers no hours despite having configured working windows.

In `schedule_demo_empty`, visit the commitment list, recurring list, working
windows, availability, and shift checker. The account begins with no sources,
commitments, or working rules. It offers no availability. Try adding a source,
a weekly pattern with multiple/overnight rows, an override, and a commitment.
Test add/remove rows and repeat the forms with JavaScript disabled. A normal
seed rerun retains these experiments; an explicit reset removes them.

Try another account's edit URL while signed in as this account: it should return
404. Use Django's admin only with your existing privileged account; ordinary
demo accounts cannot enter it.

For general interface checks, submit an empty required field or an end before
the start and verify the form retains your input with a helpful error. Resize
the calendar/availability to phone width, use the calendar details and date
navigation, and try the forms with JavaScript disabled. Deny clipboard access
to verify text selection works without falsely claiming a successful copy.
Use your device's reduced-motion preference to inspect calendar transitions.

## Clock-change account: `schedule_demo_dst`

This separate account keeps deliberately unresolved clock cases away from the
main demonstration. Fixtures use the seed week's year; these dates are for 2026.

| Scenario | What to check |
| --- | --- |
| Spring forward, 8 March | [Calendar](http://127.0.0.1:8000/week/?week=2026-03-08): 02:15 becomes 03:15 ADT. Another 02:30–03:00 rule resolves to an invalid interval and needs review. Working windows also contain a deliberate invalid rule. |
| Incomplete availability/copy | [Spring availability](http://127.0.0.1:8000/availability/?week=2026-03-08): Sunday says **Needs review**; copied text includes **Draft**. It must not offer unconfirmed Sunday hours. |
| Incomplete shift check | Check 8 March, 03:30–04:00. The result needs review while retaining a known commitment conflict. |
| Correct review issues | [Working hours on 8 March](http://127.0.0.1:8000/working-windows/?date=2026-03-08): set a valid date override. Also change/cancel the invalid recurring commitment occurrence in the calendar. Then reload availability. Fixing only one cause must not clear the other. |
| Fall back, 1 November | [Calendar](http://127.0.0.1:8000/week/?week=2026-11-01): a recurring start uses the first 01:15 ADT. A one-time commitment spans first 01:15 ADT to second 01:45 AST: 90 elapsed minutes. |
| Explicit second hour | [Shift checker](http://127.0.0.1:8000/check-shift/?date=2026-11-01): check 01:45–01:15 with **second end** selected. This is a positive 30-minute interval, with existing commitment conflicts. Select a second-hour choice on an ordinary time to see its correction message, then clear it. |
| Spring automatic input | Check 8 March, 02:15–04:00. The start moves to 03:15 and the screen explains it. The unresolved schedule still prevents an available result. |
| Spring invalid input | Check 8 March, 02:30–03:00. Resolved endpoints are reversed; the form shows an error instead of checking. |

One-time commitment entry still rejects ambiguous or missing times; its automatic
clock-input enhancement is unfinished. The fixture's repeated-hour one-time
entry uses explicit aware instants through the write service. Voice entry,
Google Calendar, REST endpoints, and source-archive buttons are not implied by
the seeds; use the [development checklist](development_checklist.md) for scope.

## How the seed is built and verified

`scheduling/demo_data.py` constructs fixtures through the existing scheduling
services. Initial recurring fixtures deliberately use the integrity services
without the interactive signed-review step, and one-time fixture conflicts
are explicitly acknowledged. The browser still enforces its normal review
workflow for anything you add or change. No scheduling rules or view behavior
were changed to support fixtures.

The management command only parses options and prints the generated walkthrough.
An ordinary Django group marks seed-owned users; a second group stores the seed
week and planned-change date, avoiding a new model or migration. These groups
have no permissions. Their marker row serializes simultaneous seed runs. Resets
delete only the marked accounts' scheduling graph in protected-reference order.
Any error rolls back all accounts and rows created or reset during that run.

Tests verify the printed scenarios against actual service results, every login,
private page access, unchanged reruns, retained manual changes/passwords, scoped
resets, username collisions, invalid date input, rollback, and historical anchors.
These fixtures support manual feature testing; they do not replace the automated
suite, browser/device testing, or the final three-minute presentation rehearsal.

Verification: **479 PostgreSQL tests pass**, including 28 seed-specific tests.
Django system checks, migration-drift checks, and whitespace checks pass.
Chromium checks passed the actual command/rerun, all four logins, current/future
calendars, a phone calendar at 390px and 320px without page overflow, exact
availability text and short gaps, conflicts and archived obligations, working
windows, all four offered-shift examples, private/empty accounts, and spring/fall
review states without JavaScript errors. Browser fixtures used a disposable
database; the application dataset was separately loaded by the same command.
No new dependency or migration was required.
