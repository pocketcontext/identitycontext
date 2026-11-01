"""Private shared sessions for the hosted Context identity service.

No provider tokens, automatic browser renewal or automatic fallback authentication.
"""
import base64
import getpass
import functools
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser

ORIGIN = 'https://id.pocketcontext.com'
AUDIENCES = {'https://wiki.pocketcontext.com', 'https://notify.pocketcontext.com'}


class IdentityError(Exception):
    """Safe diagnostic which never includes response bodies or tokens."""


class NoSessionError(IdentityError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _request(path, data, token=None, timeout=30):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
               'User-Agent': 'pocketcontext-identity/0.1'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(ORIGIN + path, json.dumps(data).encode(), headers)
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise IdentityError('Identity server returned an oversized response.')
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise NoSessionError('Identity session is expired, disabled or revoked; run login again.') from None
        raise IdentityError('Identity server rejected the request (HTTP %d).' % error.code) from None
    except (OSError, ValueError, urllib.error.URLError):
        raise IdentityError('Identity server is unavailable or returned an invalid response.') from None


def _email(email):
    if not isinstance(email, str) or len(email) > 254 or not email.strip() or email.count('@') != 1:
        raise IdentityError('A valid Workspace email is required.')
    return email.strip().lower()


def _directory():
    root = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'pocketcontext-id'
    root = root.absolute()
    for part in reversed([root, *root.parents]):
        try:
            info = part.lstat()
        except FileNotFoundError:
            part.mkdir(mode=0o700)
            info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise IdentityError('Identity state path must contain only real directories.')
    if root.stat().st_uid != os.getuid():
        raise IdentityError('Identity state directory belongs to another user.')
    root.chmod(0o700)
    return root


def _path(email):
    return _directory() / (hashlib.sha256((ORIGIN + '\n' + _email(email)).encode()).hexdigest() + '.json')


def _read(email):
    path = _path(email)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 16384:
                raise IdentityError('Identity session file has unsafe ownership, permissions or size.')
            value = json.load(stream)
    except FileNotFoundError:
        raise NoSessionError('No shared identity session; run login.') from None
    except (OSError, ValueError):
        raise IdentityError('Cannot read the private identity session.') from None
    if (not isinstance(value, dict) or value.get('issuer') != ORIGIN or value.get('email') != _email(email)
            or not isinstance(value.get('token'), str) or not 32 <= len(value['token']) <= 256):
        raise IdentityError('Stored identity session is invalid.')
    return value


def _save(email, value):
    path = _path(email)
    value = {**value, 'issuer': ORIGIN, 'email': _email(email)}
    fd, temporary = tempfile.mkstemp(prefix='.session-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_io(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except OSError:
            raise IdentityError('Cannot access private identity state or terminal input.') from None
    return wrapped


@_safe_io

def login(email, *, no_browser=False, timeout=180):
    """Reuse an active session or interactively sign in. Return safe account details."""
    email = _email(email)
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600:
        raise IdentityError('Login timeout must be between 1 and 600 seconds.')
    try:
        existing = _read(email)
        account = _request('/api/identity/session', {}, existing['token'])
        if account.get('email') != email:
            raise IdentityError('Identity server returned a different account.')
        return account
    except NoSessionError:
        pass
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    started = _request('/api/identity/login/start', {'email': email, 'challenge': challenge})
    request_id = started.get('request', '')
    if not isinstance(request_id, str) or not request_id.isalnum() or not 15 <= len(request_id) <= 64:
        raise IdentityError('Identity server returned an invalid sign-in request.')
    url = ORIGIN + '/l/' + request_id
    print('Sign in: ' + url, file=sys.stderr, flush=True)
    opened = False
    if not no_browser and not os.environ.get('SSH_CONNECTION') and not os.environ.get('SSH_TTY'):
        try:
            opened = webbrowser.open(url)
        except webbrowser.Error:
            pass
    if not opened:
        print('Browser not opened. Open this URL on your browser computer; no SSH tunnel is needed.', file=sys.stderr)
    print('Paste the code shown after Google sign-in (expires in 5 minutes).', file=sys.stderr, flush=True)
    # select enforces the command timeout while leaving interactive terminal echo
    # disabled through getpass. No codes are written to history or normal stdout.
    import select
    if not sys.stdin.isatty():
        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        if not readable:
            raise IdentityError('Identity login timed out.')
        code = sys.stdin.readline().strip()
    else:
        import signal
        previous = signal.getsignal(signal.SIGALRM)
        def expired(*_):
            raise IdentityError('Identity login timed out.')
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(int(timeout))
        try:
            code = getpass.getpass('Code: ').strip()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
    result = _request('/api/identity/login/redeem', {'request': request_id, 'code': code, 'verifier': verifier})
    if result.get('email') != email or not isinstance(result.get('token'), str) or not 32 <= len(result['token']) <= 256:
        raise IdentityError('Identity server returned an invalid account/session.')
    _save(email, result)
    return {key: value for key, value in result.items() if key != 'token'}


@_safe_io
def assertion(email, audience):
    """Issue a single-use assertion; never prompt or fall back to Google/password."""
    if audience not in AUDIENCES:
        raise IdentityError('This application origin is outside the identity pilot.')
    session = _read(email)
    result = _request('/api/identity/assertion', {'audience': audience}, session['token'])
    token = result.get('assertion')
    if not isinstance(token, str) or len(token) > 16384 or token.count('.') != 2:
        raise IdentityError('Identity server returned an invalid assertion.')
    return token


@_safe_io
def logout(email):
    """Revoke the shared session on the server before deleting its local copy."""
    try:
        session = _read(email)
    except NoSessionError:
        return
    try:
        _request('/api/identity/logout', {}, session['token'])
    except NoSessionError:
        pass
    _path(email).unlink(missing_ok=True)
