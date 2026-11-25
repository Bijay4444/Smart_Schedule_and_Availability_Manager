import json
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from assistant import provider, services
from assistant.tools import execute_tool
from scheduling.models import Commitment

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api(owner):
    client = APIClient()
    client.force_login(owner)
    return client


def call(name="read_schedule", **arguments):
    return {"role": "assistant", "tool_calls": [{"id": "lookup", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments or {"start_date": "2026-10-26", "end_date": "2026-10-26"})}}]}


def test_authentication_and_csrf(owner):
    client = APIClient(enforce_csrf_checks=True)
    assert client.get('/api/chat/').status_code == 403
    assert client.get('/chat/').status_code == 302
    client.force_login(owner)
    assert client.post('/api/chat/', {'message': 'Tomorrow?'}, format='json').status_code == 403
    assert client.delete('/api/chat/').status_code == 403


def test_private_read_and_touching_boundaries(owner, other_source, commitment, halifax_time):
    Commitment.objects.create(source=other_source, title='Secret', starts_at=commitment.starts_at, ends_at=commitment.ends_at)
    Commitment.objects.create(source=commitment.source, title='Touching', starts_at=commitment.ends_at, ends_at=halifax_time('2026-10-26T13:00'))
    data = execute_tool(owner=owner, name='read_schedule', arguments={'start_date': '2026-10-26', 'end_date': '2026-10-26'})
    assert {item['title'] for item in data['commitments']} == {'Morning shift', 'Touching'}
    assert data['conflicts'] == []
    assert data['work_availability'] == []
    assert 'Secret' not in json.dumps(data)


def test_conflicts_and_shift_never_save(owner, commitment, halifax_time):
    Commitment.objects.create(source=commitment.source, title='Overlap', starts_at=halifax_time('2026-10-26T11:00'), ends_at=halifax_time('2026-10-26T13:00'))
    data = execute_tool(owner=owner, name='read_schedule', arguments={'start_date': '2026-10-26', 'end_date': '2026-10-26'})
    assert len(data['conflicts']) == 1
    count = Commitment.objects.count()
    result = execute_tool(owner=owner, name='check_shift', arguments={'starts_at': '2026-10-26T09:00', 'ends_at': '2026-10-26T11:00'})
    assert not result['is_available']
    assert result['outside_working_windows']
    assert result['conflicting_commitments'][0]['title'] == 'Morning shift'
    assert Commitment.objects.count() == count


@pytest.mark.parametrize('name,args', [
    ('delete_commitment', {}),
    ('read_schedule', {'start_date': '2026-01-01', 'end_date': '2027-01-01'}),
    ('read_schedule', {'start_date': '2026-10-26', 'end_date': '2026-10-26', 'owner': 2}),
    ('read_schedule', {'start_date': 'invalid', 'end_date': '2026-10-26'}),
    ('check_shift', {'starts_at': '2026-10-26T10:00Z', 'ends_at': '2026-10-26T11:00Z'}),
])
def test_bad_arguments(owner, name, args):
    with pytest.raises(ValidationError):
        execute_tool(owner=owner, name=name, arguments=args)


def test_followup_reads_fresh_data(api, commitment):
    with patch('assistant.provider.complete', side_effect=[call(), {'content': 'You have a morning shift.'}]) as model:
        response = api.post('/api/chat/', {'message': 'What is on Monday?'}, format='json')
        assert response.status_code == 200
        assert 'Morning shift' in model.call_args.args[0][-1]['content']
    commitment.title = 'Updated shift'
    commitment.save()
    with patch('assistant.provider.complete', side_effect=[call(), {'content': 'Your updated shift.'}]) as model:
        assert api.post('/api/chat/', {'message': 'What about now?'}, format='json').status_code == 200
        assert 'Updated shift' in model.call_args.args[0][-1]['content']
        assert model.call_args.args[0][2]['content'] == 'You have a morning shift.'
    assert len(api.get('/api/chat/').json()['messages']) == 4
    assert api.delete('/api/chat/').json() == {'messages': []}


def test_session_isolation_and_logout(api, other_owner):
    with patch('assistant.provider.complete', return_value={'content': 'Private answer'}):
        api.post('/api/chat/', {'message': 'Hello'}, format='json')
    api.post('/accounts/logout/')
    api.force_login(other_owner)
    assert api.get('/api/chat/').json()['messages'] == []


