"""T022: generic route enumeration / authorisation harness.

The harness walks the *real* ``url_map`` of the application, therefore every
route that is added later is covered automatically.  For each rule it checks
that

* state changing views are marked with ``@state_change`` and are rejected
  without a session, without a CSRF token and for a ``viewer`` account,
* read only views never change the database,
* download views need a session and a CSRF token and are closed for viewers,
* no rule mixes ``GET`` with a state changing method.
"""

from __future__ import annotations

import hashlib

from app_fixtures import csrf_of
from noor_registry.db import open_db

STATE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
#: Endpoints a viewer is allowed to POST to (logout and the login form).
VIEWER_EXEMPT_ENDPOINTS = {"logout", "login_post"}
EXPECTED_ENDPOINTS = {
    "login", "login_post", "logout", "home",
    # Story 1 (T043-T046): the harness must see them, so a missing blueprint fails loudly.
    "tenders.list_tenders", "tenders.tender_page",
    "imports.import_form", "imports.import_post",
    "approval.accept", "approval.reject", "approval.complete_field",
    "manual.manual_form", "manual.manual_post", "manual.select_existing",
}


def _rules(app):
    """Every rule of the application except the static file handler."""
    return [rule for rule in app.url_map.iter_rules()
            if rule.endpoint != "static" and not rule.rule.startswith('/internal/')]


def _dummy_value(rule, argument):
    """Fill a URL converter with a harmless dummy value."""
    converters = getattr(rule, "_converters", None) or {}
    converter = converters.get(argument)
    name = type(converter).__name__ if converter is not None else ""
    if "Integer" in name:
        return "1"
    if "Float" in name:
        return "1.0"
    if "UUID" in name:
        return "00000000-0000-0000-0000-000000000000"
    if "Path" in name:
        return "x"
    return "NT-2026-0001"


def _url(app, rule):
    """Build a URL for ``rule`` with all converters filled."""
    adapter = app.url_map.bind("localhost")
    arguments = {argument: _dummy_value(rule, argument) for argument in rule.arguments}
    method = sorted(rule.methods - {"HEAD", "OPTIONS"})[0]
    return adapter.build(rule.endpoint, arguments, method=method, append_unknown=False)


def _snapshot(conn):
    """A stable fingerprint of every table of the database."""
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    snapshot = {}
    for table in tables:
        freshness = {'system_session': {'last_seen_at', 'idle_expires_at'}}
        columns = [column[1] for column in conn.execute('PRAGMA table_info("{}")'.format(table))
                   if column[1] not in freshness.get(table, set())]
        rows = conn.execute('SELECT {} FROM "{}"'.format(
            ', '.join('"{}"'.format(column) for column in columns), table)).fetchall()
        digest = hashlib.sha256()
        for row in sorted(repr(tuple(item)) for item in rows):  # values, not Row object ids
            digest.update(row.encode("utf-8", "replace"))
            digest.update(b"\n")
        snapshot[table] = (len(rows), digest.hexdigest())
    return snapshot


def test_snapshot_detects_sso_table_writes(nmis_app):
    conn = open_db(nmis_app.config.data_dir)
    before = _snapshot(conn)
    with conn:
        conn.execute("INSERT INTO access_decision_log (at,platform_id,result) VALUES (datetime('now'),'radar','forbidden')")
    assert _snapshot(conn) != before
    conn.close()


def test_url_map_is_not_vacuous(nmis_app):
    endpoints = {rule.endpoint for rule in _rules(nmis_app.app)}
    missing = EXPECTED_ENDPOINTS - endpoints
    assert not missing, "missing endpoints: {}".format(sorted(missing))
    assert len(_rules(nmis_app.app)) >= len(EXPECTED_ENDPOINTS)


def test_no_rule_mixes_get_with_a_state_change(nmis_app):
    offenders = []
    for rule in _rules(nmis_app.app):
        methods = set(rule.methods)
        if "GET" in methods and methods & STATE_METHODS:
            offenders.append(rule.endpoint)
    assert not offenders, "rules that mix GET with a state change: {}".format(offenders)


