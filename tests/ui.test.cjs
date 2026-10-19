const {test} = require('node:test');
const assert = require('node:assert/strict');
let ui = {}; try { ui = require('../web/views.js'); } catch (e) { if (e.code !== 'MODULE_NOT_FOUND') throw e; }
test('escapes all untrusted text and attributes', () => {
 assert.equal(typeof ui.escape, 'function', 'escape helper missing');
 assert.equal(ui.escape('<img src="x" onerror=\'bad\'>&'), '&lt;img src=&quot;x&quot; onerror=&#39;bad&#39;&gt;&amp;');
});
test('routes preserve source identifiers, pagination and same-origin media', () => {
 assert.equal(typeof ui.route, 'function', 'route helper missing');
 assert.equal(ui.route('/reader/12/3').chapter, '3');
 const id = '9007199254740993123';
 assert.equal(ui.sourceURL(id, 'search', 2, 'a & b'), '/api/v1/source/'+id+'/search?searchTerm=a+%26+b&pageNum=2');
 assert.equal(ui.pageURL('12','3',0), '/api/v1/manga/12/chapter/3/page/0');
 assert.equal(ui.route('/made-up').name, 'notfound');
});
test('library merges all categories without duplicates and filters without changing input', () => {
 assert.equal(typeof ui.filterLibrary, 'function', 'library filter missing');
 const input = [{id:1,title:'A',unreadCount:3,downloadCount:1},{id:2,title:'B',unreadCount:0,downloadCount:0}];
 assert.deepEqual(ui.filterLibrary(input,'a','unread','title').map(x=>x.id), [1]);
 assert.deepEqual(ui.filterLibrary(input,'','downloaded','title').map(x=>x.id), [1]);
 assert.equal(input.length,2);
 assert.equal(ui.uniqueManga([input,input]).length,2);
});

test('route views render honest empty library, navigation, and all supported sections', async () => {
 assert.equal(typeof ui.renderRoute, 'function', 'route renderer missing');
 const empty = async path => path === '/api/bridge' ? {data:{chapters:{nodes:[],pageInfo:{hasNextPage:false}},extensionStores:{nodes:[]}}} : path.endsWith('/category') ? [] : path.includes('recentChapters') ? {page:[],hasNextPage:false} : [];
 for (const name of ['library','browse','updates','history','more']) {
  const html = await ui.renderRoute({name},new URLSearchParams(),empty,{theme:'dark',gridColumns:3,readerMode:'webtoon'});
  assert.match(html, /<h1/);
  assert.doesNotMatch(html, /undefined|NaN/);
 }
 const library = await ui.renderRoute({name:'library'},new URLSearchParams(),empty,{});
 assert.match(library, /Perpustakaan masih kosong/);
 assert.match(library, /href="\/browse"/);
 assert.match(ui.navigation('library'), /aria-current="page"/);
});
test('source browsing uses exact string ID and displays real paginated manga with escaped metadata',async () => {
 const calls=[];
 const api=async path => {calls.push(path); if(path.endsWith('/list'))return [{id:'9007199254740993123',displayName:'Sumber',lang:'id',supportsLatest:true}]; return {mangaList:[{id:9,title:'<script>bad</script>'}],hasNextPage:true};};
 const html=await ui.renderRoute({name:'browse'},new URLSearchParams('source=9007199254740993123&mode=search&q=test'),api,{});
 assert.ok(calls.includes('/api/v1/source/9007199254740993123/search?searchTerm=test&pageNum=1'));
 assert.match(html,/&lt;script&gt;/); assert.doesNotMatch(html,/<script>/); assert.match(html,/page=2/);
});
test('typing a title searches the selected source even when the form still says popular',async()=>{
 const calls=[];
 const api=async path=>{calls.push(path);return path.endsWith('/list')?[{id:'4838485846640015979',displayName:'Komiku',lang:'id',supportsLatest:true}]:{mangaList:[],hasNextPage:false};};
 const html=await ui.renderRoute({name:'browse'},new URLSearchParams('source=4838485846640015979&mode=popular&q=  one piece  '),api,{});
 assert.ok(calls.includes('/api/v1/source/4838485846640015979/search?searchTerm=one+piece&pageNum=1'));
 assert.match(html,/<option value="search" selected/);
});
test('details and reader use chapter index not ID, correct media paths and server progress',async () => {
 const chapter={id:234,index:3,name:'Bab 3',pageCount:4,lastPageRead:2,read:false,bookmarked:false};
 const api=async path => path.endsWith('/chapters') ? [chapter] : path.endsWith('/category') ? [] : path.includes('/chapter/') ? chapter : {id:12,title:'Judul',inLibrary:true,genre:[],source:{displayName:'Sumber'}};
 const details=await ui.renderRoute({name:'manga',id:'12'},new URLSearchParams(),api,{});
 assert.match(details,/\/reader\/12\/3/); assert.match(details,/data-action="bookmark"/); assert.match(details,/\/api\/v1\/chapter\/234\/download/);
 const reader=await ui.renderRoute({name:'reader',id:'12',chapter:'3'},new URLSearchParams(),api,{readerMode:'ltr'});
 assert.match(reader,/\/api\/v1\/manga\/12\/chapter\/3\/page\/2/);
 assert.match(reader,/data-page="2"/);
});
test('more reports REST limitations and keeps tracking explicitly unavailable',async()=>{
 const html=await ui.renderRoute({name:'more'},new URLSearchParams('tab=extensions'),async path=>path==='/api/bridge'?{data:{extensionStores:{nodes:[]}}}:[],{});
 assert.match(html,/Repositori/); assert.match(html,/tidak tersedia/); assert.match(html,/name="indexUrl"/);
 const more=await ui.renderRoute({name:'more'},new URLSearchParams(),async()=>[],{});
 assert.match(more,/bersama/); assert.match(more,/Pelacakan/);
});

