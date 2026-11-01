import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from cryptography.hazmat.primitives.asymmetric import rsa,padding,utils
from cryptography.hazmat.primitives import hashes,serialization

spec=importlib.util.spec_from_file_location('signer',Path(__file__).resolve().parents[1]/'docker/signer.py');signer=importlib.util.module_from_spec(spec);spec.loader.exec_module(signer)


class Signing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    def setUp(self):
        self.env=patch.dict(os.environ,{'IDENTITYCONTEXT_KMS_KEY_VERSION_ID':'version1','IDENTITYCONTEXT_KMS_KEY_ID':'key1','IDENTITYCONTEXT_KMS_PREVIOUS_KEY_VERSION_IDS':''});self.env.start();self.addCleanup(self.env.stop)
        self.claims={'iss':'https://id.pocketcontext.com','sub':'synthetic','email':'synthetic@pocketcontext.com','email_verified':True,'hd':'pocketcontext.com','aud':'https://wiki.pocketcontext.com','iat':int(time.time()),'nbf':int(time.time()),'exp':int(time.time())+60,'jti':'r'*32}
        self.oci=SimpleNamespace(key_management=SimpleNamespace(models=SimpleNamespace(SignDataDetails=lambda **kwargs:SimpleNamespace(**kwargs))))
    def test_rsa_digest_contract_round_trip(self):
        def sign(details):
            self.assertEqual(details.signing_algorithm,'SHA_256_RSA_PKCS1_V1_5');self.assertEqual(details.message_type,'DIGEST')
            signature=self.key.sign(base64.b64decode(details.message),padding.PKCS1v15(),utils.Prehashed(hashes.SHA256()))
            return SimpleNamespace(data=SimpleNamespace(key_version_id='version1',signature=base64.b64encode(signature).decode()))
        with patch.dict(sys.modules,{'oci':self.oci}):
            for audience in ('https://wiki.pocketcontext.com','https://notify.pocketcontext.com','https://tasks.pocketcontext.com','https://crm.pocketcontext.com','https://vault.pocketcontext.com'):
                jwt=signer.sign({**self.claims,'aud':audience},SimpleNamespace(sign=sign))
                header,payload,signature=jwt.split('.')
                self.key.public_key().verify(base64.urlsafe_b64decode(signature+'='*(-len(signature)%4)),(header+'.'+payload).encode(),padding.PKCS1v15(),hashes.SHA256())
                self.assertEqual(json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))['aud'],audience)
        header,payload,signature=jwt.split('.')
        self.key.public_key().verify(base64.urlsafe_b64decode(signature+'='*(-len(signature)%4)),(header+'.'+payload).encode(),padding.PKCS1v15(),hashes.SHA256())
        self.assertEqual(json.loads(base64.urlsafe_b64decode(header+'='*(-len(header)%4)))['kid'],'version1')
    def test_rejects_bad_claims_before_signing(self):
        crypto=Mock()
        for changes in ({'aud':'https://evil.example'},{'email_verified':'true'},{'exp':self.claims['iat']+61},{'iat':self.claims['iat']-100},{'hd':'evil.example'}):
            with patch.dict(sys.modules,{'oci':self.oci}),self.assertRaises(ValueError):signer.sign({**self.claims,**changes},crypto)
        crypto.sign.assert_not_called()
    def test_rotation_publishes_only_configured_public_keys(self):
        pem=self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        management=Mock();management.get_key_version.return_value=SimpleNamespace(data=SimpleNamespace(public_key=pem))
        with patch.dict(os.environ,{'IDENTITYCONTEXT_KMS_PREVIOUS_KEY_VERSION_IDS':'version0'}):result=signer.jwks(management)
        self.assertEqual([key['kid'] for key in result['keys']],['version1','version0'])
        self.assertEqual(int.from_bytes(base64.urlsafe_b64decode(result['keys'][0]['e']+'=='),'big'),65537)
        self.assertNotIn('PRIVATE',json.dumps(result))
    def test_signing_process_capacity_is_bounded_and_released(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(signer.tempfile,'gettempdir',return_value=temporary):
            first=signer.acquire_slot();second=signer.acquire_slot()
            try:
                with self.assertRaises(ValueError):signer.acquire_slot()
                os.close(first);first=None
                third=signer.acquire_slot();os.close(third)
            finally:
                if first is not None:os.close(first)
                os.close(second)
    def test_wrong_key_version_fails_closed(self):
        crypto=Mock();crypto.sign.return_value=SimpleNamespace(data=SimpleNamespace(key_version_id='wrong',signature='bad'))
        with patch.dict(sys.modules,{'oci':self.oci}),self.assertRaises(ValueError):signer.sign(self.claims,crypto)

if __name__=='__main__':unittest.main()
