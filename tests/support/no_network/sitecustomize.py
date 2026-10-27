"""Demo guard: refuse non-loopback network access when NOOR_NETGUARD=1.

CPython imports a module named ``sitecustomize`` during start-up (see the
``site`` module), so putting this directory on ``PYTHONPATH`` activates the
guard for every interpreter that inherits the environment - children
included::

    NOOR_NETGUARD=1 PYTHONPATH=tests/support/no_network python -c "..."

When ``NOOR_NETGUARD`` is not ``"1"`` this module does nothing at all.

Only the calls named in the brief are patched; the unpatched callables are
kept in module globals so the guard can call through to them.

Note: if some other ``sitecustomize`` lives further down ``sys.path`` this
module deliberately does *not* try to import or chain it - a demo guard is not
a good place to fight the interpreter's start-up order.
"""

from __future__ import annotations

import ipaddress
import os
import socket

GUARD_ERROR_MESSAGE = "network blocked by Noor guard: non-loopback destination"

_LOOPBACK_NAMES = frozenset({"localhost"})
_UNIX_FAMILY = getattr(socket, "AF_UNIX", None)
_PATCH_MARKER = "_noor_netguard_patched"

# --------------------------------------------------------------------------
# originals (kept in module globals on purpose)
# --------------------------------------------------------------------------
original_socket = socket.socket
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
original_create_connection = socket.create_connection
original_getaddrinfo = socket.getaddrinfo
original_sendto = socket.socket.sendto

# True when another copy of this guard already patched the socket module.
_already_patched = bool(getattr(socket.socket, _PATCH_MARKER, False))


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _normalize_host(host):
    """Return a comparable textual form of *host* (or ``None``)."""
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    elif not isinstance(host, str):
        return None
    value = host.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if "%" in value:  # scope id, e.g. fe80::1%eth0
        value = value.split("%", 1)[0]
    return value.lower()


def _host_allowed(host):
    """True when *host* denotes the loopback interface."""
    if host is None:
        return True  # "this host" - not a remote destination
    value = _normalize_host(host)
    if value is None:
        return False
    if value == "":
        return True  # empty string means "local"
    if value in _LOOPBACK_NAMES:
        return True
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False  # a name we do not know -> not loopback
    if address.is_loopback:
        return True
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None and mapped.is_loopback:
        return True
    return False


def _check_host(host):
    if not _host_allowed(host):
        raise PermissionError(GUARD_ERROR_MESSAGE)


def _check_socket_address(sock, address):
    """Validate the destination of ``connect``/``sendto`` on *sock*."""
    family = getattr(sock, "family", None)
    if _UNIX_FAMILY is not None and family == _UNIX_FAMILY:
        return  # AF_UNIX paths are always local
    if address is None:
        return
    if isinstance(address, (tuple, list)):
        if not address:
            return
        _check_host(address[0])
        return
    # A bare string address is a filesystem path (AF_UNIX style) - allow it.
    return


def _check_address_pair(address):
    """Validate the ``(host, port)`` pair used by ``create_connection``."""
    if address is None:
        return
    if isinstance(address, (tuple, list)):
        if not address:
            return
        _check_host(address[0])
        return
    _check_host(address)


# --------------------------------------------------------------------------
# installation
# --------------------------------------------------------------------------
def _install():
    """Patch the socket API (idempotent)."""
    if getattr(socket.socket, _PATCH_MARKER, False):
        return False

    def connect(self, address):
        _check_socket_address(self, address)
        return original_connect(self, address)

    def connect_ex(self, address):
        _check_socket_address(self, address)
        return original_connect_ex(self, address)

    def create_connection(address, *args, **kwargs):
        _check_address_pair(address)
        return original_create_connection(address, *args, **kwargs)

    def getaddrinfo(host, port, *args, **kwargs):
        _check_host(host)
        return original_getaddrinfo(host, port, *args, **kwargs)

    def sendto(self, data, *args, **kwargs):
        if len(args) >= 2:
            address = args[1]
        elif args:
            address = args[0]
        else:
            address = kwargs.get("address")
        _check_socket_address(self, address)
        return original_sendto(self, data, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.create_connection = create_connection
    socket.getaddrinfo = getaddrinfo
    setattr(socket.socket, _PATCH_MARKER, True)
    return True


if os.environ.get("NOOR_NETGUARD") == "1":
    _install()
