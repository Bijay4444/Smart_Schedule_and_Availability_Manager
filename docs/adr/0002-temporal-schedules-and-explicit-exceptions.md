---
status: accepted
---

# Preserve schedules with dated revisions and explicit exceptions

Use stable recurring-series identities, effective-date revisions, and
series-level occurrence exceptions so future changes preserve earlier weeks
and deliberate one-off changes survive general edits. Generate dated occurrences
and availability from these rules, retaining original zones and DST policies,
instead of storing an unbounded set of future copies. This adds relational
tables and PostgreSQL range exclusions, but directly represents the confirmed
history, cancellation, and override requirements; see the
[database design](../database_design.md) for fields and migration details.