def test_state_changing_rules_are_marked_and_protected(nmis_app, client_for):
    problems = []
    for rule in _rules(nmis_app.app):
        methods = set(rule.methods) & STATE_METHODS
        if not methods:
            continue
        view = nmis_app.app.view_functions[rule.endpoint]
        if not getattr(view, "_noor_state_change", False):
            problems.append("{}: the view is not marked with @state_change".format(rule.endpoint))
            continue
        url = _url(nmis_app.app, rule)
        for method in sorted(methods):
            anonymous = nmis_app.app.test_client()
            response = anonymous.open(url, method=method)
            if 200 <= response.status_code < 300:
                problems.append(
                    "{} {}: anonymous request returned {}".format(
                        rule.endpoint, method, response.status_code
                    )
                )
            # Anonymous but with a valid CSRF token (GET /login hands one out): CSRF must not be
            # the only barrier. login_post is the one route meant to accept anonymous posts.
            if rule.endpoint != "login_post":
                token = csrf_of(anonymous)
                response = anonymous.open(url, method=method, headers={"X-CSRF-Token": token,
                                                                       'Origin': 'http://noor.localhost:5310'},
                                          data={"csrf_token": token})
                if response.status_code not in (401, 403) and not (
                    response.status_code == 302 and "/login" in (response.location or "")
                ):
                    problems.append("{} {}: anonymous request with csrf returned {}".format(
                        rule.endpoint, method, response.status_code))
            manager = client_for("pm")
            response = manager.open(url, method=method,
                                    headers={'Origin': 'http://noor.localhost:5310'})
            if response.status_code != 400:
                problems.append(
                    "{} {}: request without a csrf token returned {} (expected 400)".format(
                        rule.endpoint, method, response.status_code
                    )
                )
            viewer = client_for("view")
            token = csrf_of(viewer)
            response = viewer.open(
                url,
                method=method,
                headers={"X-CSRF-Token": token, 'Origin': 'http://noor.localhost:5310'},
                data={"csrf_token": token},
            )
            if rule.endpoint in VIEWER_EXEMPT_ENDPOINTS or getattr(
                    view, "_noor_viewer_download_ok", False):
                if response.status_code == 403:
                    problems.append(
                        "{} {}: viewers are allowed on this endpoint".format(rule.endpoint, method)
                    )
            elif response.status_code != 403:
                problems.append(
                    "{} {}: viewer request returned {} (expected 403)".format(
                        rule.endpoint, method, response.status_code
                    )
                )
    assert not problems, "\n".join(problems)


def test_get_rules_are_read_only_and_side_effect_free(nmis_app, client_for):
    problems = []
    conn = open_db(nmis_app.config.data_dir)
    try:
        for rule in _rules(nmis_app.app):
            if set(rule.methods) & STATE_METHODS:
                continue
            view = nmis_app.app.view_functions[rule.endpoint]
            if getattr(view, "_noor_state_change", False):
                problems.append(
                    "{}: a GET view must not be marked with @state_change".format(rule.endpoint)
                )
                continue
            url = _url(nmis_app.app, rule)
            # Every enabled account kind, not only the viewer: no GET may change state for anyone.
            for user_id in ("view", "mem", "pm"):
                client = client_for(user_id)
                before = _snapshot(conn)
                client.get(url)
                if _snapshot(conn) != before:
                    problems.append("{}: the database changed during a GET by {}".format(
                        rule.endpoint, user_id))
    finally:
        conn.close()
    assert not problems, "\n".join(problems)


def test_downloads_are_post_only(nmis_app):
    """Downloads go through POST with the CSRF token in the body, never a token in a URL. The
    state-change test above then covers them: anonymous, missing CSRF, and viewer cases."""
    problems = []
    for rule in _rules(nmis_app.app):
        view = nmis_app.app.view_functions[rule.endpoint]
        if getattr(view, "_noor_download", False):
            if set(rule.methods) - {"POST", "OPTIONS"}:
                problems.append("{}: a download must be POST only".format(rule.endpoint))
            if not getattr(view, "_noor_state_change", False):
                problems.append("{}: a download must carry @state_change".format(rule.endpoint))
    assert not problems, "\n".join(problems)


def test_every_browser_write_checks_exact_home_origin(nmis_app, client_for):
    problems = []
    for rule in _rules(nmis_app.app):
        for method in sorted(set(rule.methods) & STATE_METHODS):
            url = _url(nmis_app.app, rule)
            for origin in (None, 'null', 'http://radar.noor.localhost:5310',
                           'http://nmis.noor.localhost:5310',
                           'http://qa.noor.localhost:5310',
                           'http://jr.noor.localhost:5310'):
                client = client_for('pm')
                token = csrf_of(client)
                headers = {'X-CSRF-Token': token}
                if origin is not None:
                    headers['Origin'] = origin
                response = client.open(url, method=method, headers=headers,
                                       data={'csrf_token': token})
                if response.status_code != 403:
                    problems.append(f'{rule.endpoint} {method} {origin}: {response.status_code}')
    assert not problems, '\n'.join(problems)
