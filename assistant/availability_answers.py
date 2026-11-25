"""Resolve common date requests and present availability without model arithmetic.

This deliberately handles a small, explicit vocabulary. Questions with source,
shift, or other qualifiers still go through the model's tools.
"""
import re
from datetime import date, timedelta

from django.core.exceptions import ValidationError

from scheduling.availability import availability_for_user
from scheduling.availability_presentation import _clock_label, _duration_label, _repeated
from scheduling.intervals import Interval, clip_intervals, date_bounds

from .tools import ZONE

MONTHS = {name: index for index, names in enumerate([
    (), ('jan', 'january'), ('feb', 'february'), ('mar', 'march'), ('apr', 'april'),
    ('may',), ('jun', 'june'), ('jul', 'july'), ('aug', 'august'), ('sep', 'sept', 'september'),
    ('oct', 'october'), ('nov', 'november'), ('dec', 'december'),
]) for name in names}
DATE = re.compile(r'\b(?:(?P<iso>\d{4}-\d{2}-\d{2})|(?P<month>' + '|'.join(MONTHS) + r')\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?)\b')
FOLLOWUP_WORDS = set('from to through until and the week of next this last today tomorrow yesterday about please dates date range'.split()) | set(MONTHS)
AVAILABILITY = re.compile(r'\b(?:availability|availablity|availabilty)\b')
# Unknown words signal a qualified question rather than a simple report request.
WORDS = set('what is are my me i our the work working availability availablity availabilty next this last week weeks of for from to through until and please give show tell get can you could would like want need copy employer share on in date dates range today tomorrow yesterday about how much time do have thanks'.split()) | set(MONTHS)


def label(day):
    return f'{day:%A} {day.day} {day:%B %Y}'


def week_dates(today, offset=0):
    first = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    return first, first + timedelta(days=6)


def relative_dates(text, today):
    periods = []
    for phrase, offset in [('next week', 1), ('this week', 0), ('last week', -1)]:
        if re.search(r'\b' + phrase + r'\b', text):
            periods.append(week_dates(today, offset))
    for phrase, offset in [('tomorrow', 1), ('yesterday', -1), ('today', 0)]:
        if re.search(r'\b' + phrase + r'\b', text):
            day = today + timedelta(days=offset)
            periods.append((day, day))
    if len(periods) > 1:
        raise ValidationError('You mentioned more than one period. Which date range should I use?')
    return periods[0] if periods else None


def conversation_year(history):
    """Use only the user's relevant date context, never a model-generated year."""
    for turn in reversed(history):
        if turn['role'] != 'user':
            continue
        text = turn['content'].lower()
        if not AVAILABILITY.search(text) and set(re.findall(r'[a-z]+', DATE.sub('', text))) - FOLLOWUP_WORDS:
            break
        years = [int(m['iso'][:4]) if m['iso'] else int(m['year'])
                 for m in DATE.finditer(text) if m['iso'] or m['year']]
        if years:
            return years[-1]
    return None


def resolve_dates(text, today, *, context_year=None):
    """Return an inclusive range, or None for expressions needing interpretation."""
    relative = relative_dates(text, today)
    matches = list(DATE.finditer(text))
    if matches:
        if len(matches) > 2:
            return None
        explicit_years = [int(m['iso'][:4]) if m['iso'] else int(m['year']) for m in matches if m['iso'] or m['year']]
        default_year = explicit_years[0] if explicit_years else context_year or today.year
        try:
            dates = [date.fromisoformat(m['iso']) if m['iso'] else date(
                int(m['year']) if m['year'] else default_year, MONTHS[m['month']], int(m['day'])
            ) for m in matches]
        except ValueError:
            raise ValidationError('That date does not exist. Please correct the date.')
        if len(dates) == 2:
            first, last = dates
        elif re.search(r'\bweek\b', text):
            first, last = week_dates(dates[0])
        else:
            first = last = dates[0]
        if relative is not None and (first, last) != relative:
            relative_first, relative_last = relative
            raise ValidationError(f'You gave {label(first)} to {label(last)}, but the relative period is {label(relative_first)} to {label(relative_last)}. Which range should I use?')
        return first, last
    return relative


