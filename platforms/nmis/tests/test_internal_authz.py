"""Platform key and signed binding both gate tender authorization."""
import json
from pathlib import Path
import pytest

from jsonschema import validate

from noor_registry import sso
from noor_registry.authz import load_user
from noor_registry.authz import authorize, AuthzError
from noor_registry.db import open_db
from app_fixtures import give_membership, TENDER_ID


def _decision(nmis_app, client_for, monkeypatch, user_id, platform, action, tender_id=TENDER_ID, task_id=None):
    monkeypatch.setenv('NOOR_PLATFORM_KEY_' + platform.upper(), 'synthetic-platform-key')
    client = client_for(user_id)
    conn = open_db(nmis_app.config.data_dir)
    parent = conn.execute('SELECT * FROM system_session WHERE user_id=? ORDER BY created_at DESC', (user_id,)).fetchone()
    code = sso.entry_code(conn, parent['sid_hash'], platform)
    psid = sso.exchange_entry(conn, code, platform)
    assertion = sso.sign_assertion(nmis_app.app.extensions['noor_registry']['signing_key'],
                                   load_user(conn, user_id), platform, 'system', parent['csrf_token'],
                                   sso.digest(psid), nmis_app.app.extensions['noor_registry']['bindings'])
    conn.close()
    body = {'assertion': assertion, 'tender_id': tender_id, 'action': action}
    if task_id is not None:
        body['task_id'] = task_id
    return nmis_app.app.test_client().post('/internal/authz/check', json=body,
                                           headers={'Authorization': 'Noor-Platform synthetic-platform-key'}).json


@pytest.mark.parametrize('user_id,role', [('pm','approver'), ('ra','review_approver'),
                                         ('mem','member'), ('view','viewer')])
def test_every_role_cannot_read_another_tender(nmis_app, client_for, monkeypatch, user_id, role):
    conn = open_db(nmis_app.config.data_dir)
    with conn:
        if user_id == 'ra':
            conn.execute('UPDATE users SET operator_label=?, enabled=1 WHERE user_id=?', ('Synthetic Operator', user_id))
        conn.execute("INSERT INTO tenders (tender_id,title,issuing_entity,created_by,created_at) VALUES ('NT-2026-0002','Other','Synthetic','pm',datetime('now'))")
    conn.close()
    give_membership(nmis_app, user_id, TENDER_ID, role)
    assert _decision(nmis_app, client_for, monkeypatch, user_id, 'radar', 'read', 'NT-2026-0002')['allowed'] is False


def test_review_approver_can_approve_gaps_on_own_tender(nmis_app, client_for, monkeypatch):
    conn = open_db(nmis_app.config.data_dir)
    with conn:
        conn.execute("UPDATE users SET operator_label='Synthetic Operator', enabled=1 WHERE user_id='ra'")
    conn.close()
    give_membership(nmis_app, 'ra', TENDER_ID, 'review_approver')
    assert _decision(nmis_app, client_for, monkeypatch, 'ra', 'nmis_full', 'approve_gaps')['allowed'] is True


def test_own_tasks_requires_owned_task(nmis_app, client_for, monkeypatch):
    give_membership(nmis_app, 'mem', TENDER_ID, 'member')
    assert _decision(nmis_app, client_for, monkeypatch, 'mem', 'nmis_full', 'own_tasks')['allowed'] is False
    conn = open_db(nmis_app.config.data_dir)
    with conn:
        conn.execute("INSERT INTO tasks (task_id,tender_id,title,owner_user_id,origin) VALUES ('TASK-1',?,'Synthetic task','mem','template:test')", (TENDER_ID,))
        conn.execute("INSERT INTO tasks (task_id,tender_id,title,owner_user_id,origin) VALUES ('TASK-2',?,'Other task','pm','template:test')", (TENDER_ID,))
    conn.close()
    assert _decision(nmis_app, client_for, monkeypatch, 'mem', 'nmis_full', 'own_tasks', task_id='TASK-1')['allowed'] is True
    assert _decision(nmis_app, client_for, monkeypatch, 'mem', 'nmis_full', 'own_tasks', task_id='TASK-2')['allowed'] is False


@pytest.mark.parametrize('platform,permissions', [
    ('radar', {'pm': ('read','send_candidate'), 'ra': ('read',), 'mem': ('read',), 'view': ('read',)}),
    ('quick_analysis', {'pm': ('read','upload_analyze'), 'ra': ('read',),
                        'mem': ('read','upload_analyze'), 'view': ('read_report',)}),
    ('nmis_full', {'pm': ('read','full','accept_tender'), 'ra': ('read','approve_gaps'),
                   'mem': ('read','own_tasks'), 'view': ('read',)}),
    ('jouready', {'pm': ('read','run_review'), 'ra': ('read','approve_report'),
                  'mem': ('read',), 'view': ('read',)}),
])
@pytest.mark.parametrize('user_id,role', [('pm','approver'), ('ra','review_approver'),
                                         ('mem','member'), ('view','viewer')])
