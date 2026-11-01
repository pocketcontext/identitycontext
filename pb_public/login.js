import PocketBase, {BaseAuthStore} from './pocketbase.es.mjs';
const button=document.querySelector('#signin'),status=document.querySelector('#status'),code=document.querySelector('#code');
const request=location.pathname.split('/').pop();
button.addEventListener('click',async()=>{
 button.disabled=true;status.textContent='Waiting for Google sign-in…';
 const pb=new PocketBase(location.origin,new BaseAuthStore());pb.authStore.clear();
 try{
  await pb.collection('users').authWithOAuth2({provider:'google',redirectUrl:location.origin+'/api/oauth2-redirect'});
  const response=await pb.send('/api/identity/login/approve',{method:'POST',body:{request}});
  code.textContent=response.code;document.querySelector('#instruction').hidden=false;status.textContent='Google sign-in completed.';
 }catch(_){status.textContent='Sign-in failed. Check that you used the account selected in your terminal, or start a new sign-in.';button.disabled=false;}
 finally{pb.authStore.clear();}
});
