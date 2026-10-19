/* Dev-only DOM integration; NODE_PATH points to a scratch jsdom installation. */
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const {JSDOM}=require('jsdom');
const root=__dirname+'/../web/';
const read=f=>fs.readFileSync(root+f,'utf8');
async function boot(path,handler){
 assert.ok(fs.existsSync(root+'index.html'),'index shell missing');
 const dom=new JSDOM(read('index.html'),{url:'https://mihon.test'+path,runScripts:'outside-only',pretendToBeVisual:true});
 const calls=[];
 Object.assign(dom.window,{AbortSignal,Response,fetch:async(url,opts={})=>{calls.push({url,opts});const value=url==='/app-session'?{username:'admin',csrfToken:'test-csrf'}:url==='/api/preferences'?{theme:'dark',readerMode:'webtoon',gridColumns:3}:await handler(url,opts);return new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});}});
 dom.window.scrollTo=()=>{};dom.window.HTMLElement.prototype.scrollIntoView=()=>{};dom.window.confirm=()=>true;
 for(const f of ['app.js','views.js','boot.js'])dom.window.eval(read(f));
 await dom.window.MihonReady;
 return {dom,doc:dom.window.document,calls};
}
test('actual application boots empty library and keeps five navigation destinations',async()=>{
 const {dom,doc}=await boot('/library',async()=>[]);
 assert.match(doc.querySelector('main').textContent,/Perpustakaan masih kosong/);
 assert.equal(doc.querySelectorAll('.nav-links a').length,5);
 assert.equal(doc.querySelector('.nav-links [aria-current]').getAttribute('href'),'/library');
 assert.ok(!doc.querySelector('main script'));
 dom.window.close();
});
test('settings submit persists preferences with CSRF and reads back server values',async()=>{
 const {dom,doc,calls}=await boot('/more?tab=settings',async()=>[]);
 doc.querySelector('[name=theme]').value='light';
 doc.querySelector('#preferences-form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
 await new Promise(r=>setTimeout(r,30));
 const req=calls.find(x=>x.url==='/api/preferences'&&x.opts.method==='PUT');
 assert.ok(req); assert.equal(req.opts.headers['X-CSRF-Token'],'test-csrf');assert.equal(JSON.parse(req.opts.body).theme,'light');
 assert.ok(calls.filter(x=>x.url==='/api/preferences').length>=2);
 dom.window.close();
});
test('chapter bookmark button uses PATCH form and verifies chapter readback',async()=>{
 const chapter={id:8,index:3,name:'Bab',read:false,bookmarked:false,pageCount:1};let bookmarked=false;
 const {dom,doc,calls}=await boot('/manga/12',async(url,opts)=>{
  if(url.includes('/chapter/3')&&opts.method==='PATCH'){bookmarked=true;return null;}
  if(url.endsWith('/chapters'))return [{...chapter,bookmarked}];if(url.endsWith('/category'))return [];
  return {id:12,title:'<img onerror=bad>',inLibrary:true,genre:[],source:{displayName:'Sumber'}};
 });
 assert.ok(!doc.querySelector('h1 img'));doc.querySelector('[data-action=bookmark]').click();
 await new Promise(r=>setTimeout(r,40));
 const req=calls.find(x=>x.opts.method==='PATCH');assert.equal(req.url,'/api/v1/manga/12/chapter/3');assert.equal(req.opts.body.toString(),'bookmarked=true');
 assert.match(doc.querySelector('[data-action=bookmark]').textContent,/Lepas/);dom.window.close();
});
test('engine failures render retryable error instead of invented content',async()=>{
 const {dom,doc}=await boot('/library',async()=>{throw Error('Offline');});
 assert.match(doc.querySelector('main').textContent,/Tidak dapat|gagal/);assert.ok(doc.querySelector('[data-action=retry]'));dom.window.close();
});
test('login exposes accessible password control and only real POST login form',()=>{
 assert.ok(fs.existsSync(root+'login.html'),'login shell missing');
 const dom=new JSDOM(read('login.html'),{url:'https://mihon.test/login?error=1',runScripts:'outside-only'});
 dom.window.eval(read('login.js'));
 const doc=dom.window.document,form=doc.querySelector('form');assert.equal(form.method,'post');assert.equal(form.getAttribute('action'),'/login');
 assert.equal(doc.querySelector('[name=password]').autocomplete,'current-password');doc.querySelector('#toggle-password').click();assert.equal(doc.querySelector('[name=password]').type,'text');
 assert.equal(doc.querySelector('#login-error').hidden,false);assert.doesNotMatch(doc.body.textContent,/demo access/i);dom.window.close();
});

test('download queue uses curated bridge and renders actual empty status without WebSocket',async()=>{
 const {dom,doc,calls}=await boot('/more?tab=downloads',async(url,opts)=>({data:{downloadStatus:{state:'STOPPED',queue:[]}}}));
 await new Promise(r=>setTimeout(r,20));
 assert.match(doc.querySelector('#queue-status').textContent,/0 bab/);assert.match(doc.querySelector('#queue-list').textContent,/Antrean kosong/);
 assert.ok(calls.some(x=>x.url==='/api/bridge'&&JSON.parse(x.opts.body).operation==='downloads'));dom.window.close();
});
test('repository addition requires explicit trust and verifies configured repository readback',async()=>{
 let repositories=[];
 const {dom,doc,calls}=await boot('/more?tab=extensions',async(url,opts)=>{
  if(url.endsWith('/extension/list'))return [];
  const command=JSON.parse(opts.body);if(command.operation==='addRepository'){repositories=[{indexUrl:command.variables.indexUrl,name:'Trusted by test user'}];return {data:{addExtensionStore:{extensionStore:repositories[0]}}};}
  return {data:{extensionStores:{nodes:repositories}}};
 });
 const form=doc.querySelector('#repo-add');form.querySelector('[name=indexUrl]').value='https://repo.example/index.min.json';
 form.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setTimeout(r,15));
 assert.ok(!calls.some(x=>x.url==='/api/bridge'&&JSON.parse(x.opts.body).operation==='addRepository'));
 form.querySelector('[name=trust]').checked=true;form.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setTimeout(r,45));
 assert.ok(calls.some(x=>x.url==='/api/bridge'&&JSON.parse(x.opts.body).operation==='addRepository'));assert.match(doc.querySelector('main').textContent,/Trusted by test user/);dom.window.close();
});

