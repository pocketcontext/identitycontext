---
name: identitycontext
description: Authenticate hosted Context application CLIs through id.pocketcontext.com and inspect or revoke the local shared identity session. Pilot applications are WikiContext and NotifyContext. Does not grant application memberships or replace operator account administration.
---

# IdentityContext

Run the self-contained `identitycontext` launcher in this directory with uv:

```sh
/path/to/skill/identitycontext login --email you@pocketcontext.com
/path/to/skill/identitycontext whoami --email you@pocketcontext.com
/path/to/skill/identitycontext logout --email you@pocketcontext.com
```

Login opens the default browser unless SSH is detected or `--no-browser` is set.
On SSH, open the printed HTTPS URL on the browser computer; no port forward is
needed. The human completes Google sign-in and pastes the displayed code into the
waiting CLI. Never drive Google sign-in or copy the code into logs. The command
waits 180 seconds by default; `--timeout` permits up to600 seconds. Run it in a
terminal/background process whose tool timeout permits the human step.

Successful sign-in caches only a revocable identity session under
`~/.local/state/pocketcontext-id/` (or `$XDG_STATE_HOME/pocketcontext-id/`), with
private permissions. WikiContext and NotifyContext can reuse it. Session renewal
never opens a browser automatically. The server limits idle life to seven days
and absolute life to thirty days. Application authorization remains independent.

Application `logout` removes only its own token. This skill's `logout` revokes the
shared session before deleting it locally; an unavailable server leaves the file
so revocation can be retried. Already issued application tokens remain bounded
by their fifteen-minute expiry. Explicit app `login --google` is an independent
fallback; it is never selected automatically after an identity rejection.

An operator disables an account using the IdentityContext dashboard's `users`
record `disabled` field or its maintenance REST API. Ordinary agent credentials
cannot administer accounts. Complete offboarding must also disable fallback app
accounts. Do not seek operator credentials merely to resolve missing access.
