#!/usr/bin/env python3
"""Synthetic isolated container startup, one-writer persistence and recovery gates."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def command(*args,env=None,check=True,timeout=180):
    result=subprocess.run(['docker',*args],env={**os.environ,**(env or {})},capture_output=True,text=True,timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('Docker '+args[0]+' failed; synthetic fixture output withheld')
    return result


def http(url,path,body=None,token=None,method=None,expected=200):
    req=urllib.request.Request(url+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'Authorization':token} if token else {})},method=method)
    try:response=urllib.request.urlopen(req,timeout=15)
    except urllib.error.HTTPError as error:response=error
    if response.status!=expected:raise AssertionError('Unexpected HTTP status for '+path+': '+str(response.status))
    raw=response.read()
    try:return json.loads(raw)
    except ValueError:return raw.decode()


def url(name,port):
    value=command('port',name,str(port)).stdout.strip().splitlines()[0]
    return 'http://'+value


def ready(name,port=80,path='/up'):
    address=url(name,port)
    for _ in range(120):
        try:
            http(address,path);return address
        except (OSError,AssertionError):time.sleep(1)
    raise RuntimeError('Synthetic container did not become ready within120 seconds')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['config','smoke','restore']);parser.add_argument('--image',required=True);parser.add_argument('--minio-image',default='identitycontext-minio-fixture:9e49d5e-7394ce0');args=parser.parse_args()
    if args.mode=='config':
        result=command('run','--rm',args.image,check=False)
        assert result.returncode!=0 and 'missing required replica configuration' in result.stderr
        print('PASS: missing replica configuration fails closed');return
    if command('image','inspect',args.minio_image,'--format','{{.Id}}',check=False).returncode:
        command('build','-f',str(ROOT/'docker/minio.Dockerfile'),'-t',args.minio_image,str(ROOT/'docker'),timeout=1200)
    prefix='idtest-'+secrets.token_hex(5);network=prefix+'-net';s3=prefix+'-s3';app=prefix+'-app';volume=prefix+'-db'
    password=secrets.token_urlsafe(24)
    env={'MINIO_ROOT_USER':'synthetic','MINIO_ROOT_PASSWORD':password,
         'LITESTREAM_BUCKET':'replica','LITESTREAM_PATH':'identity','LITESTREAM_REGION':'us-east-1','LITESTREAM_ENDPOINT':'http://s3:9000','LITESTREAM_SYNC_INTERVAL':'1s','LITESTREAM_ACCESS_KEY_ID':'synthetic','LITESTREAM_SECRET_ACCESS_KEY':password,
         'IDENTITYCONTEXT_SUPERUSER_EMAIL':'admin@example.test','IDENTITYCONTEXT_SUPERUSER_PASSWORD':password,'IDENTITYCONTEXT_RATE_LIMITS':'false','BASE_URL':'https://id.pocketcontext.com'}
    flags=[item for name in env for item in ('-e',name)]
    try:
        command('network','create',network)
        command('run','-d','--name',s3,'--network',network,'--network-alias','s3','-p','127.0.0.1::9000','-e','MINIO_ROOT_USER','-e','MINIO_ROOT_PASSWORD',args.minio_image,'server','/data',env=env)
        ready(s3,9000,'/minio/health/live')
        command('run','--rm','--network',network,'-e','MC_HOST_fixture','--entrypoint','mc',args.minio_image,'mb','fixture/replica',env={'MC_HOST_fixture':'http://synthetic:'+password+'@s3:9000'})
        command('volume','create',volume)
        with tempfile.TemporaryDirectory(prefix='identity-signer-fixture-') as temporary:
            fixture=Path(temporary)/'signer.py';fixture.write_text('import json,sys\nprint(json.dumps({"keys":[]}) if sys.argv[1]=="jwks" else "header.payload.signature")\n');fixture.chmod(0o644)
            mount=['--mount','type=bind,src='+str(fixture)+',dst=/app/docker/signer.py,readonly']
            common=['--network',network,'-v',volume+':/storage',*mount,*flags]
            command('run','--rm',*common,args.image,'init',env=env)
            def start():
                command('run','-d','--name',app,'-p','127.0.0.1::80',*common,args.image,env=env)
                return ready(app)
            address=start()
            def admin_token():return http(address,'/api/collections/_superusers/auth-with-password',{'identity':'admin@example.test','password':password})['token']
            admin=admin_token()
            user=http(address,'/api/collections/users/records',{'email':'synthetic@pocketcontext.com','name':'Synthetic User','verified':True,'password':password,'passwordConfirm':password},admin)
            browser=http(address,'/api/collections/users/impersonate/'+user['id'],{'duration':300},admin)['token']
            verifier='v'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            request=http(address,'/api/identity/login/start',{'email':'synthetic@pocketcontext.com','challenge':challenge})['request']
            code=http(address,'/api/identity/login/approve',{'request':request},browser)['code']
            session=http(address,'/api/identity/login/redeem',{'request':request,'code':code,'verifier':verifier})['token']
            http(address,'/api/identity/session',{},'Bearer '+session)
            command('stop','-t','60',app);command('rm',app)
            if args.mode=='restore':
                command('volume','rm',volume);command('volume','create',volume)
            address=start();admin=admin_token()
            restored=http(address,'/api/collections/users/records/'+user['id'],token=admin)
            assert restored['disabled']==(args.mode=='restore')
            http(address,'/api/identity/session',{},'Bearer '+session,expected=401 if args.mode=='restore' else 200)
            if args.mode=='restore':
                http(address,'/api/collections/users/records/'+user['id'],{'disabled':False},admin,method='PATCH')
                http(address,'/api/identity/session',{},'Bearer '+session,expected=401)
            command('stop','-t','60',app)
        print('PASS: synthetic container '+args.mode+' and shared-session recovery boundary')
    finally:
        for name in (app,s3):command('rm','-f',name,check=False)
        command('volume','rm',volume,check=False);command('network','rm',network,check=False)

if __name__=='__main__':main()
