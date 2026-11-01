import PocketBase, {BaseAuthStore} from './pocketbase.es.mjs';
const button=document.querySelector('#signin'),status=document.querySelector('#status'),code=document.querySelector('#code'),copy=document.querySelector('#copy'),copied=document.querySelector('#copied');
const request=location.pathname.split('/').pop();
button.addEventListener('click',async()=>{
 button.disabled=true;status.textContent='Waiting for Google sign-in…';
 const pb=new PocketBase(location.origin,new BaseAuthStore());pb.authStore.clear();
 try{
  await pb.collection('users').authWithOAuth2({provider:'google',redirectUrl:location.origin+'/api/oauth2-redirect'});
  const response=await pb.send('/api/identity/login/approve',{method:'POST',body:{request}});
  code.textContent=response.code;document.querySelector('#instruction').hidden=false;copy.hidden=false;status.textContent='Google sign-in completed.';
 }catch(_){status.textContent='Sign-in failed. Check that you used the account selected in your terminal, or start a new sign-in.';button.disabled=false;}
 finally{pb.authStore.clear();}
});
copy.addEventListener('click',async()=>{
 try{await navigator.clipboard.writeText(code.textContent);copied.textContent='Code copied. Paste it into your terminal.';}
 catch(_){const range=document.createRange();range.selectNodeContents(code);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);copied.textContent='Your browser blocked copying. The code is selected; copy it manually.';}
});
