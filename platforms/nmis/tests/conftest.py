"""Make `noor_registry` importable when pytest runs from the repository root."""

import sys
from pathlib import Path

NMIS_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_ROOT = Path(__file__).resolve().parents[3] / "packages" / "noor_identity"
SSO_ROOT = Path(__file__).resolve().parents[3] / 'packages' / 'noor_sso' / 'python'
if str(NMIS_ROOT) not in sys.path:
    sys.path.insert(0, str(NMIS_ROOT))
if str(IDENTITY_ROOT) not in sys.path:
    sys.path.insert(0, str(IDENTITY_ROOT))
if str(SSO_ROOT) not in sys.path:
    sys.path.insert(0, str(SSO_ROOT))

# Shared Flask app fixtures (nmis_app, client_for) for the security and route-harness tests.
from app_fixtures import *  # noqa: E402,F401,F403