test('repository readback accepts the canonical URL returned by the engine',async()=>{
 let repositories=[];
 const canonical='https://github.com/keiyoushi/extensions/raw/repo/index.pb';
 const {dom,doc}=await boot('/more?tab=extensions',async(url,opts)=>{
  if(url.endsWith('/extension/list'))return [];
  const command=JSON.parse(opts.body);
  if(command.operation==='addRepository'){repositories=[{indexUrl:canonical,name:'Canonical repository'}];return {data:{addExtensionStore:{extensionStore:repositories[0]}}};}
  return {data:{extensionStores:{nodes:repositories}}};
 });
 const form=doc.querySelector('#repo-add');form.querySelector('[name=indexUrl]').value='https://raw.githubusercontent.com/keiyoushi/extensions/refs/heads/repo/index.min.json';form.querySelector('[name=trust]').checked=true;
 form.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setTimeout(r,70));
 assert.match(doc.querySelector('main').textContent,/Canonical repository/);
 assert.equal(doc.querySelector('#notice').classList.contains('error'),false);
 dom.window.close();
});

test('reader only saves progress after image load, not when an image may have failed',async()=>{
 let lastPageRead=1;
 const {dom,doc,calls}=await boot('/reader/12/3?mode=ltr',async(url,opts)=>{
  if(opts.method==='PATCH'){lastPageRead=Number(opts.body.get('lastPageRead'));return null;}
  const c={id:8,index:3,name:'Bab',pageCount:3,lastPageRead,read:false};
  return url.endsWith('/chapters')?[c]:url.includes('/chapter/3')?c:{id:12,title:'Reader test'};
 });
 await new Promise(r=>setTimeout(r,550));assert.equal(calls.filter(x=>x.opts.method==='PATCH').length,0,'unloaded page must not write progress');
 doc.querySelector('.reader-page').dispatchEvent(new dom.window.Event('load'));await new Promise(r=>setTimeout(r,550));
 const req=calls.find(x=>x.opts.method==='PATCH');assert.ok(req);assert.equal(req.opts.body.get('lastPageRead'),'1');assert.ok(!req.opts.body.has('read'));dom.window.close();
});

test('login server validation keeps form usable and reports rate limits instead of navigating to raw text',async()=>{
 const dom=new JSDOM(read('login.html'),{url:'https://mihon.test/login',runScripts:'outside-only'});let called=false;
 dom.window.fetch=async(url,opts)=>{called=true;assert.equal(url,'/login');assert.equal(opts.method,'POST');assert.match(opts.headers['Content-Type'],/urlencoded/);return {ok:false,status:429};};
 dom.window.eval(read('login.js'));dom.window.document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setTimeout(r,20));
 assert.ok(called);assert.equal(dom.window.document.querySelector('.login-submit').disabled,false);assert.equal(dom.window.document.querySelector('#login-error').hidden,false);assert.match(dom.window.document.querySelector('#login-error').textContent,/Terlalu banyak/);dom.window.close();
});
