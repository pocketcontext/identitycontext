const ORIGIN = 'https://id.pocketcontext.com';
const AUDIENCES = ['https://wiki.pocketcontext.com','https://notify.pocketcontext.com'];
function now(){return Math.floor(Date.now()/1000);}
function hash(value){return $security.sha256(value);}
function input(e){
  const data=e.requestInfo().body;
  if (!data || typeof data!=='object') throw new BadRequestError('Invalid request.');
  return data;
}
function email(value){
  if(typeof value!=='string'||value.length>254||! /^[^\s@]+@pocketcontext\.com$/i.test(value)) throw new BadRequestError('A pocketcontext.com Workspace email is required.');
  return value.toLowerCase();
}
function safe(e){
 e.response.header().set('Cache-Control','no-store');
 e.response.header().set('Referrer-Policy','no-referrer');
 e.response.header().set('X-Content-Type-Options','nosniff');
}
function start(e){
 safe(e);const data=input(e),identity=email(data.email);
 if(typeof data.challenge!=='string'||! /^[A-Za-z0-9_-]{43}$/.test(data.challenge)) throw new BadRequestError('Invalid verifier challenge.');
 const record=new Record(e.app.findCollectionByNameOrId('identity_requests'));
 record.set('email',identity);record.set('challenge',data.challenge);record.set('expires',now()+300);
 e.app.save(record);
 return e.json(200,{request:record.id,expires_in:300});
}
function approve(e){
 safe(e);const data=input(e);
 if(!e.auth||e.auth.collection().name!=='users'||!e.auth.getBool('verified')||e.auth.getBool('disabled')) throw new UnauthorizedError('Sign in with Google first.');
 let code='';
 e.app.runInTransaction(tx=>{
   const record=tx.findRecordById('identity_requests',String(data.request||''));
   const user=tx.findRecordById('users',e.auth.id);
   if(user.getBool('disabled')||user.tokenKey()!==e.auth.tokenKey()||record.getBool('used')||record.getInt('expires')<=now()||record.getString('code_hash')) throw new ForbiddenError('Sign-in request is expired or already approved.');
   if(email(user.getString('email'))!==record.getString('email')) throw new ForbiddenError('The Google account does not match the terminal request.');
   code=$security.randomStringWithAlphabet(12,'ABCDEFGHJKLMNPQRSTUVWXYZ23456789');
   record.set('code_hash',hash(code));record.set('account_key_hash',hash(user.tokenKey()));record.set('subject',user.id);tx.save(record);
 });
 return e.json(200,{code:code,expires_in:300});
}
function redeem(e){
 safe(e);const data=input(e);
 if(typeof data.verifier!=='string'||! /^[A-Za-z0-9_-]{43,128}$/.test(data.verifier)||typeof data.code!=='string'||! /^[A-Z2-9]{12}$/.test(data.code)) throw new BadRequestError('Invalid code or verifier.');
 let result=null,invalid=false;
 e.app.runInTransaction(tx=>{
   const request=tx.findRecordById('identity_requests',String(data.request||''));
   if(request.getBool('used')||request.getInt('expires')<=now()||request.getInt('attempts')>=5) throw new UnauthorizedError('Sign-in request expired or already consumed.');
   // sha256 returns hex; PKCE requires base64url of digest bytes.
   const digest=hash(data.verifier);let bytes=[];
   for(let i=0;i<digest.length;i+=2) bytes.push(parseInt(digest.slice(i,i+2),16));
   const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';let challenge='';let bits=0,acc=0;for(const b of bytes){acc=(acc<<8)|b;bits+=8;while(bits>=6){bits-=6;challenge+=alphabet[(acc>>>bits)&63];}}if(bits)challenge+=alphabet[(acc<<(6-bits))&63];
   if(challenge!==request.getString('challenge')||hash(data.code)!==request.getString('code_hash')){
      request.set('attempts',request.getInt('attempts')+1);tx.save(request);invalid=true;return;
   }
   const user=tx.findRecordById('users',request.getString('subject'));
   if(user.getBool('disabled')||!user.getBool('verified')||hash(user.tokenKey())!==request.getString('account_key_hash')||email(user.getString('email'))!==request.getString('email')) throw new ForbiddenError('Account is unavailable.');
   const token=$security.randomString(64),session=new Record(tx.findCollectionByNameOrId('identity_sessions'));
   session.set('token_hash',hash(token));session.set('subject',user.id);session.set('account_key_hash',hash(user.tokenKey()));
   session.set('expires',now()+30*86400);session.set('idle_expires',now()+7*86400);tx.save(session);
   request.set('used',true);request.set('code_hash','');tx.save(request);
   result={token:token,email:email(user.getString('email')),subject:user.id,expires:session.getInt('expires'),idle_expires:session.getInt('idle_expires')};
 });
 if(invalid)throw new UnauthorizedError('Invalid code or verifier.');
 return e.json(200,result);
}
function withSession(e,callback,touch){
 const authorization=e.request.header.get('Authorization')||'';
 if(!/^Bearer [A-Za-z0-9]{64}$/.test(authorization)) throw new UnauthorizedError('A shared identity session is required.');
 let result;
 e.app.runInTransaction(tx=>{
  let sessions=tx.findRecordsByFilter('identity_sessions','token_hash = {:hash}','',1,0,{hash:hash(authorization.slice(7))});
  if(!sessions.length)throw new UnauthorizedError('Identity session is invalid.');
  const session=sessions[0],user=tx.findRecordById('users',session.getString('subject'));
  if(session.getBool('revoked')||session.getInt('expires')<=now()||session.getInt('idle_expires')<=now()||user.getBool('disabled')||!user.getBool('verified')||session.getString('account_key_hash')!==hash(user.tokenKey()))throw new UnauthorizedError('Identity session is expired or revoked.');
  email(user.getString('email'));
  result=callback(tx,session,user);
  if(touch){session.set('idle_expires',Math.min(now()+7*86400,session.getInt('expires')));tx.save(session);}
 });
 return result;
}
function session(e){safe(e);return e.json(200,withSession(e,(_,s,u)=>({email:email(u.getString('email')),subject:u.id,expires:s.getInt('expires'),idle_expires:s.getInt('idle_expires')}),true));}
function logout(e){safe(e);withSession(e,(tx,s)=>{s.set('revoked',true);tx.save(s);},false);return e.json(200,{revoked:true});}
function sign(payload){
 const cmd=$os.cmd('python3','-I',__hooks+'/../docker/signer.py','sign');
 const reader=$filesystem.fileFromBytes(toBytes(JSON.stringify(payload)),'claims.json').reader.open();cmd.stdin=reader;
 try{return toString(cmd.output()).trim();}catch(_){throw new ApiError(503,'Identity signing is unavailable.',{});}finally{reader.close();}
}
function assertion(e){
 safe(e);const data=input(e);
 if(!AUDIENCES.includes(data.audience))throw new BadRequestError('Unsupported application audience.');
 // Renew within the transaction, then sign outside it; never hold SQLite while KMS responds.
 const claims=withSession(e,(_,s,u)=>({iss:ORIGIN,sub:u.id,email:email(u.getString('email')),email_verified:true,hd:'pocketcontext.com',aud:data.audience,iat:now(),nbf:now(),exp:now()+60,jti:$security.randomString(32)}),true);
 return e.json(200,{assertion:sign(claims),expires_in:60});
}
function warmKeys(app){
 try{const cmd=$os.cmd('python3','-I',__hooks+'/../docker/signer.py','jwks');const value=JSON.parse(toString(cmd.output()));if(!Array.isArray(value.keys))throw new Error();app.store().set('identityJWKS',JSON.stringify(value));}catch(_){throw new Error('Identity verification keys could not be loaded; startup stopped.');}
}
function jwks(e){
 e.response.header().set('Cache-Control','public, max-age=60');
 const cached=e.app.store().get('identityJWKS');
 if(!cached)throw new ApiError(503,'Identity verification keys are unavailable.',{});
 return e.json(200,JSON.parse(cached));
}
function page(e){
 safe(e);e.response.header().set('Content-Security-Policy',"default-src 'self'; script-src 'self'; connect-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
 return e.html(200,toString($os.readFile(__hooks+'/../pb_public/login.html')));
}
module.exports={start,approve,redeem,session,logout,assertion,jwks,page,warmKeys};
