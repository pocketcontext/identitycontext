import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
 const context=await browser.newContext({viewport:{width:390,height:844}});
 await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:new URL(process.env.ID_TEST_URL).origin});
 const page=await context.newPage();
 const errors=[];page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});page.on('requestfailed',request=>{if(new URL(request.url()).pathname!=='/api/realtime')errors.push(new URL(request.url()).pathname+': '+request.failure().errorText);});page.on('pageerror',error=>errors.push(error.message));
 await page.goto(process.env.ID_TEST_URL+'/l/'+process.env.ID_TEST_REQUEST);
 await page.getByRole('heading',{name:'Sign in to PocketContext'}).waitFor();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.keyboard.press('Tab');
 assert.equal(await page.getByRole('button',{name:'Continue with Google'}).evaluate(node=>node===document.activeElement),true);
 await page.keyboard.press('Enter');
 try{await page.getByText('Google sign-in completed.',{exact:true}).waitFor({timeout:15000});}catch(error){console.error(await page.locator('#status').textContent(),errors);throw error;}
 const code=await page.locator('#code').textContent();
 assert.match(code,/^[A-Z2-9]{12}$/);
 const copy=page.getByRole('button',{name:'Copy code'});
 await copy.focus();await page.keyboard.press('Enter');
 await page.getByText('Code copied. Paste it into your terminal.',{exact:true}).waitFor();
 assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),code);
 await page.evaluate(()=>{navigator.clipboard.writeText=()=>Promise.reject(new Error('denied'));});
 await copy.click();
 await page.getByText('Your browser blocked copying. The code is selected; copy it manually.',{exact:true}).waitFor();
 assert.equal(await page.evaluate(()=>getSelection().toString()),code);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 const stored=await page.evaluate(()=>({...localStorage}));
 assert.ok(Object.keys(stored).every(key=>key==='pbSettings'));
 assert.ok(!JSON.stringify(stored).includes('member@pocketcontext.com'));
 assert.ok(!JSON.stringify(stored).toLowerCase().includes('token'));
 assert.deepEqual(await page.evaluate(()=>Object.keys(sessionStorage)),[]);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({code}));
 await context.close();
}finally{await browser.close();}