def test_fr005_decision_matrix(nmis_app, client_for, monkeypatch, platform, permissions, user_id, role):
    conn = open_db(nmis_app.config.data_dir)
    with conn:
        if user_id == 'ra':
            conn.execute("UPDATE users SET operator_label='Synthetic Operator', enabled=1 WHERE user_id='ra'")
        conn.execute("INSERT INTO tenders (tender_id,title,issuing_entity,created_by,created_at) VALUES ('NT-2026-0002','Other','Synthetic','pm',datetime('now'))")
        if user_id == 'mem':
            conn.execute("INSERT INTO tasks (task_id,tender_id,title,owner_user_id,origin) VALUES ('TASK-1',?,'Synthetic task','mem','template:test')", (TENDER_ID,))
    conn.close()
    give_membership(nmis_app, user_id, TENDER_ID, role)
    universe = set().union(*map(set, permissions.values()))
    for action in universe:
        task = 'TASK-1' if action == 'own_tasks' else None
        decision = _decision(nmis_app, client_for, monkeypatch, user_id, platform, action, task_id=task)
        assert decision['allowed'] is (action in permissions[user_id]), (platform, user_id, action, decision)
        assert _decision(nmis_app, client_for, monkeypatch, user_id, platform, action,
                         'NT-2026-0002', task_id=task)['allowed'] is False


@pytest.mark.parametrize('user_id,role,can_build', [
    ('pm','approver',True), ('ra','review_approver',False),
    ('mem','member',True), ('view','viewer',False),
])
def test_atpas_desktop_role_decisions_are_tender_scoped(nmis_app, user_id, role, can_build):
    conn = open_db(nmis_app.config.data_dir)
    with conn:
        if user_id == 'ra':
            conn.execute("UPDATE users SET operator_label='Synthetic Operator', enabled=1 WHERE user_id='ra'")
        conn.execute("INSERT INTO tenders (tender_id,title,issuing_entity,created_by,created_at) VALUES ('NT-2026-0002','Other','Synthetic','pm',datetime('now'))")
    conn.close()
    give_membership(nmis_app, user_id, TENDER_ID, role)
    conn = open_db(nmis_app.config.data_dir)
    user = load_user(conn, user_id)
    for action, allowed in (('read_outputs', True), ('build', can_build)):
        if action not in sso.ROLE_PERMISSIONS['atpas'][user.kind]:
            assert not allowed
        else:
            assert (authorize(conn, user, TENDER_ID, sso.ACTION_TO_CORE[action]) is not None) is allowed
        with pytest.raises(AuthzError):
            authorize(conn, user, 'NT-2026-0002', sso.ACTION_TO_CORE[action])
    conn.close()


def test_role_matrix_covers_all_five_platforms():
    expected = {
        'radar': (('read', 'send_candidate'), ('read',), ('read',), ('read',)),
        'quick_analysis': (('read', 'upload_analyze'), ('read',),
                           ('read', 'upload_analyze'), ('read_report',)),
        'nmis_full': (('read', 'full', 'accept_tender'), ('read', 'approve_gaps'),
                      ('read', 'own_tasks'), ('read',)),
        'atpas': (('read_outputs', 'build'), ('read_outputs',),
                  ('read_outputs', 'build'), ('read_outputs',)),
        'jouready': (('read', 'run_review'), ('read', 'approve_report'),
                     ('read',), ('read',)),
    }
    roles = ('proposal_manager', 'review_approver', 'member', 'viewer')
    assert {platform: tuple(sso.ROLE_PERMISSIONS[platform][role] for role in roles)
            for platform in expected} == expected


def test_internal_check_requires_key_binding_and_no_origin(nmis_app, client_for, monkeypatch):
    monkeypatch.setenv('NOOR_PLATFORM_KEY_RADAR', 'synthetic-platform-key')
    give_membership(nmis_app, 'pm', TENDER_ID, 'approver')
    client_for('pm')
    conn = open_db(nmis_app.config.data_dir)
    parent = conn.execute('SELECT * FROM system_session').fetchone()
    code = sso.entry_code(conn, parent['sid_hash'], 'radar')
    psid = sso.exchange_entry(conn, code, 'radar')
    key = nmis_app.app.extensions['noor_registry']['signing_key']
    bindings = nmis_app.app.extensions['noor_registry']['bindings']
    assertion = sso.sign_assertion(key, load_user(conn, 'pm'), 'radar', 'system',
                                   parent['csrf_token'], sso.digest(psid), bindings)
    body = {'assertion': assertion, 'tender_id': 'NT-2026-0001', 'action': 'read'}
    client = nmis_app.app.test_client()
    headers = {'Authorization': 'Noor-Platform synthetic-platform-key'}
    assert client.post('/internal/authz/check', json=body,
                       headers={**headers, 'Origin': 'http://noor.localhost:5310'}).status_code == 403
    response = client.post('/internal/authz/check', json=body, headers=headers)
    assert response.status_code == 200 and response.json['allowed'] is True
    body['action'] = 'upload_analyze'
    assert client.post('/internal/authz/check', json=body, headers=headers).json['allowed'] is False
    body['action'] = 'read'
    schema = json.loads((Path(__file__).resolve().parents[3] /
                         'specs/002-full-noor-suite/contracts/authz-decision.schema.json').read_text(encoding='utf-8'))
    validate(response.json, schema)
    bad = client.post('/internal/authz/check', json=body,
                      headers={'Authorization': 'Noor-Platform wrong-key'})
    assert bad.status_code == 401 and bad.json['allowed'] is False
    logs = conn.execute('SELECT * FROM access_decision_log').fetchall()
    assert logs and assertion not in repr([tuple(row) for row in logs])
    assert psid not in repr([tuple(row) for row in logs])
    conn.close()
