function configure(app){
 if(app.store().get('pocketcontextMaintenanceReadOnly')===true)return;
 const id=$os.getenv('IDENTITYCONTEXT_GOOGLE_CLIENT_ID'),secret=$os.getenv('IDENTITYCONTEXT_GOOGLE_CLIENT_SECRET');
 if(!!id!==!!secret)throw new Error('Google client ID and secret must be provided together.');
 if(id){
  try{const users=app.findCollectionByNameOrId('users');users.oauth2={enabled:true,providers:[{name:'google',clientId:id,clientSecret:secret}]};app.save(users);}catch(_){throw new Error('Identity Google settings could not be applied.');}
 }
 const settings=app.settings();
 settings.meta.appName='IdentityContext';settings.meta.appURL='https://id.pocketcontext.com';
 settings.rateLimits.enabled=$os.getenv('IDENTITYCONTEXT_RATE_LIMITS')!=='false';
 settings.rateLimits.rules=[{label:'/api/identity/login/',audience:'',duration:60,maxRequests:10},{label:'/api/identity/',audience:'',duration:60,maxRequests:60},{label:'*:auth',audience:'',duration:60,maxRequests:10},{label:'/',audience:'',duration:60,maxRequests:300}];
 const header=$os.getenv('IDENTITYCONTEXT_TRUSTED_PROXY_HEADER');
 if(header){settings.trustedProxy.headers=[header];settings.trustedProxy.useLeftmostIP=false;}
 app.save(settings);
}
function up(e){const n=new DynamicModel({n:0});e.app.db().newQuery('SELECT count(*) AS n FROM _collections').one(n);return e.string(200,'OK');}
module.exports={configure,up};
