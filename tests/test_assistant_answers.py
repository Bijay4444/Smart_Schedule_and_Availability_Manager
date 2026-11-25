"""Regression cases from a real conversation; no provider quota required."""
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from assistant.services import answer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr('assistant.services.timezone.now', lambda: datetime(2026, 11, 25, 16, tzinfo=UTC))


def test_next_week_does_not_ask_for_exact_dates(owner):
    with patch('assistant.provider.complete', return_value={'content': 'Please specify the exact dates.'}) as model:
        text = answer(owner=owner, history=[], message='What is my work availability next week?')
    assert 'Monday 30 November 2026' in text
    assert 'Sunday 6 December 2026' in text
    model.assert_not_called()


def test_full_31_day_range_is_supported_after_availability_question(owner):
    history = [{'role': 'user', 'content': 'What is my work availability next week?'},
               {'role': 'assistant', 'content': 'Please specify exact dates.'}]
    with patch('assistant.provider.complete', return_value={'content': 'Please narrow to 14 days.'}) as model:
        text = answer(owner=owner, history=history, message='from nov 25 to dec 25')
    assert 'Wednesday 25 November 2026' in text
    assert 'Friday 25 December 2026' in text
    assert '14 days' not in text
    model.assert_not_called()


def test_explicit_range_weekdays_are_calendar_correct(owner):
    with patch('assistant.provider.complete', return_value={'content': '2026-11-27 (Mon)'}) as model:
        text = answer(owner=owner, history=[], message='work availability for the week of 2026-11-27 to 2026-12-03')
    assert 'Friday 27 November 2026' in text
    assert 'Thursday 3 December 2026' in text
    assert '(Mon)' not in text
    model.assert_not_called()


def test_reversed_and_conflicting_ranges_ask_one_specific_clarification(owner):
    text = answer(owner=owner, history=[], message='my work availability from dec 25 to nov 25')
    assert 'end date is before' in text
    text = answer(owner=owner, history=[], message='from nov 25 to dec 8 give me my work availablity next week')
    assert 'Monday 30 November 2026' in text
    assert 'Which range' in text


def test_overnight_report_splits_days_and_totals_without_private_titles(owner, source, monkeypatch):
    from datetime import date, time
    from scheduling.working_windows import WindowSpec, set_working_schedule
    monkeypatch.setattr('scheduling.working_windows.timezone.now', lambda: datetime(2026, 11, 25, 16, tzinfo=UTC))
    set_working_schedule(owner=owner, effective_from=date(2026, 11, 25), windows=[WindowSpec(4, time(22), time(6), 1)])
    text = answer(owner=owner, history=[], message='work availability from nov 27 to nov 28')
    assert 'Friday 27 November 2026: 22:00–24:00' in text
    assert 'Saturday 28 November 2026: 00:00–06:00' in text
    assert 'Total available time: 8h' in text
    assert source.name not in text


def test_year_boundary_and_local_timezone(owner, monkeypatch):
    monkeypatch.setattr('assistant.services.timezone.now', lambda: datetime(2027, 1, 1, 1, tzinfo=UTC))
    # Still Dec 31 in Halifax. Next Monday is Jan 4.
    text = answer(owner=owner, history=[], message='my availability next week')
    assert 'Monday 4 January 2027' in text
    assert 'Sunday 10 January 2027' in text


def test_qualifiers_and_unrelated_history_are_not_silently_ignored(owner):
    history = [{'role': 'user', 'content': 'my work availability next week'},
               {'role': 'user', 'content': 'What do I have tomorrow?'}]
    with patch('assistant.provider.complete', return_value={'content': 'Model handles qualified request.'}) as model:
        for text, prior in [('my availability next week after 4', []),
                            ('my availability next week for Job A', []),
                            ('from nov 25 to dec 8', history)]:
            assert answer(owner=owner, history=prior, message=text) == 'Model handles qualified request.'
    assert model.call_count == 3


def test_tool_report_is_returned_without_model_rewriting(owner):
    import json
    tool = {'tool_calls': [{'id': 'lookup', 'type': 'function', 'function': {
        'name': 'read_work_availability',
        'arguments': json.dumps({'start_date': '2026-11-27', 'end_date': '2026-12-03'})}}]}
    with patch('assistant.provider.complete', return_value=tool) as model:
        text = answer(owner=owner, history=[], message='When could I offer hours to my employer for the coming week?')
    assert 'Friday 27 November 2026' in text
    assert 'Thursday 3 December 2026' in text
    assert model.call_count == 1


def test_incomplete_report_never_confirms_dst_review_date(owner, source, monkeypatch):
    from datetime import date, time
    from scheduling.recurrence import create_series
    from scheduling.working_windows import WindowSpec, set_working_schedule
    monkeypatch.setattr('scheduling.recurrence.timezone.now', lambda: datetime(2026, 1, 1, tzinfo=UTC))
    set_working_schedule(owner=owner, effective_from=date(2026, 1, 1), windows=[WindowSpec(6, time(0), time(12))])
    create_series(owner=owner, source_id=source.pk, title='Private class', starts_on=date(2026, 3, 8), start_time=time(2, 30), end_time=time(3), weekdays=[6])
    text = answer(owner=owner, history=[], message='my availability on 2026-03-08')
    assert 'Needs review — availability not confirmed' in text
    assert 'Draft' in text
    assert 'Total available time' not in text
    assert 'Private class' not in text


def test_date_only_followup_keeps_explicit_year_from_user_context(owner):
    history = [{'role': 'user', 'content': 'my availability from dec 1 2027 to dec 7 2027'},
               {'role': 'assistant', 'content': 'Work availability for December 2027'}]
    text = answer(owner=owner, history=history, message='from dec 8 to dec 14')
    assert 'Wednesday 8 December 2027' in text
    assert '2026' not in text


@pytest.mark.parametrize('message', [
    'my availability this week from dec 7 to dec 13',
    'my availability last week from dec 7 to dec 13',
    'my availability today november 27',
    'my availability tomorrow november 28',
])
def test_all_contradictory_relative_dates_require_clarification(owner, message):
    text = answer(owner=owner, history=[], message=message)
    assert 'Which range' in text
