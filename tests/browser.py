#!/usr/bin/env python3
"""Actual hosted browser assets against only a local synthetic Google provider."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import oauth_integration
from oauth_integration import google_fixture
from integration import server

parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True);args=parser.parse_args()
with google_fixture() as (provider,_),server(args.binary) as request:
    oauth_integration.REDIRECT=request.base_url+'/api/oauth2-redirect'
    admin=request('POST','/api/collections/_superusers/auth-with-password',{'identity':'admin@example.test','password':'SyntheticAdminPassword123!'})['token']
    request('PATCH','/api/collections/users',{'oauth2':{'enabled':True,'providers':[{'name':'google','clientId':'synthetic','clientSecret':'synthetic','authURL':provider+'/authorize','tokenURL':provider+'/token','userInfoURL':provider+'/userinfo'}]}},admin)
    verifier='b'*64
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    started=request('POST','/api/identity/login/start',{'email':'member@pocketcontext.com','challenge':challenge})
    result=subprocess.run(['node','tests/browser.mjs'],cwd=Path(__file__).resolve().parents[1],env={**os.environ,'ID_TEST_URL':request.base_url,'ID_TEST_REQUEST':started['request']},capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stderr
    code=json.loads(result.stdout)['code']
    session=request('POST','/api/identity/login/redeem',{'request':started['request'],'verifier':verifier,'code':code})
    assert session['email']=='member@pocketcontext.com'
print('PASS: hosted browser Google flow, mobile layout, keyboard and memory-only auth; local synthetic provider only')