def validate_range(first, last):
    if first > last:
        raise ValidationError('The end date is before the start date. Which dates did you mean? Include years if the range crosses New Year.')
    if (last - first).days >= 31:
        raise ValidationError('I can check up to 31 inclusive dates at once. Please choose a range of 31 days or fewer.')
    if first.year < 2 or last.year > 9998:
        raise ValidationError('Choose dates between years 0002 and 9998.')


def availability_answer(*, owner, first, last):
    validate_range(first, last)
    lower, _ = date_bounds(first, ZONE.key)
    _, upper = date_bounds(last, ZONE.key)
    result = availability_for_user(owner=owner, starts_at=lower, ends_at=upper)
    lines = [f'Work availability: {label(first)} – {label(last)}', 'Halifax time (America/Halifax).']
    if not result.complete:
        lines.append('Draft: dates marked Needs review have unconfirmed availability.')
    if result.adjustments or any(getattr(item, 'start_resolution', None) and (
        item.start_resolution.adjustment or item.end_resolution.adjustment
    ) for item in result.commitments):
        lines.append('Clock-change rules were applied: missing times move forward; repeated times use the first occurrence. Review details on your calendar or working-window page.')
    lines.append('')
    total = timedelta()
    day = first
    while day <= last:
        start, end = date_bounds(day, ZONE.key)
        bounds = Interval(start, end)
        if clip_intervals(result.withheld, bounds):
            hours = 'Needs review — availability not confirmed'
        else:
            slots = clip_intervals(result.available, bounds)
            parts = []
            for slot in slots:
                a, b = slot.starts_at.astimezone(ZONE), slot.ends_at.astimezone(ZONE)
                show_zone = _repeated(a) or _repeated(b) or a.utcoffset() != b.utcoffset()
                parts.append(f'{_clock_label(a, end, show_zone)}–{_clock_label(b, end, show_zone)}')
                total += slot.ends_at - slot.starts_at
            hours = '; '.join(parts) or 'Unavailable'
        lines.append(f'{label(day)}: {hours}')
        day += timedelta(days=1)
    lines.extend(['', f'{"Confirmed time on reviewed dates" if not result.complete else "Total available time"}: {_duration_label(total)}'])
    if not result.working_windows and result.complete:
        lines.append('No working windows cover these dates. Empty calendar time is not automatically work availability.')
    return '\n'.join(lines)


def direct_availability_answer(*, owner, history, message, today):
    text = message.lower().strip()
    # Avoid answering a source-filtered question or proposed shift with an unfiltered report.
    residue = DATE.sub('', text)
    if re.search(r'\d', residue) or set(re.findall(r'[a-z]+', residue)) - WORDS:
        return None
    requested = bool(AVAILABILITY.search(text))
    if not requested and set(re.findall(r'[a-z]+', residue)) - FOLLOWUP_WORDS:
        return None
    if not requested:
        # Carry the report intent through date-only clarifications, not unrelated turns.
        for turn in reversed(history):
            if turn['role'] != 'user':
                continue
            previous = turn['content'].lower()
            if AVAILABILITY.search(previous):
                requested = True
                break
            if set(re.findall(r'[a-z]+', DATE.sub('', previous))) - FOLLOWUP_WORDS:
                break
    if not requested:
        return None
    try:
        dates = resolve_dates(text, today, context_year=conversation_year(history))
        if dates is None:
            return None
        return availability_answer(owner=owner, first=dates[0], last=dates[1])
    except (ValidationError, OverflowError) as error:
        return ' '.join(error.messages) if isinstance(error, ValidationError) else 'Those dates are outside the supported calendar range.'
