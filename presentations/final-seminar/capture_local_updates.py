"""Capture local feature evidence without calling an LLM or changing saved data.

Run from the repo with uv run --with playwright python this_file.py.
Requires migrated local PostgreSQL and the fictional schedule_demo account.
OAuth buttons are a clearly labelled configuration preview, not a live login.
"""
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
sys.path.insert(0, str(PROJECT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.django.test')

import django

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, override_settings
from playwright.sync_api import sync_playwright

from assistant.services import answer


def main():
    question = 'What is my work availability on 2026-11-23?'
    with transaction.atomic(), override_settings(ALLOWED_HOSTS=['testserver']):
        owner = get_user_model().objects.get(username='schedule_demo')
        content = answer(owner=owner, history=[], message=question)
        client = Client()
        client.force_login(owner)
        session = client.session
        history = [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': content}]
        session['schedule_chat'] = history
        session.save()
        chat_html = client.get('/chat/').content
        transaction.set_rollback(True)

    request = RequestFactory().get('/accounts/login/')
    request.user = AnonymousUser()
    with override_settings(SOCIALACCOUNT_PROVIDERS={
        name: {'APP': {'client_id': 'preview-only', 'secret': 'preview-only'}} for name in ('google', 'github')
    }):
        login_html = render_to_string('registration/login.html', {'form': AuthenticationForm(request)}, request=request)

    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=os.environ.get('SLIDES_BROWSER_PATH'))
        for name, html, selector, width in [
            ('chat', chat_html, '.chat-page', 1500),
            ('social-login', login_html, '.auth-card', 1366),
        ]:
            page = browser.new_page(viewport={'width': width, 'height': 1050}, device_scale_factor=1.5)
            def handle(route):
                path = urlparse(route.request.url).path
                if path.startswith('/static/'):
                    route.fulfill(path=str(PROJECT / path.lstrip('/')))
                elif path == '/api/chat/':
                    route.fulfill(json={'messages': history})
                else:
                    route.fulfill(body=html, content_type='text/html')
            page.route('http://local-preview.test/**', handle)
            page.goto('http://local-preview.test/')
            page.evaluate('document.fonts.ready')
            if name == 'chat':
                page.locator('.chat-message-assistant').wait_for()
            page.locator(selector).screenshot(path=str(ROOT / 'assets' / f'{name}.png'))
            page.close()
        browser.close()

    manifest_path = ROOT / 'assets/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['localUpdates'] = {
        'capturedAt': datetime.now(UTC).isoformat(),
        'chat.png': {'source': 'Local rendered app with actual scheduling-service response',
                     'account': 'schedule_demo', 'question': question, 'answer': content,
                     'modelCalled': False, 'databaseChanges': 'rolled back'},
        'social-login.png': {'source': 'Local rendered app with placeholder provider configuration',
                             'liveOAuthVerified': False, 'credentialsIncluded': False},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print('Captured local chat evidence and configured-provider UI preview; no saved schedule changes.')


if __name__ == '__main__':
    main()
