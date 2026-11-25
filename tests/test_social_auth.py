"""Exercise real OAuth state, signup and session flows with provider transport mocked."""
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from allauth.socialaccount.models import SocialAccount, SocialToken

pytestmark = pytest.mark.django_db


@pytest.fixture
def configured(settings):
    from copy import deepcopy
    providers = deepcopy(settings.SOCIALACCOUNT_PROVIDERS)
    for name in ('google', 'github'):
        providers[name]['APP'] = {'client_id': f'{name}-test-client', 'secret': 'test-secret', 'key': ''}
    settings.SOCIALACCOUNT_PROVIDERS = providers


def start(client, provider, **data):
    response = client.post(reverse(f'{provider}_login'), data)
    assert response.status_code == 302
    return parse_qs(urlparse(response.url).query)


def finish(client, provider, state, profile):
    module = 'allauth.socialaccount.providers.' + provider + '.views.'
    adapter = 'GoogleOAuth2Adapter' if provider == 'google' else 'GitHubOAuth2Adapter'
    def login(adapter, request, app, token, **kwargs):
        return adapter.get_provider().sociallogin_from_response(request, profile)
    with patch('allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token', return_value={'access_token': 'test-token'}), patch(module + adapter + '.complete_login', autospec=True, side_effect=login):
        return client.get(reverse(f'{provider}_callback'), {'code': 'fake-code', 'state': state})


def profile(provider, uid='123', email='new@example.test'):
    if provider == 'google':
        return {'sub': uid, 'email': email, 'email_verified': True, 'name': 'Demo Person', 'given_name': 'Demo'}
    return {'id': uid, 'login': 'demo-person', 'name': 'Demo Person', 'email': email,
            'emails': [{'email': email, 'primary': True, 'verified': True}]}


def test_only_configured_provider_buttons(client, settings):
    settings.SOCIALACCOUNT_PROVIDERS = {}
    assert b'Continue with Google' not in client.get('/accounts/login/').content
    assert client.post('/accounts/google/login/').url == reverse('login')
    settings.SOCIALACCOUNT_PROVIDERS = {'github': {'APP': {'client_id': 'id', 'secret': 'secret'}}}
    html = client.get('/accounts/login/?next=/week/').content
    assert b'Continue with GitHub' in html
    assert b'Continue with Google' not in html
    assert b'name="next" value="/week/"' in html


@pytest.mark.parametrize('provider', ['google', 'github'])
def test_start_is_csrf_protected_and_get_does_not_start_oauth(configured, provider):
    client = Client(enforce_csrf_checks=True)
    url = reverse(f'{provider}_login')
    response = client.get(url)
    assert response.status_code == 200
    assert b'Continue with' in response.content
    assert client.post(url).status_code == 403
    client.get(reverse('login'))
    response = client.post(url, {'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
    assert response.status_code == 302
    query = parse_qs(urlparse(response.url).query)
    assert query['state']
    assert query['redirect_uri'] == [f'http://testserver/accounts/{provider}/login/callback/']
    assert 'test-secret' not in response.url
    if provider == 'google':
        assert query['code_challenge']
        assert 'calendar' not in query['scope'][0]
    else:
        assert 'repo' not in query['scope'][0]


@pytest.mark.parametrize('provider', ['google', 'github'])
def test_first_signup_repeat_login_private_schedule_and_token_storage(client, configured, provider, django_user_model):
    data = profile(provider)
    state = start(client, provider, next='/week/')['state'][0]
    response = finish(client, provider, state, data)
    assert response.status_code == 302
    assert response.url == '/week/'
    user = django_user_model.objects.get(pk=client.session['_auth_user_id'])
    assert not user.has_usable_password()
    assert not user.is_staff and not user.is_superuser
    assert SocialAccount.objects.filter(user=user, provider=provider, uid='123').exists()
    assert not SocialToken.objects.exists()
    assert client.get('/week/').context['week']['entry_count'] == 0
    client.post('/accounts/logout/')
    state = start(client, provider)['state'][0]
    response = finish(client, provider, state, data)
    assert response.status_code == 302
    assert client.session['_auth_user_id'] == str(user.pk)
    assert django_user_model.objects.count() == 1


def test_callback_missing_or_invalid_state_never_authenticates(client, configured, django_user_model):
    with patch('allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token') as exchange:
        response = client.get(reverse('github_callback'), {'code': 'fake', 'state': 'bad-state'})
    exchange.assert_not_called()
    assert '_auth_user_id' not in client.session
    assert not django_user_model.objects.exists()
    assert b'Sign-in could not finish' in response.content


def test_cancelled_consent_has_recovery_link(client, configured):
    state = start(client, 'google')['state'][0]
    response = client.get(reverse('google_callback'), {'error': 'access_denied', 'state': state}, follow=True)
    assert b'Sign-in cancelled' in response.content
    assert b'Back to sign in' in response.content


def test_matching_email_never_takes_over_existing_account(client, configured, django_user_model):
    existing = django_user_model.objects.create_user(username='existing', email='same@example.test', password='existing-password')
    state = start(client, 'github')['state'][0]
    response = finish(client, 'github', state, profile('github', email=existing.email))
    assert response.url == reverse('socialaccount_signup')
    assert '_auth_user_id' not in client.session
    assert not SocialAccount.objects.filter(user=existing).exists()
    page = client.get(response.url)
    assert b'not merged automatically' in page.content


def test_external_next_url_is_not_followed(client, configured):
    state = start(client, 'github', next='https://evil.example/')['state'][0]
    response = finish(client, 'github', state, profile('github'))
    assert response.status_code == 302
    assert response.url == reverse('home')


def test_no_local_signup_route(client):
    assert client.get('/accounts/signup/').status_code == 404
