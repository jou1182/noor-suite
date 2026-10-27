"""Platform origins, entry codes and forwarding boundaries."""
from app_fixtures import client_for
from noor_registry import sso
from noor_registry.db import open_db


def test_host_routing_and_one_use_entry(nmis_app, client_for):
    client = client_for('pm')
    assert client.get('/login', base_url='http://unknown.localhost:5310').status_code == 421
    alias = client.get('/login', base_url='http://127.0.0.1:5310')
    assert alias.status_code == 302 and alias.location == 'http://noor.localhost:5310/login'
    conn = open_db(nmis_app.config.data_dir)
    parent = conn.execute('SELECT sid_hash FROM system_session').fetchone()['sid_hash']
    code = sso.entry_code(conn, parent, 'radar')
    url = '/__noor/enter?c=' + code
    assert client.get(url, base_url='http://qa.noor.localhost:5310').status_code == 403
    response = client.get(url, base_url='http://radar.noor.localhost:5310')
    assert response.status_code == 302 and response.location == '/'
    assert 'noor_psid=' in response.headers['Set-Cookie']
    assert 'Domain=' not in response.headers['Set-Cookie']
    assert client.get(url, base_url='http://radar.noor.localhost:5310').status_code == 403
    assert client.get('/internal/authz/check', base_url='http://radar.noor.localhost:5310').status_code == 404
    conn.close()


def test_proxy_strips_credentials_and_requires_platform_origin(nmis_app, client_for, monkeypatch):
    from noor_registry import proxy
    client = client_for('pm')
    conn = open_db(nmis_app.config.data_dir)
    parent = conn.execute('SELECT sid_hash FROM system_session').fetchone()['sid_hash']
    code = sso.entry_code(conn, parent, 'radar')
    client.get('/__noor/enter?c=' + code, base_url='http://radar.noor.localhost:5310')
    captured = {}
    class UpstreamResponse:
        status = 200
        def read(self): return b'ok'
        def getheaders(self): return [('Set-Cookie', 'bad=1'), ('Content-Type', 'text/plain')]
    class Connection:
        def __init__(self, host, port, timeout):
            assert host == '127.0.0.1' and port == 5312
        def request(self, method, path, body, headers):
            captured.update(method=method, path=path, body=body, headers=headers)
        def getresponse(self): return UpstreamResponse()
        def close(self): pass
    monkeypatch.setattr(proxy.http.client, 'HTTPConnection', Connection)
    base = 'http://radar.noor.localhost:5310'
    assert client.post('/api/item', base_url=base).status_code == 403
    response = client.post('/api/item?q=1', base_url=base, data=b'hello',
                           headers={'Origin': base, 'X-Noor-Forged': 'injected',
                                    'X-User-Email': 'fake@example.invalid', 'Authorization': 'Bearer wrong'})
    assert response.status_code == 200 and response.data == b'ok'
    assert 'Set-Cookie' not in response.headers
    assert captured['method'] == 'POST' and captured['path'] == '/api/item?q=1'
    assert captured['body'] == b'hello'
    names = {name.lower() for name in captured['headers']}
    assert 'cookie' not in names and 'authorization' not in names
    assert 'x-user-email' not in names and 'x-noor-forged' not in names
    assert 'x-noor-assertion' in names
    conn.close()
