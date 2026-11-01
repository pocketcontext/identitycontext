# IdentityContext

Hosted CLI sign-in for WikiContext and NotifyContext at https://id.pocketcontext.com. IdentityContext uses PocketContext and its default users collection. Read docs/protocol.md for the protocol and deployment contract.

## Develop and validate

Install with `uv pip install -e .` or build with `uv build`. The client command is
`identitycontext login --email you@pocketcontext.com`; `whoami` and `logout` take
that same explicit email. The reusable library powers the two pilot app clients.

Build the server commit in `POCKETCONTEXT_VERSION` using its documented Go/CGO
commands. Run from this application directory with isolated storage:

```sh
/path/to/pocketcontext serve --dir /private/path/pb_data --http 127.0.0.1:8097
python3 -m unittest discover -s tests -v
python3 tests/integration.py --binary /path/to/pocketcontext
python3 tests/oauth_integration.py --binary /path/to/pocketcontext
```

Tests use synthetic accounts, temporary databases, a local Google provider
fixture and a mocked external signing boundary. They never call live Google or
OCI signing. Production OAuth and HSM verification are separate deployment gates.

Default-users authentication hooks were adapted from RaiseContext; the hosted
identity protocol and client are independent. The browser vendors PocketBase SDK
0.28.1 under its MIT license in `pb_public/POCKETBASE-LICENSE.md`.