def test_failures_retain_history(api, settings):
    settings.GROQ_API_KEY = ''
    response = api.post('/api/chat/', {'message': 'Tomorrow?'}, format='json')
    assert response.status_code == 503
    assert 'GROQ_API_KEY' in response.json()['detail']
    assert api.get('/api/chat/').json()['messages'] == []
    assert api.post('/api/chat/', {'message': ' '}, format='json').status_code == 400
    assert api.post('/api/chat/', {'message': 'x' * 2001}, format='json').status_code == 400


def test_loop_is_bounded_and_invalid_calls_are_reported(owner):
    with patch('assistant.provider.complete', return_value=call('delete_commitment')) as model:
        with pytest.raises(provider.AssistantUnavailable):
            services.answer(owner=owner, history=[], message='Delete everything')
    assert model.call_count == 4
    assert 'Unsupported tool' in model.call_args.args[0][-1]['content']


def test_busy_and_rate_limits(api, owner):
    cache.add(f'schedule-chat-busy:{owner.pk}', True, 60)
    assert api.delete('/api/chat/').status_code == 409
    cache.clear()
    for _ in range(10):
        assert api.get('/api/chat/').status_code == 200
    assert api.get('/api/chat/').status_code == 429


def test_surfaces(api):
    page = api.get('/chat/').content.decode()
    assert 'chat-message' in page
    assert 'schedule-chat-panel' not in page
    assert '/static/js/chat.js' in page
    panel = api.get('/week/').content.decode()
    assert 'id="schedule-chat-panel"' in panel
    assert 'Open full chat page' in panel


def test_recurrence_overnight_and_working_windows(owner, source, monkeypatch):
    from datetime import UTC, date, datetime, time
    from scheduling.recurrence import create_series, cancel_occurrence
    from scheduling.working_windows import set_working_schedule, WindowSpec
    monkeypatch.setattr('scheduling.recurrence.timezone.now', lambda: datetime(2026, 10, 25, tzinfo=UTC))
    set_working_schedule(owner=owner, effective_from=date(2026, 10, 25), windows=[WindowSpec(0, time(0), time(12))])
    series = create_series(owner=owner, source_id=source.pk, title='Night shift', starts_on=date(2026, 10, 25), start_time=time(22), end_time=time(6), end_day_offset=1, weekdays=[6])
    args = {'start_date': '2026-10-26', 'end_date': '2026-10-26'}
    data = execute_tool(owner=owner, name='read_schedule', arguments=args)
    assert data['commitments'][0]['title'] == 'Night shift'
    assert data['available_minutes'] == 360
    assert data['work_availability'][0]['starts_at'].startswith('2026-10-26T06:00')
    cancel_occurrence(owner=owner, series_id=series.pk, original_start_date=date(2026, 10, 25))
    assert execute_tool(owner=owner, name='read_schedule', arguments=args)['available_minutes'] == 720


def test_dst_review_withholds_availability(owner, source, monkeypatch):
    from datetime import UTC, date, datetime, time
    from scheduling.recurrence import create_series
    from scheduling.working_windows import set_working_schedule, WindowSpec
    monkeypatch.setattr('scheduling.recurrence.timezone.now', lambda: datetime(2026, 1, 1, tzinfo=UTC))
    set_working_schedule(owner=owner, effective_from=date(2026, 1, 1), windows=[WindowSpec(6, time(0), time(12))])
    create_series(owner=owner, source_id=source.pk, title='Clock review', starts_on=date(2026, 3, 8), start_time=time(2, 30), end_time=time(3), weekdays=[6])
    data = execute_tool(owner=owner, name='read_schedule', arguments={'start_date': '2026-03-08', 'end_date': '2026-03-08'})
    assert not data['complete']
    assert data['needs_review']
    assert data['work_availability'] == []
    shift = execute_tool(owner=owner, name='check_shift', arguments={'starts_at': '2026-03-08T08:00', 'ends_at': '2026-03-08T09:00'})
    assert not shift['is_available']


def test_provider_quota_failure(settings):
    import httpx
    from groq import RateLimitError
    settings.GROQ_API_KEY = 'test-key'
    error = RateLimitError('quota', response=httpx.Response(429, request=httpx.Request('POST', 'https://api.groq.com')), body={})
    with patch('assistant.provider.Groq') as sdk:
        sdk.return_value.__enter__.return_value.chat.completions.create.side_effect = error
        with pytest.raises(provider.AssistantUnavailable, match='quota'):
            provider.complete([], [])
        assert sdk.call_args.kwargs['max_retries'] == 0
