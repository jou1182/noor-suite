"""Loopback client for tender-level home authorization decisions."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator, FormatChecker


class AuthzClient:
    def __init__(self, platform_key, home_url='http://127.0.0.1:5310', schema_path=None):
        parsed = urlsplit(home_url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path or parsed.query:
            raise ValueError('home authz endpoint must be loopback')
        self.url = home_url + '/internal/authz/check'
        self.key = platform_key
        if schema_path is None:
            schema_path = Path(__file__).resolve().parents[3] / 'noor_contracts' / 'noor_contracts' / 'schemas' / 'authz-decision.schema.json'
        self.validator = Draft202012Validator(json.loads(Path(schema_path).read_text(encoding='utf-8')),
                                                format_checker=FormatChecker())

    def check(self, assertion, tender_id, action):
        body = json.dumps({'assertion': assertion, 'tender_id': tender_id, 'action': action}).encode('utf-8')
        request = Request(self.url, body, headers={'Authorization': 'Noor-Platform ' + self.key,
                                                    'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=2) as response:
                decision = json.load(response)
        except (OSError, ValueError):
            return False
        if next(self.validator.iter_errors(decision), None) is not None:
            return False
        return bool(decision['allowed'])
