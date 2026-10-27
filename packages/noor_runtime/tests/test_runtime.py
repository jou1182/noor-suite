import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_edition_is_fixed(monkeypatch):
    monkeypatch.setenv('NOOR_EDITION', 'cloud')
    from noor_runtime import edition
    importlib.reload(edition)
    assert edition.NOOR_EDITION == 'hackathon'


@pytest.mark.parametrize('value', ['https://example.com/api', '192.0.2.1', '0.0.0.0', 'evil.localhost.example'])
def test_non_loopback_config_fails(value):
    from noor_runtime.edition import assert_loopback
    with pytest.raises(ValueError):
        assert_loopback(value)


@pytest.mark.parametrize('value', ['127.0.0.1', '::1', 'localhost', 'http://radar.noor.localhost:5310'])
def test_loopback_config_allowed(value):
    from noor_runtime.edition import assert_loopback
    assert_loopback(value)
