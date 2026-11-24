"""Read-only public checks after a deployment; no owner password required."""

import argparse
import re
import time
from urllib.parse import urlsplit
from urllib.request import urlopen


def check(url):
    if urlsplit(url).scheme != 'https':
        raise ValueError('Verify the deployment over HTTPS')
    url = url.rstrip('/')
    with urlopen(url + '/healthz/', timeout=15) as response:
        assert response.status == 200 and response.read() == b'ok\n'
    with urlopen(url.replace('https://', 'http://', 1) + '/healthz/', timeout=15) as response:
        assert response.geturl() == url + '/healthz/'
    with urlopen(url + '/accounts/login/', timeout=15) as response:
        html = response.read().decode()
        assert response.status == 200 and 'csrfmiddlewaretoken' in html and 'name="username"' in html
    asset = re.search(r'href="(/static/css/app\.[^"]+\.css)"', html)
    assert asset, 'Versioned application CSS was not found'
    with urlopen(url + asset[1], timeout=15) as response:
        assert response.status == 200 and response.headers['Content-Type'].startswith('text/css')
    print('Public HTTPS, redirect, login form and static CSS verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    args = parser.parse_args()
    for attempt in range(6):
        try:
            check(args.url)
            break
        except Exception:
            if attempt == 5:
                raise
            time.sleep(5)
