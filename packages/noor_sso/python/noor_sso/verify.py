"""Verify Ed25519 home assertions in the contract's required order."""
from __future__ import annotations

import base64
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker


class AssertionError401(Exception):
    """The caller should return only HTTP 401, without details."""


def _decode(value):
    if not value or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in value):
        raise ValueError('base64url')
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


class AssertionVerifier:
    def __init__(self, public_key, platform_id, schema_path=None):
        if isinstance(public_key, (str, Path)):
            public_key = serialization.load_pem_public_key(Path(public_key).read_bytes())
        if not isinstance(public_key, Ed25519PublicKey):
            raise TypeError('Ed25519 public key required')
        self.public_key = public_key
        self.platform_id = platform_id
        if schema_path is None:
            schema_path = Path(__file__).resolve().parents[3] / 'noor_contracts' / 'noor_contracts' / 'schemas' / 'principal.schema.json'
        self.validator = Draft202012Validator(json.loads(Path(schema_path).read_text(encoding='utf-8')),
                                                format_checker=FormatChecker())
        self.seen = {}
        self.lock = threading.Lock()

    def verify(self, assertion, now=None, *, replay=True):
        try:
            # Format, signature, schema, audience, time, nonce: order is security relevant.
            parts = assertion.split('.')
            if len(parts) != 3 or parts[0] != 'v1':
                raise ValueError('format')
            payload_bytes, signature = _decode(parts[1]), _decode(parts[2])
            self.public_key.verify(signature, (parts[0] + '.' + parts[1]).encode('ascii'))
            payload = json.loads(payload_bytes.decode('utf-8'))
            if next(self.validator.iter_errors(payload), None) is not None:
                raise ValueError('schema')
            if json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8') != payload_bytes:
                raise ValueError('canonical')
            if payload['platform_id'] != self.platform_id:
                raise ValueError('audience')
            current = now or datetime.now(timezone.utc)
            issued, expires = _date(payload['issued_at']), _date(payload['expires_at'])
            if issued > current + timedelta(seconds=2) or current >= expires or expires <= issued or expires - issued > timedelta(seconds=5):
                raise ValueError('time')
            if replay:
                with self.lock:
                    self.seen = {nonce: expiry for nonce, expiry in self.seen.items() if expiry > current}
                    if payload['nonce'] in self.seen:
                        raise ValueError('replay')
                    self.seen[payload['nonce']] = expires
            return payload
        except (AttributeError, TypeError, ValueError, KeyError, UnicodeError, InvalidSignature):
            raise AssertionError401() from None
