# Hosted identity contract

IdentityContext admits only server-verified Google Workspace identities in
`pocketcontext.com`. It configures PocketBase's existing `users` collection;
public signup, password/OTP authentication, account deletion and ordinary account
administration are disabled. An operator changes `users.disabled` through the
maintenance REST API or dashboard. Both disabling and re-enabling rotate the
account token key. New users receive no operator authority.

The browser redirects through `https://id.pocketcontext.com/api/oauth2-redirect`.
Register that exact URI on a separate Google Web OAuth client, Internal audience,
with `openid email profile`. The browser uses a memory-only PocketBase auth store,
never caches Google provider credentials and discards its five-minute application
token after approval. Refresh cannot extend that token.

## CLI protocol

1. POST `/api/identity/login/start` with lowercase email and a base64url SHA256
   verifier challenge. The server returns an opaque request ID expiring in five
   minutes. The verifier stays in the starting CLI process.
2. Open `/l/<request>` and sign in with Google. Authenticated POST
   `/api/identity/login/approve` checks the account matches the request and shows a
   twelve-character code once. An approved request cannot be approved again.
3. POST `/api/identity/login/redeem` with request, code and verifier. A transaction
   checks expiry, both secrets and disabled state, consumes the request, and
   issues a random shared session. Five incorrect attempts exhaust the request;
   concurrent redemption succeeds once. Only token/code hashes are persisted.
4. POST `/api/identity/assertion` with `Authorization: Bearer <shared token>` and
   an exact `audience`: `https://wiki.pocketcontext.com` or
   `https://notify.pocketcontext.com`. Each request checks the current account,
   token-key generation, idle expiry and absolute expiry before signing.
5. Exchange that assertion at the application's
   `/api/context/auth-with-assertion`. The application preserves its own account,
   disabled state and membership authorization. Identity admission grants no wiki
   space membership.

Shared sessions have seven-day idle and thirty-day absolute limits. POST
`/api/identity/session` validates/renews idle expiry; POST `/api/identity/logout`
revokes the selected shared session. Protocol collections have locked REST rules
and are absent from SQL exports. Expired records are removed hourly after an
additional day; they contain no reusable cleartext code/session secrets.

Assertions use RS256, with an OCI key-version OCID as `kid`. Claims are `iss`,
`sub`, `email`, boolean `email_verified`, `hd`, exact `aud`, integer `iat`, `nbf`,
`exp` and random single-use `jti`. Lifetime is sixty seconds. The application caps
its own token at assertion `iat + 900` and prevents refresh from extending that
expiry. An explicit central disable therefore stops new assertions immediately
and bounds previously issued assertion access to fifteen minutes. Requests
already running can finish.

`/.well-known/jwks.json` publishes configured current and retained previous
verification keys. Signing uses a dedicated OCI principal with only key-specific
sign/read permissions, a standard shared vault, and an HSM RSA3072 key. The HSM
private key is never exported. API authentication credentials remain private.
KMS failures fail closed; clients do not silently fall back to another login.

## Client contract

The `pocketcontext-identity` Python package exports `IdentityError`,
`NoSessionError`, `login(email, no_browser=False, timeout=180)`,
`assertion(email, audience)` and `logout(email)`. Login reuses a validated shared
session when possible. Assertion renewal never opens a browser. Production
issuer and pilot audiences are fixed; HTTP redirects never forward credentials.
The package uses Python's standard library and runs on Linux and macOS.

Shared sessions live under `$XDG_STATE_HOME/pocketcontext-id/` (default
`~/.local/state/pocketcontext-id/`) in issuer/email-hashed files. Directories have
mode 0700, files 0600, symlink state paths are rejected. Files are replaced
atomically. Codes, verifiers and Google tokens are not persisted. Application
`default.json` and application token files remain application-owned.

Application logout deletes that application's token. `identitycontext logout
--email you@pocketcontext.com` additionally revokes the shared session. Explicit
per-app `login --google` remains an independent fallback requiring its existing
SSH loopback tunnel when remote. Complete offboarding must disable those app
accounts as well. No automatic downgrade follows central rejection or outage.

## Recovery and rotation

Database replicas include identities, revocations and hashed sessions. Keep the
replica private and use one writer. Restoring stale state may restore old account
or session status: before reopening a recovered identity service, revoke all
restored shared sessions and rotate all restored user token keys through
operator REST writes, then reapply the current offboarding list. Never treat an
old replica as authoritative for recent revocations. Fresh Google login is then
required. Recovery must not create another writer on the live replica.

To rotate KMS, create a new HSM key version, publish its public key before issuing
assertions with it, retain the previous version in
`IDENTITYCONTEXT_KMS_PREVIOUS_KEY_VERSION_IDS`, update the current version, and
verify both versions during the overlap. Wait at least the verifier cache window
plus assertion lifetime before retiring an old public key. Never schedule key or
vault deletion as part of application removal. Preserve KMS ownership metadata
independently of application database backups.
