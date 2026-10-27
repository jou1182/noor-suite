"""Flask before-request assertion, Origin and CSRF guard for a platform."""
import hmac

from flask import abort, g, request

from .verify import AssertionError401


def install_guard(app, verifier, public_paths=()):
    allowed = frozenset(public_paths)

    @app.before_request
    def verify_home_assertion():
        if request.path in allowed:
            return None
        try:
            g.noor_principal = verifier.verify(request.headers.get('X-Noor-Assertion', ''))
            g.noor_assertion = request.headers['X-Noor-Assertion']
        except (AssertionError401, KeyError):
            abort(401)
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origins = {'nmis_full': 'nmis', 'radar': 'radar',
                       'quick_analysis': 'qa', 'jouready': 'jr'}
            host = origins.get(verifier.platform_id)
            expected_origin = f'http://{host}.noor.localhost:5310' if host else None
            submitted = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
            if request.headers.get('Origin') != expected_origin or not submitted or not hmac.compare_digest(submitted, g.noor_principal['csrf']):
                abort(403)
        return None
