"""Application factory of the local NMIS demo (story 1).

The application only serves the loopback interface of the local machine and
never opens an outbound network connection.
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import (
    Flask,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from jsonschema import Draft202012Validator

from . import sso
from .config import load_config
from .db import open_db
from .platforms_registry import load_platforms
from .security import init_security, login_required, state_change
from .security import login as security_login

#: The demo server binds to the loopback interface only, never the wildcard address:
#: the data is synthetic but the application is not hardened for network use.
HOST = "127.0.0.1"
#: Fixed port of the local demo.
PORT = 5310


def get_db():
    """Return the sqlite connection of the current application context."""
    if "db" not in g:
        config = current_app.config["NOOR_CONFIG"]
        # The database must already exist, it is never created from here.
        g.db = open_db(config.data_dir)
    return g.db


def create_app(config=None) -> Flask:
    """Build the Flask application (the database must already exist)."""
    if config is None:
        config = load_config()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["NOOR_CONFIG"] = config
    from importlib.resources import files

    from noor_identity import build_identity
    identity = build_identity(config.identity_dir)
    try:
        labels_document = json.loads(files("noor_identity").joinpath("labels.ar.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("labels.ar.json is missing or malformed") from exc
    from noor_contracts import __file__ as contracts_init
    schema = json.loads((Path(contracts_init).parent / "schemas" / "labels.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(labels_document))
    if errors:
        raise ValueError("labels.ar.json failed noor.labels/v1 validation: " + errors[0].message)
    labels = labels_document["entries"]
    required = {f"platform.{name}" for name in ("radar", "quick_analysis", "nmis_full", "atpas", "jouready")}
    required |= {f"platform_state.{name}" for name in ("running", "stopped", "unavailable_on_device", "not_cleared_for_demo")}
    required |= {f"provider_mode.{name}" for name in ("local", "cloud", "none")}
    missing = sorted(required - labels.keys())
    if missing:
        raise ValueError("labels.ar.json missing shell label keys: " + ", ".join(missing))
    disclosures = json.loads(Path(__file__).with_name("disclosures.ar.json").read_text(encoding="utf-8"))
    app.extensions["noor_registry"] = {"get_db": get_db, "config": config,
                                       "identity": identity, "labels": labels, "disclosures": disclosures,
                                       "platforms": load_platforms(),
                                       "signing_key": sso.load_private_key(config), "bindings": {}}
    from .proxy import route_host
    @app.before_request
    def host_router():
        return route_host()
    @app.context_processor
    def inject_identity():
        return {"identity": identity, "disclosures": disclosures}
    init_security(app, config)
    sso.register_authz(app)
    sso.start_expiry_timer(app)

    @app.teardown_appcontext
    def close_db(exception=None):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.get("/login")
    def login():
        """Render the login form (it carries the CSRF token)."""
        return render_template("login.html")

    @app.post("/login")
    @state_change
    def login_post():
        """Check the credentials and start a new session."""
        user_id = (request.form.get("user_id") or "").strip()
        password = request.form.get("password") or ""
        user = security_login(get_db(), user_id, password)
        if user is None:
            # The same message for every failure: unknown user, wrong
            # password or a disabled account.
            flash("بيانات الدخول غير صحيحة", "error")
            return redirect(url_for("login"))
        return redirect(url_for("home"))

    @app.post("/logout")
    @state_change
    @login_required
    def logout():
        """Drop the session and go back to the login form."""
        sso.revoke(get_db(), g.system_session['sid_hash'], 'logged_out')
        g.clear_sid = True
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def home():
        """The unified home shell."""
        from .views_shell import home as shell_home
        return shell_home()

    # Story 1: registry, import, decisions, manual entry (T043-T046).
    from . import views_approval, views_import, views_manual, views_shell, views_tenders

    for module in (views_tenders, views_import, views_approval, views_manual, views_shell):
        app.register_blueprint(module.bp)

    return app


def main() -> None:
    """Run the local demo server (not used by the tests)."""
    app = create_app()
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
