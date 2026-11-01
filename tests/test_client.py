import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import pocketcontext_identity as identity


class Client(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env=patch.dict(os.environ,{'XDG_STATE_HOME':self.directory.name,'SSH_CONNECTION':'synthetic'})
        self.env.start();self.addCleanup(self.env.stop)
        self.email='synthetic@pocketcontext.com'

    def test_missing_session_never_prompts_or_networks(self):
        with patch.object(identity,'_request') as send,patch.object(identity.webbrowser,'open') as browser:
            with self.assertRaises(identity.NoSessionError):identity.assertion(self.email,'https://wiki.pocketcontext.com')
            send.assert_not_called();browser.assert_not_called()

    def test_private_storage_and_cache_identity_binding(self):
        identity._save(self.email,{'token':'x'*64})
        path=identity._path(self.email)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(path.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(identity._read(self.email)['token'],'x'*64)
        path.write_text(json.dumps({'token':'x'*64,'issuer':'https://evil.example','email':self.email}))
        with self.assertRaises(identity.IdentityError):identity._read(self.email)

    def test_rejects_symlink_and_world_readable_session(self):
        identity._save(self.email,{'token':'x'*64});path=identity._path(self.email)
        path.chmod(0o644)
        with self.assertRaises(identity.IdentityError):identity._read(self.email)
        path.unlink();path.symlink_to(Path(self.directory.name)/'other')
        with self.assertRaises(identity.IdentityError):identity._read(self.email)

    def test_explicit_login_reuses_shared_session_without_browser(self):
        identity._save(self.email,{'token':'x'*64})
        with patch.object(identity,'_request',return_value={'email':self.email,'subject':'synthetic'}) as send,patch.object(identity.webbrowser,'open') as browser:
            self.assertEqual(identity.login(self.email)['email'],self.email)
            self.assertEqual(send.call_args.args[0],'/api/identity/session');browser.assert_not_called()

    def test_network_failure_never_reauthenticates(self):
        identity._save(self.email,{'token':'x'*64})
        with patch.object(identity,'_request',side_effect=identity.IdentityError('unavailable')) as send:
            with self.assertRaises(identity.IdentityError):identity.login(self.email)
            self.assertEqual(send.call_count,1)

    def test_audience_rejected_before_reading_token(self):
        with patch.object(identity,'_read') as read:
            with self.assertRaises(identity.IdentityError):identity.assertion(self.email,'https://wiki.pocketcontext.com.evil.example')
            read.assert_not_called()

    def test_shared_session_issues_each_application_audience(self):
        identity._save(self.email,{'token':'x'*64})
        for audience in ('https://wiki.pocketcontext.com','https://notify.pocketcontext.com','https://tasks.pocketcontext.com','https://crm.pocketcontext.com','https://vault.pocketcontext.com'):
            with self.subTest(audience=audience),patch.object(identity,'_request',return_value={'assertion':'header.payload.signature'}) as send,patch.object(identity.webbrowser,'open') as browser:
                self.assertEqual(identity.assertion(self.email,audience),'header.payload.signature')
                send.assert_called_once_with('/api/identity/assertion',{'audience':audience},'x'*64)
                browser.assert_not_called()

    def test_logout_preserves_cache_when_revocation_uncertain(self):
        identity._save(self.email,{'token':'x'*64})
        with patch.object(identity,'_request',side_effect=identity.IdentityError('unavailable')):
            with self.assertRaises(identity.IdentityError):identity.logout(self.email)
        self.assertTrue(identity._path(self.email).exists())
        with patch.object(identity,'_request',return_value={'revoked':True}):identity.logout(self.email)
        self.assertFalse(identity._path(self.email).exists())

    def test_http_redirect_handler_never_forwards_bearer(self):
        self.assertIsNone(identity._NoRedirect().redirect_request(None,None,None,None,None,None))

    def test_login_binds_verifier_and_does_not_persist_code(self):
        responses=[{'request':'r'*15},{'email':self.email,'token':'s'*64,'subject':'synthetic'}]
        with patch.object(identity,'_request',side_effect=responses) as send,patch('select.select',return_value=([1],[],[])),patch.object(sys,'stdin',io.StringIO('ABCD23456789\n')),contextlib.redirect_stderr(io.StringIO()):
            identity.login(self.email,no_browser=True)
        challenge=send.call_args_list[0].args[1]['challenge'];verifier=send.call_args_list[1].args[1]['verifier']
        self.assertEqual(challenge,identity.base64.urlsafe_b64encode(identity.hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='))
        stored=identity._path(self.email).read_text()
        self.assertNotIn(verifier,stored);self.assertNotIn('ABCD23456789',stored)

if __name__=='__main__':unittest.main()
