# Smart Schedule

The language used to describe a person's commitments and the time they can offer for work.

## Language

**Commitment**:
A scheduled obligation or protected block of personal time that makes a person unavailable, such as a class, work shift, or study session.
_Avoid_: Event, appointment when referring to the general concept

**One-time commitment**:
A commitment on a specific date that does not repeat.

**Weekly recurring commitment**:
A commitment that repeats on selected weekdays at fixed times, beginning on a start date and optionally ending on an end date.

**Occurrence**:
One dated instance of a recurring commitment.

**Occurrence exception**:
A one-off reschedule or cancellation of an occurrence that leaves the recurring commitment's usual schedule unchanged.

**Effective date**:
The date from which a schedule change applies, preserving the schedule before that date.

**Overnight commitment**:
A commitment that starts on one calendar date and continues past midnight into the following date. It can be one-time or weekly recurring.

**Commitment source**:
A person's grouping of commitments, such as classes, Job A, Job B, or personal time. Each person has their own sources.

**Archived source**:
A retired commitment source whose past and future commitments are preserved. Archiving does not cancel its scheduled obligations.

**Working window**:
A weekly repeating period during which a person is willing to work, before accounting for their commitments. A weekday can have multiple windows, and a window can continue into the next date.
_Avoid_: Availability when commitments have not yet been accounted for

**Working-date override**:
A person's complete working availability for a particular local date, replacing the usual availability on that date including overnight carry-in. An empty override means unavailable for the whole date.

**Work availability**:
Time within a person's working windows that remains after subtracting their commitments, including every positive-length remaining interval.
_Avoid_: Free time, empty calendar slot

**Weekly availability**:
A person's work availability for a specific week, expressed as available time intervals for each day.

**Proposed shift**:
A work shift being considered before the person decides to add it to their commitments.

**Scheduling conflict**:
An overlap in time between commitments, or between a proposed shift and an existing commitment. A commitment ending exactly when another starts does not overlap it.

**Weekly view**:
A visual presentation of a person's schedule for a specific week.
