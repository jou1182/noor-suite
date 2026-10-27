"""Local register of documented owner authorizations (T030, Codex critique 2026-10-25).

A grant is accepted only when it matches a record in a JSON file kept OUTSIDE the repository
(env NOOR_AUTHORIZATIONS_FILE). The file names the one account designated for Eng. Yousef's
configuration procedure and lists each authorization: who authorized it (an owner role, not a
person's name), for which account, which capability or role, and on which tender.

    {
      "configurer_user_id": "<account designated for the configuration procedure>",
      "authorizations": [
        {"ref": "AUTH-0001", "owner": "nmis_owner", "grantee": "pm",
         "capability": "create_synthetic_tender"},
        {"ref": "AUTH-0002", "owner": "nmis_owner", "grantee": "mem",
         "role": "member", "tender_id": "NT-2026-0001"}
      ]
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "NOOR_AUTHORIZATIONS_FILE"
# Owner role required for each grant. review_approver belongs to the JoUReady owner (JR-D0).
OWNER_FOR_ROLE = {"approver": "nmis_owner", "member": "nmis_owner", "viewer": "nmis_owner",
                  "review_approver": "jouready_owner"}
OWNER_FOR_CAPABILITY = {"create_synthetic_tender": "nmis_owner"}


class AuthorizationError(PermissionError):
    """No matching documented authorization; the message names no person and no path."""


@dataclass(frozen=True)
class Register:
    configurer_user_id: str
    records: tuple[dict, ...]

    def require(self, *, configurer_id: str, ref: str, grantee: str,
                capability: str | None = None, role: str | None = None,
                tender_id: str | None = None) -> dict:
        """Return the record that authorizes exactly this grant, or raise."""
        if configurer_id != self.configurer_user_id:
            raise AuthorizationError("configurer is not the designated configuration account")
        owner = OWNER_FOR_CAPABILITY.get(capability) if capability else OWNER_FOR_ROLE.get(role)
        if owner is None:
            raise AuthorizationError("unknown capability or role")
        wanted = {"ref": ref, "owner": owner, "grantee": grantee}
        wanted.update({"capability": capability} if capability else
                      {"role": role, "tender_id": tender_id})
        for record in self.records:
            if all(record.get(key) == value for key, value in wanted.items()):
                return record
        raise AuthorizationError("no documented authorization matches this grant")


def load_register(repo_root: Path, env: dict | None = None) -> Register:
    location = (env if env is not None else os.environ).get(ENV_VAR)
    if not location:
        raise AuthorizationError(f"{ENV_VAR} is not set")
    path = Path(location).resolve()
    if path.is_relative_to(Path(repo_root).resolve()):
        raise AuthorizationError("the authorization register must live outside the repository")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        configurer = data["configurer_user_id"]
        records = tuple(data["authorizations"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AuthorizationError("the authorization register is missing or malformed") from exc
    if not isinstance(configurer, str) or not configurer or not all(
            isinstance(r, dict) for r in records):
        raise AuthorizationError("the authorization register is missing or malformed")
    return Register(configurer, records)
