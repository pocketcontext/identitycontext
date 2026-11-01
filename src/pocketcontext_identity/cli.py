import argparse
import json
import sys
from . import IdentityError, _read, _request, login, logout


def main():
    parser = argparse.ArgumentParser(prog='identitycontext')
    parser.add_argument('command', choices=['login', 'whoami', 'logout'])
    parser.add_argument('--email', required=True)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    try:
        if args.command == 'login':
            result = login(args.email, no_browser=args.no_browser, timeout=args.timeout)
        elif args.command == 'logout':
            logout(args.email)
            result = {'revoked': True}
        else:
            result = _request('/api/identity/session', {}, _read(args.email)['token'])
        print(json.dumps(result))
    except KeyboardInterrupt:
        print('Identity command cancelled.', file=sys.stderr)
        return 130
    except (IdentityError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
