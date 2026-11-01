#!/usr/bin/env python3
"""Synthetic HTTP protocol, privacy, revocation and replay checks."""
import argparse
import base64
import concurrent.futures
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def server(binary):
    with tempfile.TemporaryDirectory(prefix='identitycontext-test-') as temporary:
        directory = Path(temporary)
        for item in ('pb_hooks', 'pb_migrations', 'pb_public', 'docker'):
            shutil.copytree(ROOT / item, directory / item)
        shutil.copy(ROOT / 'pocketcontext.json', directory)
        # Mock only external KMS in isolated app copy. Production has no test bypass.
        (directory/'docker/signer.py').write_text('import json,sys\nif sys.argv[1]=="jwks": print(json.dumps({"keys":[]}))\nelse: print("header."+__import__("base64").urlsafe_b64encode(sys.stdin.buffer.read()).decode().rstrip("=")+".signature")\n')
        common=[str(Path(binary).resolve()),'--dir',str(directory/'pb_data')]
        env={key:value for key,value in os.environ.items() if not key.startswith(('IDENTITYCONTEXT_','LITESTREAM_'))}
        env['IDENTITYCONTEXT_RATE_LIMITS']='false'
        result=subprocess.run(common+['superuser','upsert','admin@example.test','SyntheticAdminPassword123!'],cwd=directory,env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        with open(directory/'server.log','w+') as log:
            process=subprocess.Popen(common+['serve','--http',f'127.0.0.1:{port}'],cwd=directory,env=env,stdout=log,stderr=log)
            def request(method,path,body=None,token=None,expected=200):
                headers={'Content-Type':'application/json'}
                if token: headers['Authorization']=token
                req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
                try: response=urllib.request.urlopen(req,timeout=25)
                except urllib.error.HTTPError as error: response=error
                value=response.read()
                allowed=(expected,) if isinstance(expected,int) else expected
                if response.status not in allowed:
                    log.flush();log.seek(0)
                    raise AssertionError((path,response.status,value.decode(),log.read()[-4000:]))
                try:return json.loads(value)
                except ValueError:return value.decode()
            request.base_url=f'http://127.0.0.1:{port}'
            try:
                for _ in range(150):
                    try:request('GET','/up');break
                    except OSError: time.sleep(.1)
                    if process.poll() is not None:log.seek(0);raise AssertionError(log.read())
                else:raise AssertionError('Server startup timed out')
                yield request
            finally:
                process.terminate();process.wait(timeout=15)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True);args=parser.parse_args()
    with server(args.binary) as req:
        admin=req('POST','/api/collections/_superusers/auth-with-password',{'identity':'admin@example.test','password':'SyntheticAdminPassword123!'})['token']
        users=req('GET','/api/collections/users',token=admin)
        assert users['id']=='_pb_users_auth_' and not users['passwordAuth']['enabled'] and users['authToken']['duration']==300
        assert {c['name'] for c in req('GET','/api/collections',token=admin)['items'] if c['type']=='auth'}=={'users','_superusers'}
        req('POST','/api/collections/users/records',{'email':'synthetic@pocketcontext.com'},expected=(400,403))
        user=req('POST','/api/collections/users/records',{'email':'synthetic@pocketcontext.com','name':'Synthetic Member','verified':True,'password':'SyntheticUserPassword123!','passwordConfirm':'SyntheticUserPassword123!'},admin)
        token=req('POST','/api/collections/users/impersonate/'+user['id'],{'duration':300},admin)['token']
        req('POST','/api/collections/users/auth-with-password',{'identity':'synthetic@pocketcontext.com','password':'SyntheticUserPassword123!'},expected=(400,403))
        req('POST','/api/collections/users/auth-refresh',{},token,expected=403)
        req('GET','/api/context/schema',expected=401)
        schema=req('GET','/api/context/schema',token=token)
        assert 'identity_sessions' not in json.dumps(schema) and 'identity_requests' not in json.dumps(schema)
        for name in ('identity_sessions','identity_requests'):
            req('GET','/api/collections/'+name+'/records',token=token,expected=403)
        for endpoint in ('login/start','login/redeem','login/approve','assertion'):
            req('POST','/api/identity/'+endpoint,{'oversized':'x'*5000},token,expected=413)
        verifier='v'*64
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        def begin():
            start=req('POST','/api/identity/login/start',{'email':'synthetic@pocketcontext.com','challenge':challenge})
            approved=req('POST','/api/identity/login/approve',{'request':start['request']},token)
            return {'request':start['request'],'code':approved['code'],'verifier':verifier}
        payload=begin()
        req('POST','/api/identity/login/approve',{'request':payload['request']},token,expected=403)
        req('POST','/api/identity/login/redeem',{**payload,'verifier':'x'*64},expected=401)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:req('POST','/api/identity/login/redeem',payload,expected=(200,401)),range(2)))
        assert sum('token' in result for result in results)==1
        session=next(r for r in results if 'token' in r)
        shared='Bearer '+session['token']
        assert session['expires']-int(time.time())<=30*86400
        assert req('POST','/api/identity/session',{},shared)['email']=='synthetic@pocketcontext.com'
        for rejected in ('https://evil.example','https://tasks.pocketcontext.com.evil.example','http://crm.pocketcontext.com','https://vault.pocketcontext.com/','https://vault.pocketcontext.com:443'):
            req('POST','/api/identity/assertion',{'audience':rejected},shared,expected=400)
        for audience in ('https://wiki.pocketcontext.com','https://notify.pocketcontext.com','https://tasks.pocketcontext.com','https://crm.pocketcontext.com','https://vault.pocketcontext.com'):
            signed=req('POST','/api/identity/assertion',{'audience':audience},shared)['assertion']
            segment=signed.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(segment+'='*(-len(segment)%4)))
            assert claims['sub']==user['id'] and claims['exp']-claims['iat']==60 and claims['email_verified'] is True
            assert claims['aud']==audience and 'BEGIN' not in signed
        req('POST','/api/identity/logout',{},shared)
        req('POST','/api/identity/session',{},shared,expected=401)
        pending=begin()
        fresh=req('POST','/api/identity/login/redeem',begin())
        req('PATCH','/api/collections/users/records/'+user['id'],{'disabled':True},admin)
        req('POST','/api/identity/assertion',{'audience':'https://wiki.pocketcontext.com'},'Bearer '+fresh['token'],expected=401)
        req('PATCH','/api/collections/users/records/'+user['id'],{'disabled':False},admin)
        req('POST','/api/identity/session',{},'Bearer '+fresh['token'],expected=401)
        req('POST','/api/identity/login/redeem',pending,expected=403)
        token=req('POST','/api/collections/users/impersonate/'+user['id'],{'duration':300},admin)['token']
        unverified_pending=begin()
        req('PATCH','/api/collections/users/records/'+user['id'],{'verified':False},admin)
        req('PATCH','/api/collections/users/records/'+user['id'],{'verified':True},admin)
        req('POST','/api/identity/login/redeem',unverified_pending,expected=403)
        req('DELETE','/api/collections/users/records/'+user['id'],token=admin,expected=403)
        assert 'Sign in to PocketContext' in req('GET','/l/synthetic')
    print('PASS: hosted login binding/replay, isolated auth, private protocol storage and disable/re-enable revocation')

if __name__=='__main__':main()
