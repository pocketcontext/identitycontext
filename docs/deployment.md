# Deployment

Deploy only through the private `pocketdeploy-v2` scaffold on its existing host.
Image: `ghcr.io/pocketcontext/identitycontext`. Origin: `https://id.pocketcontext.com`.
Use `stop-first`, one database/Litestream writer, persistent `/storage`, port80,
database-backed `/up`, disabled ONCE automatic updates and a300-second graceful
stop allowance. ONCE's fixed startup readiness window remains120 seconds.

The service intentionally uses the tested server revision recorded in
`POCKETCONTEXT_VERSION`. The assertion-exchange server revision is required by
the two consuming applications, not by this issuer.

## Private configuration

Scaffold bindings must be app-specific `COLORS_PAR_APP_IDENTITYCONTEXT_*` variables
in its ignored mode0600 `.envrc.private`. Never commit or log values. The container
consumes:

- `BASE_URL=https://id.pocketcontext.com`;
- `IDENTITYCONTEXT_GOOGLE_CLIENT_ID`, `IDENTITYCONTEXT_GOOGLE_CLIENT_SECRET`,
  `IDENTITYCONTEXT_GOOGLE_WORKSPACE_DOMAIN=pocketcontext.com`;
- `IDENTITYCONTEXT_TRUSTED_PROXY_HEADER=X-Forwarded-For` and rate limits enabled;
- paired `IDENTITYCONTEXT_SUPERUSER_EMAIL`, `IDENTITYCONTEXT_SUPERUSER_PASSWORD`
  for initial operator provisioning; ordinary clients never receive them;
- `LITESTREAM_BUCKET`, `LITESTREAM_PATH`, `LITESTREAM_REGION=auto`,
  `LITESTREAM_ENDPOINT`, `LITESTREAM_ACCESS_KEY_ID`,
  `LITESTREAM_SECRET_ACCESS_KEY` for a dedicated private R2 replica;
- `IDENTITYCONTEXT_OCI_TENANCY_ID`, `IDENTITYCONTEXT_OCI_USER_ID`,
  `IDENTITYCONTEXT_OCI_FINGERPRINT`, `IDENTITYCONTEXT_OCI_REGION`,
  `IDENTITYCONTEXT_OCI_PRIVATE_KEY` for the dedicated limited signing principal;
- `IDENTITYCONTEXT_KMS_KEY_ID`, `IDENTITYCONTEXT_KMS_KEY_VERSION_ID`,
  `IDENTITYCONTEXT_KMS_CRYPTO_ENDPOINT`,
  `IDENTITYCONTEXT_KMS_MANAGEMENT_ENDPOINT`; optionally comma-separated
  `IDENTITYCONTEXT_KMS_PREVIOUS_KEY_VERSION_IDS` during rotation.

PocketDeploy owns the standard shared OCI vault, HSM RSA3072 key, dedicated IAM
principal/policy and generated API authentication key. The service cannot create,
rotate, disable or delete the signing key. JWKS is fetched once at bootstrap and
kept in memory; public requests never trigger a subprocess or OCI call. Each
signing process has a twenty-second limit and only two OCI signing processes may
run concurrently. Excess requests fail closed. No HSM signing key material is
exported. The signer dependencies are hash-pinned in
`docker/requirements-signing.txt`.

Register the separate Internal Google Web client with exactly
`https://id.pocketcontext.com/api/oauth2-redirect`. Scopes are `openid email
profile`. The normal hosted CLI flow has no localhost callback. Keep the pilot
apps' existing Google clients/redirects for explicit fallback.

## First deployment and recovery

The image's default `start` requires an existing local database or recoverable
replica. `init` is an explicit one-shot action accepting only an empty volume and
an absent replica; it refuses an existing replica. Do not use init as a retry for
an unknown or damaged instance.

For the first deployment, seed the new dedicated replica on the target host:

1. Create a uniquely named, labeled temporary volume, using the exact tested
   image digest and private environment bindings. Run that image with `init` and
   this volume at `/storage`. This applies migrations and provisions the operator.
2. Start the same image normally on the same volume, with no public port. Wait for
   database health and the initial Litestream synchronization. Stop cleanly and
   verify exit status and absence of a writer.
3. Converge the scaffold's new app. Its normal startup restores the dedicated
   replica into its ONCE-owned volume. Verify one writer, public HTTPS health,
   serving image revision/digest, cached JWKS and nonempty replica objects before
   enabling GitHub delivery. Preserve the seed volume until this succeeds.

This sequence is covered by the isolated container restore test. No ordinary
users exist at bootstrap. A later replica recovery automatically disables all
restored ordinary accounts and revokes every restored shared session before
serving. This prevents stale backup state from reversing recent offboarding.
Operators must selectively reactivate eligible accounts, then users sign in
fresh. The marker persists until the transactional reset succeeds. Normal
container restart on an existing volume preserves active accounts/sessions.

There are no application file fields or uploaded originals. Recovery verifies
SQLite integrity and required identity schema and refuses unexpected file fields.
The replica contains sensitive identities, account hashes, OAuth settings and
hashed sessions, so its bucket must remain private. A restored copy never writes
to the live replica alongside production. Roll back only to an image compatible
with the current schema, with the current writer stopped first.

## Release gates

Run unit tests, HTTP protocol/revocation tests, adversarial synthetic Google
provider tests and actual browser tests documented in README. Native AMD64 and
ARM64 container CI runs missing-config rejection, persistent restart and populated
replica recovery before publishing the multi-architecture image. It uses a pinned
MinIO source fixture and replaces only the external signer in disposable tests.
No test flag bypasses signing in the production application.

The CI deploy job stays disabled until `COLORS_PROFILE=pocketdeploy-v2` is set
following verified initial deployment. It uses the scaffold's restricted SSH key,
pinned host key and current-main guard. Public `/up` alone does not prove the
source revision: inspect only allowlisted image digest/revision fields separately.
A live human Google login and a real KMS signing/verification probe remain
production acceptance checks; local provider/signing mocks do not establish them.

## Litestream cleanup frequency

The image checks for expired L0 files every five minutes
(`l0-retention-check-interval: 5m`) to reduce object-store listing requests.
This delays cleanup and can temporarily retain more local and remote files; it
does not change the default ten-second replication interval, compaction schedule,
minimum L0 retention or snapshot history. Successful L1 compaction can also run
cleanup. Container smoke checks verify the effective interval, and populated
restore checks remain release gates.
