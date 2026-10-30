# -*- coding: utf-8 -*-
"""HTML templates for the public dashboard + engineer portal.
Rendered with flask.render_template_string by web_dashboard.py / bp_engineer.py.

The pages live in templates/*.html (moved out of this file on 2026-09-23 so they
can be edited as real HTML); the constant names are unchanged for the importers."""
from pathlib import Path

_TEMPLATES = Path(__file__).resolve().parent / "templates"


def _load(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


LOGIN_HTML          = _load("login.html")
DASH_FORGOT_HTML    = _load("dash_forgot.html")
TENDER_DETAIL_HTML  = _load("tender_detail.html")
DASHBOARD_HTML      = _load("dashboard.html")
RESULTS_HTML        = _load("results.html")
ENGINEER_LOGIN_HTML = _load("engineer_login.html")
ENGINEER_DASH_HTML  = _load("engineer_dash.html")
ENGINEER_VIEW_HTML  = _load("engineer_view.html")
OWNERS_HTML         = _load("owners.html")
TASKS_HTML          = _load("tasks.html")
TEAM_HTML           = _load("team.html")
ENGINEER_PASSWORD_HTML = _load("engineer_password.html")
ADMIN_ENGINEERS_HTML   = _load("admin_engineers.html")
ANALYTICS_HTML         = _load("analytics.html")
ADMIN_SOURCE_HTML      = _load("admin_source.html")
ADMIN_DEMO_HTML        = _load("admin_demo.html")
CALENDAR_HTML          = _load("calendar.html")
TASK_TEMPLATES_HTML    = _load("task_templates.html")
