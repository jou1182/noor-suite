"""Import of noor.tender-candidate/v1 files from NOOR_EXCHANGE_DIR (T043, FR-002a, safeguard 4).

Order of checks, on every request:
1. identity from the session and the creation grant (before anything touches the exchange dir);
2. the file is chosen by NAME only: no "..", no separators, no drive, no reserved device name,
   no symbolic link, and the resolved file must sit directly inside the exchange dir;
3. size limit, then the contract schema and every rule of noor_contracts.validate;
4. only then create or update (an update also needs approver on the existing tender).
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from noor_contracts.validate import MAX_CONTRACT_BYTES, ContractError, validate_bytes

from .authz import AuthzError, authorize_creation
from .registry import RegistryError, upsert_candidate
from .security import login_required, state_change
from .views_common import conflict, db, message, refused, user

bp = Blueprint("imports", __name__)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.json$")
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                       *(f"LPT{i}" for i in range(1, 10))})


class ExchangeNameError(ValueError):
    """The requested name does not denote a regular file inside the exchange dir."""


def _exchange_dir() -> Path:
    return Path(current_app.config["NOOR_CONFIG"].exchange_dir).resolve()


def resolve_exchange_name(exchange_dir: Path, name: str) -> Path:
    """Map a bare file name to a regular file directly inside ``exchange_dir`` (never opens it)."""
    if not isinstance(name, str) or ".." in name or not NAME_RE.match(name):
        raise ExchangeNameError("bad name")
    if name.split(".", 1)[0].upper() in _RESERVED:
        raise ExchangeNameError("reserved name")
    candidate = exchange_dir / name
    if candidate.is_symlink():
        raise ExchangeNameError("symbolic link")
    resolved = candidate.resolve()
    if resolved.parent != exchange_dir or not resolved.is_file():
        raise ExchangeNameError("not a file inside the exchange dir")
    if resolved.stat().st_size > MAX_CONTRACT_BYTES:
        raise ExchangeNameError("too large")
    return resolved


def read_exchange_file(path: Path) -> bytes:
    """The only place that opens an exchange file.

    The name was checked before, but the file may be swapped between the check and the open.
    So: open without following a link where the OS allows it, then compare the OPENED file
    (fstat) with the directory entry (lstat): same file, not a link, a regular file, within the
    size limit. Only then read, at most the limit plus one byte.
    """
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        entry = os.lstat(path)
        if (stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(opened.st_mode)
                or (entry.st_ino, entry.st_dev) != (opened.st_ino, opened.st_dev)
                or opened.st_size > MAX_CONTRACT_BYTES):
            raise ExchangeNameError("the file changed after it was checked")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            return handle.read(MAX_CONTRACT_BYTES + 1)
    finally:
        if fd is not None:
            os.close(fd)


def _list_names(exchange_dir: Path) -> list[str]:
    names = []
    for entry in sorted(exchange_dir.iterdir()):
        try:
            resolve_exchange_name(exchange_dir, entry.name)
        except (ExchangeNameError, OSError):
            continue
        names.append(entry.name)
    return names


@bp.get("/import")
@login_required
def import_form():
    try:
        authorize_creation(db(), user())
    except AuthzError:
        return render_template("tenders/import.html", allowed=False, names=[])
    return render_template("tenders/import.html", allowed=True,
                           names=_list_names(_exchange_dir()))


@bp.post("/import")
@state_change
@login_required
def import_post():
    conn = db()
    try:
        authorize_creation(conn, user())
    except AuthzError as exc:
        return refused(exc)

    try:
        path = resolve_exchange_name(_exchange_dir(), request.form.get("filename", ""))
    except (ExchangeNameError, OSError):
        return message("اسم الملف غير صالح أو الملف غير موجود في مجلد التبادل.", 400)

    try:
        document = validate_bytes(read_exchange_file(path), "tender-candidate")
    except ContractError as exc:
        return message("الملف لا يطابق عقد noor.tender-candidate/v1.", 400, exc.errors)
    except (ExchangeNameError, OSError):
        return message("تعذّرت قراءة الملف أو تغيّر بعد فحصه.", 400)

    try:
        with conn:
            result = upsert_candidate(conn, user=user(), candidate=document)
    except AuthzError as exc:
        return refused(exc)
    except RegistryError as exc:
        return conflict(exc)

    if result.created:
        flash(f"استُوردت المنافسة {result.tender_id} «مرشَّحة».")
    elif result.changed_fields:
        flash(f"المنافسة {result.tender_id} موجودة؛ حُدّثت الحقول: "
              + "، ".join(result.changed_fields))
    else:
        flash(f"المنافسة {result.tender_id} موجودة ولم يتغير شيء.")
    return redirect(url_for("tenders.tender_page", tender_id=result.tender_id))
