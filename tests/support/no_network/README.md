# Noor network guard (demo)

Enable it for a child process (and everything that child spawns) with:

    NOOR_NETGUARD=1 PYTHONPATH=tests/support/no_network python -c "..."
    NOOR_NETGUARD=1 NODE_OPTIONS="--require $PWD/tests/support/no_network/no_network.cjs" node -e "..."

It blocks every non-loopback TCP/UDP connect, DNS lookup and UDP send:
loopback (127.0.0.0/8, ::1, "localhost") and AF_UNIX/IPC paths stay allowed.
It is a demo guard for local test runs, not a security sandbox: it can be bypassed.
