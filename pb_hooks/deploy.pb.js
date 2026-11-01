onBootstrap(e=>{e.next();require(`${__hooks}/deploy.js`).configure(e.app);});
routerAdd('GET','/up',e=>require(`${__hooks}/deploy.js`).up(e),$apis.skipSuccessActivityLog());
// Browser approval tokens are short lived and require a fresh Google login.
onRecordAuthRefreshRequest(()=>{throw new ForbiddenError('Sign in with Google again.');},'users');
