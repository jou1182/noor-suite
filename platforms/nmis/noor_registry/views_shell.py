"""Arabic home shell and honest placeholders for unimported platforms."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, g, redirect, render_template, send_file, url_for

from .security import login_required

bp = Blueprint("shell", __name__)


def _platforms() -> list[dict]:
    from .platforms_registry import ORDER, status_documents

    extension = current_app.extensions["noor_registry"]
    entries = extension["platforms"]
    labels = extension["labels"]
    states = status_documents(entries)["platforms"]
    disclosures = extension["disclosures"]
    return [{"id": platform_id, "name": labels[f"platform.{platform_id}"],
             "status": states[platform_id],
             "state_label": labels[f"platform_state.{states[platform_id]['run_state']}"],
             "fr010_text": (f"{states[platform_id]['fr010']['passed']}/{states[platform_id]['fr010']['total']}"
                             if states[platform_id]["fr010"] else disclosures["fr010_unmeasured"]),
             "provider_label": labels[f"provider_mode.{states[platform_id]['provider_mode']}"]}
            for platform_id in ORDER]


def home():
    return render_template("shell/home.html", platforms=_platforms(), active_id=None)


@bp.get("/platform/<platform_id>")
@login_required
def platform(platform_id: str):
    platforms = _platforms()
    selected = next((item for item in platforms if item["id"] == platform_id), None)
    if selected is None:
        abort(404)
    return render_template("shell/platform.html", platforms=platforms,
                           selected=selected, active_id=platform_id)


def entry_url(platform_id: str) -> str | None:
    """Issue a short code only for a platform cleared and running now."""
    from .platforms_registry import BROWSER_ORIGINS
    from .app import get_db
    from . import sso
    if platform_id not in BROWSER_ORIGINS:
        return None
    item = current_app.extensions['noor_registry']['platforms'][platform_id]
    if item['demo_gate'] != 'passed' or item['run_state'] != 'running':
        return None
    code = sso.entry_code(get_db(), g.system_session['sid_hash'], platform_id)
    return BROWSER_ORIGINS[platform_id] + '/__noor/enter?c=' + code


@bp.get('/platform/<platform_id>/enter')
@login_required
def enter_platform(platform_id: str):
    url = entry_url(platform_id)
    if url is None:
        abort(403)
    return redirect(url, code=302)


@bp.get("/identity/<path:name>")
def identity_asset(name: str):
    """Serve only the compiled CSS, referenced fonts, and valid profile logo."""
    extension = current_app.extensions["noor_registry"]
    tokens = extension["identity"]
    allowed = {"build/noor-tokens.css", *tokens["font_files"]}
    if tokens["logo_ok"]:
        allowed.add(tokens["logo"])
    if name not in allowed:
        abort(404)
    root = extension["config"].identity_dir.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        abort(404)
    if name == "build/noor-tokens.css":
        mime = "text/css"
    elif name == tokens.get("logo") and tokens["logo_ok"]:
        mime = tokens["logo_mimetype"]
    else:
        mime = "font/ttf"
    return send_file(path, mimetype=mime)
