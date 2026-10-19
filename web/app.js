/* Vanilla client. REST contracts: Suwayomi v2.4.2366 MangaAPI/controllers. */
(function (root) {
 'use strict';
 const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const enc = value => encodeURIComponent(String(value));
 function route(path) {
  const parts = path.split('/').filter(Boolean);
  if (!parts.length) return {name:'library'};
  if (['library','browse','updates','history','more'].includes(parts[0]) && parts.length === 1) return {name:parts[0]};
  if (parts[0] === 'manga' && /^\d+$/.test(parts[1]) && parts.length === 2) return {name:'manga',id:parts[1]};
  if (parts[0] === 'reader' && /^\d+$/.test(parts[1]) && /^\d+$/.test(parts[2]) && parts.length === 3) return {name:'reader',id:parts[1],chapter:parts[2]};
  return {name:'notfound'};
 }
 const sourceURL = (id, mode, page=1, query='') => '/api/v1/source/'+enc(id)+(mode === 'search' ? '/search?'+new URLSearchParams({searchTerm:query,pageNum:String(page)}) : '/'+(mode === 'latest' ? 'latest' : 'popular')+'/'+enc(page));
 const pageURL = (id, chapter, page) => '/api/v1/manga/'+enc(id)+'/chapter/'+enc(chapter)+'/page/'+enc(page);
 const uniqueManga = groups => [...new Map(groups.flat().map(m=>[String(m.id),m])).values()];
 function filterLibrary(items, query='', filter='all', sort='title') {
  return items.filter(m => String(m.title).toLocaleLowerCase().includes(query.toLocaleLowerCase()) && (filter !== 'unread' || m.unreadCount > 0) && (filter !== 'downloaded' || m.downloadCount > 0) && (filter !== 'read' || m.unreadCount === 0 && m.chapterCount > 0))
   .sort((a,b) => sort === 'recent' ? (b.lastReadAt || 0)-(a.lastReadAt || 0) : String(a.title).localeCompare(String(b.title),'id'));
 }
 function makeAPI(token, transport=fetch) {
  return async function api(path, opts={}) {
   const method=opts.method||'GET', headers={'Accept':'application/json','X-CSRF-Token':token,...opts.headers};
   let body=opts.body;
   if(opts.form){body=new URLSearchParams(Object.entries(opts.form).map(([k,v])=>[k,String(v)]));headers['Content-Type']='application/x-www-form-urlencoded;charset=UTF-8';}
   if(opts.json){body=JSON.stringify(opts.json);headers['Content-Type']='application/json';}
   let response;
   try { response=await transport(path,{method,headers,body,credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(opts.timeout||90000),keepalive:!!opts.keepalive}); }
   catch(error){throw Error(error.name==='TimeoutError'?'Mesin terlalu lama merespons. Coba lagi.':'Tidak dapat terhubung ke server. Periksa koneksi Anda.');}
   if(!response.ok){
    if(response.status===401) throw Error('Sesi berakhir. Silakan masuk kembali.');
    let detail=''; if((response.headers.get('content-type')||'').includes('application/json')){try{const data=await response.json();detail=String(data.message||data.error||'').slice(0,240);}catch{}}
    throw Error(`Permintaan gagal (${response.status}). ${detail||'Periksa sumber, mesin, atau izin akses; lalu coba lagi.'}`);
   }
   if(opts.raw)return response;
   const text=await response.text();
   if(!text.trim())return null;
   try{return JSON.parse(text);}catch{if(opts.mutation)return null;throw Error('Respons mesin bukan JSON yang valid.');}
  };
 }
 function mutation(action,d){
  const manga='/api/v1/manga/'+enc(d.manga),chapter=manga+'/chapter/'+enc(d.index);
  if(action==='library')return {path:manga+'/library',method:d.value==='true'?'GET':'DELETE'};
  if(['read','bookmark','finish-chapter'].includes(action))return {path:chapter,method:'PATCH',form:{[action==='bookmark'?'bookmarked':'read']:action==='finish-chapter'?'true':d.value}};
  if(action==='download')return {path:'/api/v1/download/'+enc(d.manga)+'/chapter/'+enc(d.index),method:'GET'};
  if(action==='unqueue')return {path:'/api/v1/download/'+enc(d.manga)+'/chapter/'+enc(d.index),method:'DELETE'};
  if(action==='delete-download')return {path:chapter,method:'DELETE'};
  if(['extension-install','extension-update','extension-uninstall'].includes(action))return {path:'/api/v1/extension/'+action.split('-')[1]+'/'+enc(d.package),method:'GET'};
  if(action.startsWith('queue-'))return {path:'/api/v1/downloads/'+action.slice(6),method:'GET'};
  if(action==='refresh')return {path:'/api/v1/update/fetch',method:'POST',form:{}};
  if(action==='category-delete')return {path:'/api/v1/category/'+enc(d.category),method:'DELETE'};
  if(action==='category-default')return {path:'/api/v1/category/'+enc(d.category),method:'PATCH',form:{default:d.value}};
  if(action==='assign-category')return {path:manga+'/category/'+enc(d.category),method:d.value==='true'?'GET':'DELETE'};
  if(action==='logout')return {path:'/logout',method:'POST'};
  throw Error('Tindakan tidak dikenal.');
 }
 async function bridge(api,operation,variables={}){
  const envelope=await api('/api/bridge',{method:'POST',json:{operation,variables},mutation:['addRepository','removeRepository'].includes(operation)});
  if(envelope?.errors?.length)throw Error(envelope.errors.map(x=>String(x.message||'Kesalahan GraphQL')).join('; '));
  if(!envelope?.data)throw Error('Data jembatan mesin tidak tersedia.');
  return envelope.data;
 }
 const UI = {escape,route,sourceURL,pageURL,uniqueManga,filterLibrary,makeAPI,mutation,bridge};
 if (typeof module !== 'undefined') module.exports = UI;
 root.MihonUI = UI;
})(typeof window !== 'undefined' ? window : globalThis);
