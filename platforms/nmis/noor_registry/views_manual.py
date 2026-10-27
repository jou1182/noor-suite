"""Manual entry of a synthetic tender without a source reference (T046, FR-001, FR-002a, R3).

- Creating needs the creation grant, checked before anything else; the creator gets approver
  in the same transaction (registry.create_tender) and the decision is recorded as manual_entry.
- Possible matches (same entity, similar title, closing date within 7 days) are shown first;
  creating despite them needs an explicit confirmation bound to the check shown in this session
  (same fields, same match list), and the shown ids go into the record.
- Choosing an existing record is limited to the matches shown in that check and needs approver
  on THAT tender; it issues no id and grants nothing.
- The fields pass the same rules as the radar contract (lengths, date-time with zone, no paths).
"""

from __future__ import annotations

import hashlib
import json

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from noor_contracts.validate import ContractError, validate

from .authz import AuthzError, authorize, authorize_creation, record_approval
from .db import utc_now
from .registry import RegistryError, create_tender, find_possible_matches
from .security import login_required, state_change
from .views_common import TENDER_ID_RE, conflict, db, message, refused, user

bp = Blueprint("manual", __name__)

#: Session key of the last check shown to this user: fingerprint of the fields + the match ids.
CHECK_KEY = "manual_check"
STALE_CHECK = ("القرار لا يطابق آخر فحص عُرض عليك (تغيّرت الحقول أو التطابقات، أو لم يُعرض فحص). "
               "افحص التطابقات من جديد ثم قرّر.")


def _fingerprint(fields: dict) -> str:
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fields() -> dict:
    form = request.form
    return {
        "title": (form.get("title") or "").strip(),
        "issuing_entity": (form.get("issuing_entity") or "").strip(),
        "closing_at": (form.get("closing_at") or "").strip() or None,
        "etimad_ref": (form.get("etimad_ref") or "").strip() or None,
    }


def _check(fields: dict) -> None:
    """Apply the tender-candidate contract rules to the typed fields (raises ContractError)."""
    now = utc_now()
    validate({"schema": "noor.tender-candidate/v1", "source_name": "manual",
              "source_ref": "manual", "source_updated_at": now, "exported_at": now,
              "synthetic": True, **fields}, "tender-candidate")


def _form(fields=None, matches=(), errors=(), status=200):
    return render_template("tenders/manual.html", fields=fields or {}, matches=list(matches),
                           errors=list(errors)), status


@bp.get("/tenders/new")
@login_required
def manual_form():
    try:
        authorize_creation(db(), user())
    except AuthzError:
        return message("حسابك غير مخوّل بإنشاء منافسات مصطنعة.", 200)
    return _form()


@bp.post("/tenders/new")
@state_change
@login_required
def manual_post():
    conn = db()
    try:
        authorize_creation(conn, user())
    except AuthzError as exc:
        return refused(exc)

    fields = _fields()
    try:
        _check(fields)
    except ContractError as exc:
        return _form(fields, errors=exc.errors, status=400)

    matches = find_possible_matches(conn, title=fields["title"],
                                    issuing_entity=fields["issuing_entity"],
                                    closing_at=fields["closing_at"])
    match_ids = [row["tender_id"] for row in matches]
    confirmed = request.form.get("confirm_new") == "1"
    if request.form.get("action") != "create" or (matches and not confirmed):
        # The (synthetic) typed fields are kept so "choose existing" can recompute the matches.
        session[CHECK_KEY] = {"fields": _fingerprint(fields), "typed": fields,
                              "matches": match_ids}
        return _form(fields, matches=matches)
    if matches:
        shown_check = session.get(CHECK_KEY) or {}
        if (shown_check.get("fields") != _fingerprint(fields)
                or shown_check.get("matches") != match_ids):
            return message(STALE_CHECK, 409)

    shown = ",".join(match_ids)
    try:
        with conn:
            grant = authorize_creation(conn, user())
            tender_id = create_tender(conn, creator=user(), creation_grant=grant, **fields)
            record_approval(conn, actor=user(), subject_type="manual_entry",
                            subject_id=f"new:{tender_id}" + (f";matches:{shown}" if shown else ""),
                            decision="approved", acting_role="creation_grant",
                            tender_id=tender_id)
    except AuthzError as exc:
        return refused(exc)
    except RegistryError as exc:
        return conflict(exc)
    session.pop(CHECK_KEY, None)
    flash(f"أُنشئت المنافسة {tender_id} «مرشَّحة» بإدخال يدوي.")
    return redirect(url_for("tenders.tender_page", tender_id=tender_id))


@bp.post("/tenders/new/select")
@state_change
@login_required
def select_existing():
    tender_id = (request.form.get("tender_id") or "").strip()
    if not TENDER_ID_RE.match(tender_id):
        return message("معرّف المنافسة غير صالح.", 400)
    # Only a tender from the matches shown to this session can be chosen (checked first: it
    # reveals nothing); then the usual permission on that tender.
    shown_check = session.get(CHECK_KEY) or {}
    typed = shown_check.get("typed")
    if (not isinstance(typed, dict) or _fingerprint(typed) != shown_check.get("fields")
            or tender_id not in (shown_check.get("matches") or [])):
        return message(STALE_CHECK, 409)
    conn = db()
    # Recompute from the checked fields: a list that changed since it was shown is refused.
    current = [row["tender_id"] for row in find_possible_matches(
        conn, title=typed.get("title", ""), issuing_entity=typed.get("issuing_entity", ""),
        closing_at=typed.get("closing_at"))]
    if current != shown_check["matches"]:
        return message(STALE_CHECK, 409)
    try:
        with conn:
            role = authorize(conn, user(), tender_id, "manual_entry_existing")
            record_approval(conn, actor=user(), subject_type="manual_entry",
                            subject_id=f"existing:{tender_id};shown:"
                                       + ",".join(shown_check["matches"]),
                            decision="approved", acting_role=role, tender_id=tender_id)
    except AuthzError as exc:
        return refused(exc)
    session.pop(CHECK_KEY, None)
    flash(f"رُبط الإدخال اليدوي بالمنافسة القائمة {tender_id}، ولم يصدر معرّف جديد.")
    return redirect(url_for("tenders.tender_page", tender_id=tender_id))
