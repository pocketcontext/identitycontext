routerAdd('POST','/api/identity/login/start',e=>require(`${__hooks}/identity.js`).start(e));
routerAdd('POST','/api/identity/login/approve',e=>require(`${__hooks}/identity.js`).approve(e),$apis.requireAuth('users'));
routerAdd('POST','/api/identity/login/redeem',e=>require(`${__hooks}/identity.js`).redeem(e));
routerAdd('POST','/api/identity/session',e=>require(`${__hooks}/identity.js`).session(e));
routerAdd('POST','/api/identity/assertion',e=>require(`${__hooks}/identity.js`).assertion(e));
routerAdd('POST','/api/identity/logout',e=>require(`${__hooks}/identity.js`).logout(e));
routerAdd('GET','/.well-known/jwks.json',e=>require(`${__hooks}/identity.js`).jwks(e));
routerAdd('GET','/l/{request}',e=>require(`${__hooks}/identity.js`).page(e));
// Purge expired protocol records without retaining login codes or session hashes.
cronAdd('identity-expiry','17 * * * *',()=>{
 for(const collection of ['identity_requests','identity_sessions']){
  $app.db().newQuery('DELETE FROM '+collection+' WHERE expires < {:cutoff}').bind({cutoff:Math.floor(Date.now()/1000)-86400}).execute();
 }
});
