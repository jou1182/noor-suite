"""Browser writes require the exact home origin in addition to CSRF."""
from app_fixtures import csrf_of


def test_login_origin_is_mandatory(nmis_app):
    for origin in (None, 'null', 'http://radar.noor.localhost:5310'):
        client = nmis_app.app.test_client()
        headers = {} if origin is None else {'Origin': origin}
        response = client.post('/login', headers=headers, data={
            'csrf_token': csrf_of(client), 'user_id': 'pm',
            'password': nmis_app.passwords['proposal_manager']})
        assert response.status_code == 403
