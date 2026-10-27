"""Signing key must be supplied as an external PEM at production startup."""
from dataclasses import replace
from pathlib import Path

import pytest
from noor_registry.app import create_app
from noor_registry.keys import generate


def test_generate_refuses_repository_directory():
    # tmp_path is outside the repository on CI, so name a path inside it explicitly.
    inside = Path(__file__).resolve().parents[3] / '.pytest_tmp' / 'refused-keys'
    with pytest.raises(ValueError):
        generate(inside)
    assert not inside.exists()


def test_startup_refuses_missing_or_repository_signing_key(nmis_app):
    for path in (None, Path(__file__).resolve()):
        config = replace(nmis_app.config, signing_key_file=path)
        with pytest.raises(ValueError, match='NOOR_HOME_SIGNING_KEY_FILE'):
            create_app(config)
