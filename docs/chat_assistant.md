# Read-only scheduling assistant

The assistant is available at `/chat/` and through **Ask my schedule** on signed-in
pages. Both surfaces share the current login session's conversation. Clearing chat
or signing out removes that conversation. Only the latest six exchanges are kept;
the model receives at most 6,000 characters of recent conversation. History is
context, not a schedule cache: the assistant is instructed to look up fresh data
for each scheduling question, including follow-ups.

## Free demo setup

ChatGPT Plus does not include app API usage. This integration uses a separate
Groq Free-tier account. Create an account and a key at
https://console.groq.com/keys, leave the account on Free, and put these values in
the local `.env` (never commit the actual key):

```dotenv
GROQ_API_KEY=your-key-here
GROQ_MODEL=openai/gpt-oss-20b
```

Install locked dependencies with `uv sync`, restart Django, sign in to a fictional
seeded demo account, and open **Ask my schedule**. No migrations are added by this
feature. DRF provides the authenticated REST boundary; the Groq SDK handles model
requests. No vector database, model training, local GPU, or paid fallback is used.

Groq Free-tier quotas and model availability can change. Verify the selected model
and your limits in the console. Each answer can use several provider requests, so
leave headroom during rehearsal. A free account requires internet and cannot
guarantee demo availability. Missing keys, exhausted quota, and provider errors
produce explicit messages; they never trigger another provider or paid upgrade.
The application cannot prevent charges if someone independently upgrades the
provider account: keep the account on Free for the zero-cost demonstration.

## Architecture and learning notes

The request path is browser → DRF view → conversation service → Groq → validated
tool adapter → existing scheduling service → model explanation.

`assistant/provider.py` knows about Groq but no scheduling models. The conversation
service bounds the tool loop to four model responses, with at most three tools per
response and a 15-second provider timeout per request (automatic retries disabled).
Tools accept only explicit date/time fields. The server supplies the authenticated
owner; model arguments cannot select another account. Unknown tools and extra
arguments are rejected. The model has no database credentials, SQL tool, write
operation, web browsing, or calendar integration.

`read_schedule` retrieves an inclusive 1–31-day Halifax range. It returns all source
commitments (including recurring exceptions), working windows, work availability,
Python-computed durations and conflict pairs, and incomplete-date metadata.
`check_shift` checks a positive interval up to seven elapsed days without saving.
Both reuse the same scheduling services as existing pages. Clock resolution uses
existing Halifax policies; unresolved dates cannot be labelled available by the
shift service. Large results request a narrower range instead of silently omitting
commitments. Source-specific questions filter displayed information; availability
still accounts for every source.

This separation matters: the LLM interprets natural language and explains results;
Python and PostgreSQL remain responsible for scheduling rules. Natural-language
interpretation can still be wrong. The prompt asks for clarification when dates,
AM/PM, or 'free time' are ambiguous, distinguishes calendar gaps from work
availability, and treats stored titles as untrusted data. Answers are rendered as
plain text. Employer-facing availability requests must omit private titles.

## HTTP interface and session safety

- `GET /api/chat/`: `{ "messages": [{ "role": "user|assistant", "content": "…" }] }`.
- `POST /api/chat/`: accepts `{ "message": "…" }` (1–2,000 trimmed characters),
  returns the updated conversation.
- `DELETE /api/chat/`: clears the conversation and returns an empty messages list.
- Session authentication, authenticated-user permissions, and CSRF protection apply.
  Invalid inputs return 400, unsigned requests 403, concurrent requests 409,
  throttled requests 429, and provider failures 503. Errors preserve existing chat.

The default Django local-memory cache limits chat requests to 10 per user per minute
and prevents simultaneous chat operations within the demo's single process. A
multi-worker deployment needs a shared cache with atomic `add` before relying on
these limits. The bounded loop and timeout keep request costs predictable, but
free-tier limits are also enforced by Groq at the account level.

Conversation text resides in Django's server-side session store, not permanent
chat models or browser localStorage. Normal expired-session cleanup still applies.
Relevant schedule data and recent conversation are sent to Groq; use fictional
demo accounts for the presentation. See https://console.groq.com/docs/your-data
for provider data handling.

## Verification and rehearsal

Run `uv run pytest tests/test_assistant.py` for endpoint, privacy, tool-loop,
provider-error, freshness, recurrence, overnight, DST, and read-only checks. Tests
mock Groq; they consume no model quota. Existing scheduling tests exercise the
underlying rules more broadly.

With a real Free-tier key, rehearse:

1. Ask 'What do I have tomorrow?' and compare with the calendar.
2. Ask for next week's work availability and compare with the availability page.
3. Ask about an explicit dated proposed shift and compare with Check a shift.
4. Edit a commitment through the ordinary form, then ask the same question again.
5. Request employer copy text; confirm it contains no private commitment titles.
6. Request a deletion; confirm the assistant explains it cannot change schedules.
7. Move between panel and full page, clear the chat, and verify mobile keyboard use.

Implementation verification: Django system checks and all 17 assistant tests passed.
The full suite had 577 passing tests, four skips, and two deployment-test failures:
the installed Docker command is a Windows/WSL stub without working Docker Desktop
integration. Rendered browser checks could not launch Chromium because this WSL
installation lacks `libnspr4.so`. No live Groq evaluation has been performed:
`GROQ_API_KEY` was not configured during implementation. Live answer quality and
rendered desktop/mobile behavior still need verification in a configured environment.

## Answer-quality correction

The first live conversation exposed unnecessary date clarifications, invented
range limits, and wrong weekday labels. The original implementation let the model
both resolve dates and rewrite availability from a large general-purpose snapshot.
That snapshot also had a payload ceiling which could make a valid long request
look unsupported. A stronger prompt alone would not make date arithmetic reliable.

`assistant/availability_answers.py` now resolves straightforward availability
reports in Python: today/tomorrow/yesterday, this/next/last Monday–Sunday week,
ISO dates, and English month-name ranges. Omitted years use the current Halifax
year (or an explicit year in the range). Reversed ranges and contradictory date
instructions receive a specific clarification. Date-only follow-ups can continue
an availability request, while unrelated questions and source/time-qualified
requests continue through the model. This is a conservative supported vocabulary,
not a general natural-language parser.

The dedicated `read_work_availability` tool provides the same report for model-
interpreted requests. Daily dates, weekdays, interval splitting, DST labels and
elapsed-time totals come from Python and existing services; the report is returned
directly without another model rewrite. It supports 31 inclusive dates without
sending private commitments or a large snapshot back to the model. General
schedule questions still use the LLM; their interpretation is not guaranteed.

Regression tests reproduce the conversation with a fixed local date, including
next week, the full Nov 25–Dec 25 range, date-only follow-ups, and the actual Friday
label for Nov 27, 2026. Additional cases cover overnight splitting, DST review,
year boundaries and qualified requests. All 26 assistant tests pass. No model
upgrade, added dependency, or extra provider cost is required for these fixes.
