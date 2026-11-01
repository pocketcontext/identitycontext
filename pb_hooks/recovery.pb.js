onBootstrap(e=>{
 e.next();
 const marker=e.app.dataDir()+'/identity-recovery.pending';
 try{$os.stat(marker);}catch(_){return;}
 if(e.app.store().get('pocketcontextMaintenanceReadOnly')===true)throw new Error('Recovered identity state cannot start frozen before account reset.');
 e.app.runInTransaction(tx=>{
  for(const user of tx.findAllRecords('users')){user.set('disabled',true);user.refreshTokenKey();tx.save(user);}
  for(const session of tx.findAllRecords('identity_sessions')){session.set('revoked',true);tx.save(session);}
 });
 $os.remove(marker);
 console.log('identity recovery: restored accounts disabled and sessions revoked; operator reactivation required');
});
