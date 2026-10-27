# Noor SSO Node guards

Create a verifier with `createVerifier({ platformId })` from `node/verify.mjs`. It reads the Ed25519 public key from `NOOR_HOME_PUBLIC_KEY_FILE` at startup; an explicit `publicKeyPem` is useful in tests. Pass the verifier to `httpGuard(handler, { verify, publicPaths })` or `expressGuard({ verify, publicPaths })`. Public paths are exact URL paths; all other requests require a fresh `X-Noor-Assertion`.

`createAuthzClient({ homeUrl, platformId })` posts `check({ assertion, tender_id, action })` to the loopback home service. Set `NOOR_PLATFORM_KEY_<PLATFORM>` in the environment. Errors deny authorization.