test('API sends CSRF even for legacy GET mutations and reports response failures safely',async()=>{
 assert.equal(typeof ui.makeAPI,'function','HTTP client missing');
 const calls=[]; const api=ui.makeAPI('token',async(path,opts)=>{calls.push({path,opts});return new Response('{"ok":true}',{headers:{'Content-Type':'application/json'}});});
 await api('/api/v1/manga/1/library',{mutation:true});
 assert.equal(calls[0].opts.headers['X-CSRF-Token'],'token');
 assert.equal(calls[0].opts.cache,'no-store');
 await api('/api/v1/manga/1/chapter/3',{method:'PATCH',form:{bookmarked:true}});
 assert.equal(calls[1].opts.body.toString(),'bookmarked=true');
 assert.match(calls[1].opts.headers['Content-Type'],/urlencoded/);
 const bad=ui.makeAPI('token',async()=>new Response('<h1>engine unavailable</h1>',{status:502}));
 await assert.rejects(()=>bad('/api/v1/category'),/502/);
});
test('mutation definitions preserve REST methods and distinguish chapter index',()=>{
 assert.equal(typeof ui.mutation,'function','mutation map missing');
 assert.deepEqual(ui.mutation('bookmark',{manga:'1',index:'3',value:'true'}),{path:'/api/v1/manga/1/chapter/3',method:'PATCH',form:{bookmarked:'true'}});
 assert.equal(ui.mutation('library',{manga:'1',value:'true'}).method,'GET');
 assert.equal(ui.mutation('library',{manga:'1',value:'false'}).method,'DELETE');
 assert.equal(ui.mutation('extension-install',{package:'a.b'}).path,'/api/v1/extension/install/a.b');
 assert.equal(ui.mutation('download',{manga:'1',index:'3'}).path,'/api/v1/download/1/chapter/3');
});

test('bridge checks GraphQL errors even when HTTP succeeds',async()=>{
 assert.equal(typeof ui.bridge,'function','bridge helper missing');
 await assert.rejects(()=>ui.bridge(async()=>({data:{},errors:[{message:'upstream schema failed'}]}),'history',{}),/upstream schema failed/);
 const calls=[];const result=await ui.bridge(async(path,options)=>{calls.push({path,options});return {data:{chapters:{nodes:[]}}};},'history',{first:50,offset:0});
 assert.deepEqual(result,{chapters:{nodes:[]}});assert.equal(calls[0].path,'/api/bridge');assert.equal(calls[0].options.json.operation,'history');
});
test('history includes non-library chapters through facade bridge and uses sourceOrder for reader',async()=>{
 const calls=[];const api=async(path,options)=>{calls.push({path,options});if(path.endsWith('/chapters'))return [{id:8,index:2,bookmarked:false,downloaded:false}];return {data:{chapters:{nodes:[{id:8,name:'Bab',mangaId:7,sourceOrder:2,lastReadAt:'123',lastPageRead:1,isRead:false,manga:{id:7,title:'Dihapus dari koleksi'}}],pageInfo:{hasNextPage:false},totalCount:1}}};};
 const html=await ui.renderRoute({name:'history'},new URLSearchParams(),api,{});
 assert.equal(calls[0].path,'/api/bridge');assert.equal(calls[0].options.json.operation,'history');assert.match(html,/Dihapus dari koleksi/);assert.match(html,/\/reader\/7\/2/);
});
test('library explicitly fetches uncategorized category zero even when list omits it',async()=>{
 const calls=[];const result=await ui.library(async path=>{calls.push(path);return path==='/api/v1/category'?[{id:4,name:'C'}]:path.endsWith('/0')?[{id:1,title:'Uncategorized'}]:[];});
 assert.ok(calls.includes('/api/v1/category/0'));assert.equal(result.items[0].id,1);
});

test('HTML local asset URLs match Go embedded filesystem root',()=>{
 const fs=require('node:fs');
 for(const name of ['index.html','login.html']){const html=fs.readFileSync(__dirname+'/../web/'+name,'utf8');for(const [,url]of html.matchAll(/(?:src|href)="(\/[^"?#]+\.(?:js|css|svg))"/g)){assert.ok(fs.existsSync(__dirname+'/../web'+url),`unserved embedded URL ${url}`);}}
});
