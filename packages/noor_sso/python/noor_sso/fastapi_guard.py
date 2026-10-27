"""Framework-neutral ASGI assertion guard; FastAPI need not be installed."""
import hmac

from .verify import AssertionError401


class AssertionMiddleware:
    def __init__(self, app, verifier, public_paths=()):
        self.app = app
        self.verifier = verifier
        self.public_paths = frozenset(public_paths)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') in self.public_paths:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', ()))
        try:
            assertion = headers.get(b'x-noor-assertion', b'').decode('ascii')
            principal = self.verifier.verify(assertion)
        except (UnicodeError, AssertionError401):
            await send({'type': 'http.response.start', 'status': 401, 'headers': [(b'content-length', b'0')]})
            await send({'type': 'http.response.body', 'body': b''})
            return
        scope['noor.principal'] = principal
        scope['noor.assertion'] = assertion
        if scope.get('method', 'GET').upper() in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origins = {'nmis_full': 'nmis', 'radar': 'radar',
                       'quick_analysis': 'qa', 'jouready': 'jr'}
            host = origins.get(self.verifier.platform_id)
            expected = f'http://{host}.noor.localhost:5310'.encode() if host else b''
            origin = headers.get(b'origin', b'')
            submitted = headers.get(b'x-csrf-token', b'')
            if origin != expected or not submitted or not hmac.compare_digest(submitted, principal['csrf'].encode()):
                await send({'type': 'http.response.start', 'status': 403, 'headers': [(b'content-length', b'0')]})
                await send({'type': 'http.response.body', 'body': b''})
                return
        await self.app(scope, receive, send)
