/* DOM lifecycle and same-origin engine integration. No demo data or external assets. */
(()=>{
 'use strict';
 const U=window.MihonUI,{escape:e}=U;
 const main=document.querySelector('main'),nav=document.querySelector('#navigation');
 const current=U.route(location.pathname),params=new URLSearchParams(location.search);
 let api,prefs,session,readerCleanup=()=>{},readerSelectPage=()=>{},queueSocket,noticeTimer,renderVersion=0;
 const notice=(text,error=false)=>{const node=document.querySelector('#notice');clearTimeout(noticeTimer);node.textContent=text;node.classList.toggle('error',error);node.hidden=false;noticeTimer=setTimeout(()=>{node.hidden=true;},error?15000:6000);};
 const applyTheme=()=>{document.documentElement.dataset.theme=prefs.theme==='system'?(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'):prefs.theme;document.documentElement.dataset.columns=String(prefs.gridColumns||3);};
 async function load(){
  const version=++renderVersion;
  readerCleanup();clearTimeout(progressTimer);if(queueSocket){queueSocket.close();queueSocket=null;}
  main.setAttribute('aria-busy','true');
  try{
   const html=await U.renderRoute(current,params,api,prefs);
   if(version!==renderVersion)return;
   main.innerHTML=html;document.title=(main.querySelector('h1')?.textContent||'Mihon')+' · Mihon Web';
   document.body.classList.toggle('reading',current.name==='reader');
   bindReader();bindQueue();
  }catch(error){
   if(version!==renderVersion)return;
   main.innerHTML=`<header class="page-header"><h1>Tidak dapat memuat halaman</h1></header><section class="empty error-state">${U.icon('book')}<h2>Koneksi belum berhasil</h2><p>${e(error.message)}</p><div class="row-actions"><button type="button" class="filled" data-action="retry">Coba lagi</button><a class="button" href="/login">Masuk kembali</a><a class="button" href="/library">Perpustakaan</a></div></section>`;
  }finally{main.removeAttribute('aria-busy');}
 }
 async function queueSnapshot(){
  const data=await U.bridge(api,'downloads');const status=data.downloadStatus;
  if(!status||!Array.isArray(status.queue))throw Error('Format status antrean mesin tidak dikenali.');
  const ids=[...new Set(status.queue.map(x=>String(x.manga.id)))];
  const chapters=new Map(await Promise.all(ids.map(async id=>[id,await api('/api/v1/manga/'+encodeURIComponent(id)+'/chapters')])));
  return {status:status.state==='STARTED'?'Started':'Stopped',queue:status.queue.map(x=>{
   const chapter=chapters.get(String(x.manga.id)).find(c=>String(c.id)===String(x.chapter.id));
   return {...x,mangaId:String(x.manga.id),chapterIndex:chapter?.index,chapter:chapter||x.chapter};
  })};
 }
 function queueMarkup(data){
  return data.queue.length?data.queue.map(x=>`<article class="manage-row"><div><a href="/manga/${encodeURIComponent(x.mangaId)}"><strong>${e(x.manga.title)}</strong></a><small>${e(x.chapter.name)} · ${e(x.state)} · ${Math.round((x.progress||0)*100)}%</small></div>${x.chapterIndex!=null?`<button type="button" data-action="unqueue" data-manga="${encodeURIComponent(x.mangaId)}" data-index="${encodeURIComponent(x.chapterIndex)}">Batalkan</button>`:''}</article>`).join(''):'<p class="muted">Antrean kosong. Tambahkan bab dari halaman detail.</p>';
 }
 function bindQueue(){
  const status=document.querySelector('#queue-status');if(!status)return;
  let cancelled=false,timer;
  queueSocket={close(){cancelled=true;clearTimeout(timer);}};
  const update=async()=>{
   try{const data=await queueSnapshot();if(cancelled||!status.isConnected)return;status.textContent=(data.status==='Started'?'Berjalan':'Dijeda')+' · '+data.queue.length+' bab dalam antrean';document.querySelector('#queue-list').innerHTML=queueMarkup(data);}
   catch(error){if(!cancelled)status.textContent='Status antrean tidak tersedia: '+error.message;}
   if(!cancelled)timer=setTimeout(update,4000);
  };
  update();
 }
 async function verify(action,d){
  const base='/api/v1/manga/'+encodeURIComponent(d.manga);
  if(['read','bookmark','finish-chapter','delete-download'].includes(action)){
   const chapters=await api(base+'/chapters'),c=chapters.find(x=>String(x.index)===d.index);
   const field=action==='bookmark'?'bookmarked':action==='delete-download'?'downloaded':'read';
   const value=action==='finish-chapter'?true:action==='delete-download'?false:d.value==='true';
   if(!c||c[field]!==value)throw Error('Mesin belum mengonfirmasi perubahan bab. Segarkan untuk memeriksa status.');
  }else if(action==='library'){
   const m=await api(base);if(m.inLibrary!==(d.value==='true'))throw Error('Status perpustakaan belum terkonfirmasi.');
  }else if(action==='assign-category'){
   const list=await api(base+'/category');if(list.some(c=>String(c.id)===d.category)!==(d.value==='true'))throw Error('Perubahan kategori belum terkonfirmasi.');
  }else if(action.startsWith('extension-')){
   const list=await api('/api/v1/extension/list'),extension=list.find(x=>x.pkgName===d.package);
   if(action==='extension-uninstall'?extension?.installed:!extension?.installed)throw Error('Perubahan ekstensi belum terkonfirmasi.');
   if(action==='extension-update'&&extension.hasUpdate)throw Error('Pembaruan ekstensi belum terkonfirmasi.');
  }else if(action.startsWith('category-')){
   const list=await api('/api/v1/category'),c=list.find(x=>String(x.id)===d.category);
   if(action==='category-delete'&&c||action==='category-default'&&c?.default!==(d.value==='true'))throw Error('Perubahan kategori belum terkonfirmasi.');
  }else if(action==='refresh'){
   await api('/api/v1/update/summary');
  }else if(action==='download'||action==='unqueue'||action.startsWith('queue-')){
   const data=await queueSnapshot();
   const item=data.queue.find(x=>String(x.mangaId)===d.manga&&String(x.chapterIndex)===d.index);
   if(action==='download'&&!item){const chapters=await api(base+'/chapters');if(!chapters.find(c=>String(c.index)===d.index)?.downloaded)throw Error('Bab belum terlihat di antrean atau unduhan. Periksa koneksi sumber.');}
   if(action==='unqueue'&&item||action==='queue-clear'&&data.queue.length||action==='queue-stop'&&data.status!=='Stopped')throw Error('Status antrean belum sesuai permintaan. Coba segarkan.');
  }
 }
 main.addEventListener('click',async event=>{
  const target=event.target.closest('[data-action]');if(!target||target.type==='checkbox')return;
  const action=target.dataset.action,d={...target.dataset};
  if(action==='retry'){await load();return;}
  if(action==='page-next'||action==='page-prev'){movePage(action==='page-next'?1:-1);return;}
  if(['library','category-delete','delete-download','extension-uninstall','extension-install','extension-update','queue-clear','logout'].includes(action)){
   const destructive=action==='library'&&d.value==='false'||action!=='library';
   if(destructive&&!confirm(action.startsWith('extension-')?'Ekstensi menjalankan kode pihak ketiga di server. Lanjutkan perubahan pada mesin bersama?':'Perubahan ini berlaku untuk perpustakaan bersama. Lanjutkan?'))return;
  }
  target.disabled=true;
  try{
   if(action==='refresh-manga'){await api('/api/v1/manga/'+d.manga+'/chapters?onlineFetch=true');await load();notice('Daftar bab diperbarui dari sumber.');return;}
   if(action==='repo-remove'){
    if(!confirm('Hapus repositori dari mesin bersama? Ekstensi yang sudah terpasang tidak otomatis dicopot.'))return;
    await U.bridge(api,'removeRepository',{indexUrl:d.url});
    const data=await U.bridge(api,'repositories');if(data.extensionStores.nodes.some(r=>r.indexUrl===d.url))throw Error('Penghapusan repositori belum terkonfirmasi.');
   }else if(action==='category-rename'){
    const name=prompt('Nama kategori baru',d.name);if(!name?.trim())return;
    await api('/api/v1/category/'+d.category,{method:'PATCH',form:{name:name.trim()},mutation:true});
    const list=await api('/api/v1/category');if(list.find(c=>String(c.id)===d.category)?.name!==name.trim())throw Error('Nama kategori belum terkonfirmasi.');
   }else{
    const command=U.mutation(action,d);await api(command.path,{...command,mutation:true});
    if(action==='logout'){const response=await fetch('/app-session',{credentials:'same-origin',cache:'no-store',redirect:'manual'});if(response.status===200)throw Error('Sesi masih aktif. Coba keluar lagi.');location.assign('/login');return;}
    await verify(action,d);
   }
   if(action==='finish-chapter'){notice('Bab ditandai selesai.');return;}
   if(action.startsWith('queue-')||action==='unqueue'){notice('Status antrean telah diperiksa.');return;}
   await load();notice(action==='refresh'?'Pemeriksaan koleksi diminta. Hasil akan muncul di Pembaruan.':action==='download'?'Bab terkonfirmasi di antrean atau sudah diunduh.':'Perubahan tersimpan di server.');
  }catch(error){notice(error.message,true);}finally{target.disabled=false;}
 });
 main.addEventListener('change',async event=>{
  const target=event.target;
  if(target.id==='chapter-filter'){document.querySelectorAll('[data-chapter-read]').forEach(row=>{row.hidden=target.value==='unread'?row.dataset.chapterRead==='true':target.value==='bookmarked'?row.dataset.chapterBookmarked!=='true':target.value==='downloaded'?row.dataset.chapterDownloaded!=='true':false;});}
  if(target.id==='page-number'){const shell=document.querySelector('.reader-shell');if(shell)showPage(Math.min(Number(shell.dataset.readerCount)-1,Math.max(0,Number(target.value)-1)));}
  if(target.dataset.action==='assign-category'){
   const checked=target.checked;target.disabled=true;
   try{const d={...target.dataset,value:String(checked)},command=U.mutation('assign-category',d);await api(command.path,{...command,mutation:true});await verify('assign-category',d);notice('Kategori diperbarui.');}catch(error){target.checked=!checked;notice(error.message,true);}finally{target.disabled=false;}
  }
 });
 main.addEventListener('input',event=>{if(event.target.id==='extension-search'){const q=event.target.value.toLocaleLowerCase();document.querySelectorAll('.extension-row').forEach(row=>{row.hidden=!row.dataset.search.includes(q);});}});
 main.addEventListener('submit',async event=>{
  const form=event.target;if(!['preferences-form','category-create','backup-import','extension-upload','repo-add'].includes(form.id))return;
  event.preventDefault();const button=form.querySelector('button');button.disabled=true;
  try{
   const data=new FormData(form);
   if(form.id==='repo-add'){
    if(data.get('trust')!=='on')throw Error('Persetujuan kepercayaan repositori wajib diberikan.');
    const indexUrl=String(data.get('indexUrl')).trim();let url;try{url=new URL(indexUrl);}catch{throw Error('Masukkan URL repositori yang valid.');}
    if(url.protocol!=='https:'||url.username||url.password)throw Error('Repositori harus memakai HTTPS tanpa kredensial URL.');
    const added=await U.bridge(api,'addRepository',{indexUrl}),canonical=added.addExtensionStore?.extensionStore?.indexUrl||indexUrl;
    const result=await U.bridge(api,'repositories');
    if(!result.extensionStores.nodes.some(r=>r.indexUrl===canonical))throw Error('Repositori baru belum terkonfirmasi.');
    await load();notice('Repositori ditambahkan. Anda tetap harus menyetujui pemasangan setiap ekstensi.');
   }else if(form.id==='preferences-form'){
    await api('/api/preferences',{method:'PUT',json:{theme:data.get('theme'),readerMode:data.get('readerMode'),gridColumns:Number(data.get('gridColumns'))},mutation:true});
    prefs=await api('/api/preferences');applyTheme();notice('Pengaturan disimpan.');
   }else if(form.id==='category-create'){
    const name=String(data.get('name')).trim();if(!name)throw Error('Masukkan nama kategori.');
    await api('/api/v1/category',{method:'POST',form:{name},mutation:true});
    const categories=await api('/api/v1/category');if(!categories.some(c=>c.name===name))throw Error('Kategori baru belum terkonfirmasi.');await load();notice('Kategori ditambahkan.');
   }else if(form.id==='extension-upload'){
    if(!confirm('APK ekstensi dapat menjalankan kode di server. Pasang hanya APK yang Anda percaya. Lanjutkan?'))return;
    const upload=new FormData();upload.append('file',data.get('file'));
    await api('/api/v1/extension/install',{method:'POST',body:upload,mutation:true});
    await api('/api/v1/extension/list');await load();notice('Unggahan diproses. Periksa status terpasang pada daftar ekstensi.');
   }else{
    const file=data.get('backup');if(!file?.size)throw Error('Pilih berkas cadangan yang tidak kosong.');
    const bytes=await file.arrayBuffer(),headers={'Content-Type':'application/octet-stream'};
    const validation=await api('/api/v1/backup/validate',{method:'POST',body:bytes,headers,timeout:180000});
    document.querySelector('#backup-report').textContent='Hasil validasi mesin:\n'+JSON.stringify(validation,null,2);
    if(!confirm('Hasil validasi telah ditampilkan. Pemulihan mengubah perpustakaan bersama dan dapat memerlukan sumber yang belum terpasang. Sudah mengekspor cadangan saat ini dan ingin melanjutkan?'))return;
    const result=await api('/api/v1/backup/import',{method:'POST',body:bytes,headers,timeout:300000,mutation:true});
    await U.library(api);
    document.querySelector('#backup-report').textContent+='\n\nHasil pemulihan mesin:\n'+JSON.stringify(result,null,2);
    notice('Mesin selesai memproses cadangan. Periksa laporan dan perpustakaan.');
   }
  }catch(error){notice(error.message,true);}finally{button.disabled=false;}
 });
 let readerPage=0,readerViewed=false,progressTimer,progressChain=Promise.resolve(),lastSaved=-1;
 function saveProgress(shell,page,immediate=false){
  clearTimeout(progressTimer);
  const run=()=>{
   if(page===lastSaved)return;lastSaved=page;
   progressChain=progressChain.catch(()=>{}).then(async()=>{
    try{
     const count=Number(shell.dataset.readerCount),path='/api/v1/manga/'+shell.dataset.readerManga+'/chapter/'+shell.dataset.readerChapter;
     const form={lastPageRead:page};if(page===count-1)form.read=true;
     await api(path,{method:'PATCH',form,mutation:true,keepalive:true});
     const list=await api('/api/v1/manga/'+shell.dataset.readerManga+'/chapters'),saved=list.find(c=>String(c.index)===shell.dataset.readerChapter);
     if(!saved||saved.lastPageRead!==page)throw Error('Kemajuan baca belum terkonfirmasi.');
     const status=document.querySelector('#reader-status');if(status)status.textContent=`Halaman ${page+1} / ${count} · Kemajuan tersimpan${page===count-1?' · Bab selesai':''}`;
    }catch(error){lastSaved=-1;notice('Kemajuan belum tersimpan: '+error.message,true);}
   });
  };
  if(immediate)run();else progressTimer=setTimeout(run,500);
 }
 function bindReader(){
  const shell=document.querySelector('.reader-shell');if(!shell)return;
  readerPage=Number(shell.dataset.readerPage);readerViewed=false;lastSaved=-1;
  if(!Number(shell.dataset.readerCount))return;
  const images=[...shell.querySelectorAll('.reader-page')],slots=images.map(image=>image.parentElement);
  const webtoon=shell.dataset.readerMode==='webtoon';
  // Independent slots let ready pages display without waiting for earlier pages.
  const tail=shell.querySelector('.reader-loading'),resume=webtoon?readerPage:0;
  let settledCount=0,active=0,frame=0,stopped=false,interacted=false,pendingResume=resume>0,observedPage=-1;
  // Only a button click can move an error back into the request queue.
  const states=images.map(()=> 'idle'),concurrency=3,preloadMargin=1200;
  const urls=images.map(image=>U.pageURL(shell.dataset.readerManga,shell.dataset.readerChapter,Number(image.dataset.page)));
  const retryControls=images.map((image,i)=>{
   const panel=document.createElement('div'),label=document.createElement('span'),button=document.createElement('button');
   panel.className='reader-error';panel.hidden=true;button.type='button';button.textContent='Coba lagi';
   panel.append(label,button);slots[i].append(panel);
   const retry=()=>{if(stopped||states[i]!=='error')return;states[i]='retry';button.disabled=true;label.textContent=`Memuat ulang halaman ${i+1}…`;pump();};
   button.addEventListener('click',retry);
   return {panel,label,button,retry};
  });
  function track(){
   if(stopped||pendingResume)return;
   const image=images.find(image=>{if(image.hidden||!image.classList.contains('loaded'))return false;const rect=image.getBoundingClientRect();return rect.bottom>innerHeight*.1&&rect.top<innerHeight*.65;});
   if(image&&Number(image.dataset.page)!==observedPage){observedPage=readerPage=Number(image.dataset.page);readerViewed=true;shell.dataset.readerPage=String(readerPage);saveProgress(shell,readerPage);}
  }
  function pump(){
   if(stopped||!shell.isConnected)return;
   const candidates=images.map((image,i)=>({image,i,rect:slots[i].getBoundingClientRect()}))
    .filter(({i,rect})=>{
     if(states[i]==='retry')return true;
     if(states[i]!=='idle')return false;
     if(!webtoon)return !slots[i].hidden;
     return pendingResume?Math.abs(i-resume)<=2:rect.bottom>-preloadMargin&&rect.top<innerHeight+preloadMargin;
    })
    .sort((a,b)=>(states[b.i]==='retry')-(states[a.i]==='retry')||(pendingResume?Math.abs(a.i-resume)-Math.abs(b.i-resume):Math.abs(a.rect.top)-Math.abs(b.rect.top)));
   for(const {image,i} of candidates){if(active>=concurrency)break;states[i]='loading';active++;image.src=urls[i];}
   const failed=images.filter(image=>image.classList.contains('image-error')).length;
   if(tail)tail.textContent=settledCount===images.length?(failed?`${failed} halaman gagal dimuat · Gunakan tombol Coba lagi pada halaman`:'Semua halaman dimuat'):active?'Memuat halaman…':'Gulir untuk memuat halaman berikutnya';
  }
  function settled(image,i,ok){
   if(stopped||states[i]!=='loading')return;
   // Capture reading content, not scrollY: shrinking an earlier placeholder
   // requires a negative scroll adjustment to keep the same pixels in view.
   const visible=images.find(i=>i.classList.contains('loaded')&&i.getBoundingClientRect().bottom>0&&i.getBoundingClientRect().top<innerHeight);
   const anchor=visible?.parentElement||slots.find(slot=>slot.getBoundingClientRect().bottom>0);
   const anchorTop=anchor?.getBoundingClientRect().top;
   active--;states[i]=ok?'loaded':'error';
   image.classList.toggle('loaded',ok);image.classList.toggle('image-error',!ok);
   const control=retryControls[i];control.panel.hidden=ok;control.button.disabled=false;control.label.textContent=`Halaman ${Number(image.dataset.page)+1} gagal dimuat.`;
   if(ok&&image.naturalWidth){image.width=image.naturalWidth;image.height=image.naturalHeight;}
   image.hidden=false;slots[i].classList.toggle('ready',ok);
   if(anchor){const delta=anchor.getBoundingClientRect().top-anchorTop;if(delta)window.scrollBy({top:delta,behavior:'instant'});}
   settledCount=states.filter(state=>state==='loaded'||state==='error').length;
   if(pendingResume&&states[resume]!=='idle'&&states[resume]!=='loading'){
    requestAnimationFrame(()=>{
     if(stopped||interacted||!pendingResume)return;
     pendingResume=false;images[resume].scrollIntoView({block:'start',behavior:'instant'});track();pump();
    });
   }
   pump();track();
  }
  const cancelResume=()=>{interacted=true;pendingResume=false;};
  const scroll=()=>{if(frame)return;frame=requestAnimationFrame(()=>{frame=0;if(stopped)return;pump();track();});};
  const gestures=['touchstart','pointerdown','wheel','keydown'];
  gestures.forEach(type=>document.addEventListener(type,cancelResume,{passive:true}));
  window.addEventListener('scroll',scroll,{passive:true});window.addEventListener('resize',scroll,{passive:true});
  const handlers=images.map((image,i)=>{
   const load=()=>settled(image,i,true),error=()=>settled(image,i,false);
   image.addEventListener('load',load);image.addEventListener('error',error);return {load,error};
  });
  readerCleanup=()=>{
   stopped=true;cancelAnimationFrame(frame);
   images.forEach((image,i)=>{
    image.removeEventListener('load',handlers[i].load);image.removeEventListener('error',handlers[i].error);
    retryControls[i].button.removeEventListener('click',retryControls[i].retry);
   });
   gestures.forEach(type=>document.removeEventListener(type,cancelResume));
   window.removeEventListener('scroll',scroll);window.removeEventListener('resize',scroll);
  };
  // Keep each paged-mode slot and its state: returning to a failed page is not
  // permission to retry it, and an in-flight hidden page must not save progress.
  readerSelectPage=page=>{
   if(stopped||webtoon)return;
   slots.forEach((slot,i)=>{slot.hidden=i!==page;});observedPage=-1;pump();track();
  };
  pump();
 }
 function showPage(page){
  const shell=document.querySelector('.reader-shell');if(!shell||page<0||page>=Number(shell.dataset.readerCount))return;
  clearTimeout(progressTimer);readerViewed=false;
  readerPage=page;shell.dataset.readerPage=String(page);
  document.querySelector('#page-number').value=String(page+1);
  document.querySelector('[data-action="page-prev"]').disabled=page===0;document.querySelector('[data-action="page-next"]').disabled=page===Number(shell.dataset.readerCount)-1;
  document.querySelector('#reader-status').textContent=`Halaman ${page+1} / ${shell.dataset.readerCount} · Memuat halaman…`;
  history.replaceState(null,'',location.pathname+'?'+new URLSearchParams({mode:shell.dataset.readerMode,at:String(page)}));
  window.scrollTo({top:0,behavior:'instant'});readerSelectPage(page);
 }
 function movePage(delta){const shell=document.querySelector('.reader-shell');if(shell&&shell.dataset.readerMode!=='webtoon')showPage(readerPage+delta);}
 document.addEventListener('keydown',event=>{if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(event.target.tagName))return;const shell=document.querySelector('.reader-shell');if(!shell||shell.dataset.readerMode==='webtoon')return;if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();movePage((event.key==='ArrowRight'?1:-1)*(shell.dataset.readerMode==='rtl'?-1:1));}});
 window.addEventListener('pagehide',()=>{clearTimeout(progressTimer);const shell=document.querySelector('.reader-shell');if(shell&&readerViewed&&Number(shell.dataset.readerCount)&&shell.querySelector(`.reader-page[data-page="${readerPage}"]`)?.classList.contains('loaded'))saveProgress(shell,readerPage,true);if(queueSocket)queueSocket.close();});
 document.addEventListener('error',event=>{if(event.target.tagName==='IMG'){event.target.classList.add('image-error');}},true);
 async function start(){
  nav.innerHTML=U.navigation(current.name==='manga'||current.name==='reader'?'library':current.name);
  try{
   const response=await fetch('/app-session',{credentials:'same-origin',cache:'no-store'});
   if(!response.ok||response.redirected){location.assign('/login');return;}
   session=await response.json();api=U.makeAPI(session.csrfToken);
   document.querySelector('#account-name').textContent=session.username||'Admin';
   prefs=await api('/api/preferences');applyTheme();await load();
  }catch(error){main.innerHTML=`<section class="empty"><h1>Tidak dapat menyiapkan aplikasi</h1><p>${e(error.message)}</p><a class="button" href="/login">Masuk kembali</a></section>`;}
 }
 window.MihonReady=start();
})();
