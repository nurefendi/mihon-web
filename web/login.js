(()=>{
 'use strict';
 const password=document.querySelector('#password'),toggle=document.querySelector('#toggle-password'),error=document.querySelector('#login-error'),form=document.querySelector('#login-form');
 toggle.addEventListener('click',()=>{const visible=password.type==='password';password.type=visible?'text':'password';toggle.textContent=visible?'Sembunyikan':'Lihat';toggle.setAttribute('aria-label',visible?'Sembunyikan kata sandi':'Tampilkan kata sandi');toggle.setAttribute('aria-pressed',String(visible));});
 const warning=document.querySelector('#caps-warning');password.addEventListener('keyup',event=>{warning.hidden=!event.getModifierState?.('CapsLock');});
 error.hidden=!new URLSearchParams(location.search).has('error');
 form.addEventListener('submit',async event=>{
  // Progressive enhancement: without JS, the same real URL-encoded form still works.
  event.preventDefault();const button=document.querySelector('.login-submit');button.disabled=true;button.textContent='Memverifikasi…';error.hidden=true;
  try{
   const body=new URLSearchParams();for(const [key,value] of new FormData(form))body.append(key,String(value));
   const response=await fetch('/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},body,cache:'no-store'});
   if(response.ok){location.assign('/library');return;}
   error.textContent=response.status===429?'Terlalu banyak percobaan masuk. Tunggu beberapa saat sebelum mencoba kembali.':response.status===403?'Akses ditolak. Buka aplikasi melalui alamat resminya lalu coba kembali.':response.status===401?'Nama pengguna atau kata sandi tidak cocok. Periksa kembali dan coba lagi.':'Server belum dapat memproses login ('+response.status+'). Coba lagi atau hubungi administrator.';
  }catch{error.textContent='Tidak dapat terhubung ke server. Periksa koneksi lalu coba kembali.';}
  finally{button.disabled=false;button.textContent='Masuk →';}
  error.hidden=false;error.scrollIntoView?.({block:'nearest',behavior:'smooth'});
 });
})();
