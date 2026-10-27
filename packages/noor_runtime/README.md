# Noor runtime

`NOOR_EDITION` is fixed to `hackathon` in Python and Node. Call `assert_loopback` / `assertLoopback` on configured endpoints at startup. Load the Node network guard with `node --import ./packages/noor_runtime/node/netguard.mjs app.mjs`.

For Python processes, reuse the existing guard in `tests/support/no_network`: set `NOOR_NETGUARD=1` and add that directory to `PYTHONPATH` before starting Python. It installs through `sitecustomize.py`; keep the existing guard files unchanged.
