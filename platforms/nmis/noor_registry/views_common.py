"""Small helpers shared by the story 1 views (no network, no shell)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from flask import abort, current_app, g, render_template

from .authz import AuthzError
from .registry import RegistryError, parse_time

TENDER_ID_RE = re.compile(r"^NT-\d{4}-\d{4}$")

STATUS_LABELS = {"candidate": "مرشَّحة", "accepted": "مقبولة", "rejected": "مرفوضة"}
DECISION_LABELS = {"approved": "معتمد", "approved_with_reservation": "معتمد بتحفظ",
                   "rejected": "مرفوض"}
FIELD_LABELS = {"closing_at": "موعد الإغلاق"}

#: Authorization refusal codes that mean "this tender does not exist".
_NOT_FOUND = frozenset({"no_tender"})


def db():
    """The sqlite connection of the current request."""
    return current_app.extensions["noor_registry"]["get_db"]()


def user():
    """The authenticated user (loaded from the signed session only)."""
    return getattr(g, "current_user", None)


def check_tender_id(tender_id: str) -> str:
    """404 for anything that is not a well formed internal id."""
    if not isinstance(tender_id, str) or not TENDER_ID_RE.match(tender_id):
        abort(404)
    return tender_id


def message(text: str, status: int, details=()):
    """Render a plain message page with an HTTP status."""
    return render_template("message.html", text=text, details=list(details)), status


def refused(exc: AuthzError):
    """403 for a refused action, 404 when the tender is unknown."""
    if exc.reason in _NOT_FOUND:
        return message("المنافسة غير موجودة.", 404)
    if exc.reason == "bad_decision":
        return message("القرار غير صالح (التحفظ يحتاج نصًا).", 400)
    return message("لا تملك صلاحية تنفيذ هذا الإجراء على هذه المنافسة.", 403)


def conflict(exc: RegistryError):
    """409 for a business-rule refusal."""
    return message(_REGISTRY_MESSAGES.get(exc.reason, "تعذّر تنفيذ الإجراء."), 409)


_REGISTRY_MESSAGES = {
    "duplicate": "توجد منافسة بالمصدر والمرجع نفسيهما.",
    "not_candidate": "المنافسة ليست «مرشَّحة»، فلا يمكن اتخاذ هذا القرار.",
    "missing_fields": "لا يمكن القبول قبل استكمال الحقول الناقصة.",
    "not_missing": "الحقل ليس ناقصًا؛ الاستكمال للحقول الناقصة فقط.",
}


def data_age(value: str | None) -> str:
    """Human age of a timestamp ("قبل 3 أيام"), or "غير معروف"."""
    if not value:
        return "غير معروف"
    try:
        delta = datetime.now(timezone.utc) - parse_time(value)
    except RegistryError:
        return "غير معروف"
    if delta.total_seconds() < 0:
        return "تاريخ في المستقبل"
    if delta.days >= 1:
        return f"قبل {delta.days} يوم"
    return f"قبل {int(delta.total_seconds() // 3600)} ساعة"
