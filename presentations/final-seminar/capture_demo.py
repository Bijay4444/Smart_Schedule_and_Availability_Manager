"""Capture fictional demo screens; shift checks do not save schedule changes.

Use temporary tooling: uv run --with playwright --with qrcode python this_file.py
No application dependency or owner credential is required.
"""
from datetime import datetime, UTC
import json
import os
from pathlib import Path

import qrcode
from qrcode.image.svg import SvgPathImage
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'assets'
SITE = 'https://schedule.khadkabijay.com.np'
WEEK = '2026-11-23'
RUN = 'https://github.com/Bijay4444/Smart_Schedule_and_Availability_Manager/actions/runs/45514354911'
BROWSER = os.environ.get('SLIDES_BROWSER_PATH', '/home/bijay/.cache/ms-playwright/chromium-1255/chrome-linux64/chrome')


def main():
    ASSETS.mkdir(exist_ok=True)
    manifest = {'capturedAt': datetime.now(UTC).isoformat(), 'week': WEEK, 'account': 'schedule_demo', 'screens': {}}
    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=BROWSER)
        context = browser.new_context(viewport={'width': 1600, 'height': 1050}, device_scale_factor=1.5, reduced_motion='reduce')
        page = context.new_page()
        page.goto(SITE + '/accounts/login/', wait_until='networkidle')
        page.locator('[name=username]').fill('schedule_demo')
        page.locator('[name=password]').fill('DemoSchedule!2026')
        page.locator('button[type=submit]').click()
        page.wait_for_url(lambda url: '/accounts/login/' not in str(url))

        def settled(path):
            page.goto(SITE + path, wait_until='networkidle')
            page.evaluate('document.fonts.ready')

        settled('/week/?week=' + WEEK)
        # Scroll the calendar's own time grid to the occupied part of the day.
        scrolls = page.evaluate('''()=>[...document.querySelectorAll('main *')].filter(e=>e.scrollHeight>e.clientHeight+200&&e.clientHeight>200&&['auto','scroll'].includes(getComputedStyle(e).overflowY)).map(e=>({className:e.className,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight}))''')
        page.screenshot(path=str(ASSETS / 'week.png'))
        manifest['screens']['week.png'] = {'url': page.url, 'scrollContainers': scrolls}

        settled('/recurring/')
        page.screenshot(path=str(ASSETS / 'recurring.png'))
        manifest['screens']['recurring.png'] = {'url': page.url}

        settled('/availability/?week=' + WEEK)
        page.locator('.availability-day').first.screenshot(path=str(ASSETS / 'monday-availability.png'))
        page.locator('.availability-sharing').screenshot(path=str(ASSETS / 'availability-sharing.png'))
        page.screenshot(path=str(ASSETS / 'availability.png'))
        manifest['screens']['availability.png'] = {'url': page.url, 'monday': page.locator('.availability-day').first.inner_text()}

        settled('/check-shift/?date=' + WEEK)
        page.locator('[name=starts_at]').fill(WEEK + 'T11:00')
        page.locator('[name=ends_at]').fill(WEEK + 'T11:30')
        page.get_by_role('button', name='Check shift').click()
        page.locator('.shift-result').wait_for()
        page.locator('.shift-result').screenshot(path=str(ASSETS / 'shift-result.png'))
        manifest['screens']['shift-result.png'] = {'url': page.url, 'heading': page.locator('#shift-result-heading').inner_text(), 'saved': False}

        try:
            page.goto(RUN, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(2000)
            if 'Test and deploy' in page.locator('body').inner_text():
                page.screenshot(path=str(ASSETS / 'github-run.png'))
                manifest['screens']['github-run.png'] = {'url': RUN}
        except Exception as error:
            manifest['githubCapture'] = type(error).__name__ + '; diagram uses the verified run link instead'
        browser.close()

    qrcode.make(SITE + '/', image_factory=SvgPathImage, border=4).save(ASSETS / 'demo-qr.svg')
    (ASSETS / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
