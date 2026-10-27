"""Fixed demo edition and startup checks for configured network destinations."""

import ipaddress
from urllib.parse import urlsplit

NOOR_EDITION = 'hackathon'


def assert_loopback(url_or_host):
    if not isinstance(url_or_host, str) or not url_or_host or url_or_host != url_or_host.strip():
        raise ValueError('loopback address required')
    if '://' in url_or_host:
        parsed = urlsplit(url_or_host)
        if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password or not parsed.hostname:
            raise ValueError('loopback URL required')
        host = parsed.hostname
    else:
        if any(c in url_or_host for c in '/?#@'):
            raise ValueError('loopback host required')
        host = url_or_host.strip('[]').lower()
    if host == 'localhost' or host == 'noor.localhost' or host.endswith('.noor.localhost'):
        return url_or_host
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError('non-loopback address') from exc
    if not address.is_loopback:
        raise ValueError('non-loopback address')
    return url_or_host
