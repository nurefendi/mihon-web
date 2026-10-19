/* Read-only engine smoke. Run only against the pinned private engine, never seeds content. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const UI=require('../web/views.js');
const base=process.env.ENGINE_URL;
const go=fs.readFileSync(__dirname+'/../bridge.go','utf8');
const queries=Object.fromEntries([...go.matchAll(/"(library|history|downloads|repositories)"\s*:\s*`([^`]+)`/g)].map(x=>[x[1],x[2]]));
const api=async(path,options={})=>{
 let endpoint=path,body;
 if(path==='/api/bridge'){const {operation,variables}=options.json;endpoint='/api/graphql';body=JSON.stringify({query:queries[operation],variables:{first:50,offset:0,...variables}});}
 const response=await fetch(base+endpoint,{method:body?'POST':'GET',body,headers:{'Content-Type':'application/json'}});
 assert.ok(response.ok,`${endpoint}: ${response.status}`);return response.json();
};
test('real stable engine renders read-only routes and every More section without seeded content',{skip:!base},async()=>{
 const routes=['library','browse','updates','history','more'];
 for(const name of routes){const html=await UI.renderRoute({name},new URLSearchParams(),api,{theme:'dark',gridColumns:3,readerMode:'webtoon'});assert.match(html,/<h1/);assert.doesNotMatch(html,/undefined|NaN/);console.log(`LIVE ${name}: ${html.length} chars`);}
 for(const tab of ['categories','extensions','settings','backup','downloads']){const html=await UI.renderRoute({name:'more'},new URLSearchParams({tab}),api,{});assert.match(html,/<h1/);assert.doesNotMatch(html,/undefined|NaN/);console.log(`LIVE more/${tab}: ${html.length} chars`);}
 const queue=await UI.bridge(api,'downloads');assert.ok(Array.isArray(queue.downloadStatus.queue));
});
