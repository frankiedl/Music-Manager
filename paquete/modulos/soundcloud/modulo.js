/* «soundcloud» module: uploads an album (or one song) to the user's own SoundCloud account, with its info.
   - Menu section «SoundCloud»: connect (3 steps: create an app, register the Redirect URI, paste Client ID/Secret → «Conectar»
     opens the SoundCloud authorize page; OAuth 2.1 + PKCE run in servidor.py), disconnect, and the list of uploads.
   - Album tab «SoundCloud» and song action «Subir a SoundCloud»: preview table (song, file, size, title, privacy) → confirm →
     sequential upload with progress per track → optional album set in album order → links. Failed tracks can be retried alone.
   - Publications: every upload/update creates or updates the song's «SoundCloud · Adelanto» entry (URL, urn, privacy) and a set
     is stored at album level, through GM.pub (the «publicaciones» module); a public upload offers the phase «Adelanto».
     Without that module everything else works the same (the «☁ SoundCloud» badge comes back).
   - Numbers: «Actualizar números de SoundCloud» (menu section) and, once a day, on opening a song page: GET /tracks/{urn}
     server side, sequential, 429-aware; kept in numeros.json and mirrored into the publication entry (GM.pub.numeros).
   Credentials and tokens live only in datos/modulos/soundcloud/cuenta.json (server side). GM.state('soundcloud') keeps only
   form preferences per album (genre, tags, description…), never secrets. */
(function(){
const ID='soundcloud';
const E=s=>GM.ui.esc(s==null?'':String(s));
const T=s=>(window.T||(x=>x))(s);
const S=()=>{const st=GM.state(ID);if(!st.alb)st.alb={};return st};
const nrm=s=>String(s==null?'':s).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const LIC=[['all-rights-reserved','Todos los derechos reservados'],['cc-by','Creative Commons: atribución'],['cc-by-sa','Creative Commons: atribución, compartir igual'],
  ['cc-by-nd','Creative Commons: atribución, sin obras derivadas'],['cc-by-nc','Creative Commons: atribución, no comercial'],
  ['cc-by-nc-sa','Creative Commons: no comercial, compartir igual'],['cc-by-nc-nd','Creative Commons: no comercial, sin obras derivadas'],['no-rights-reserved','Sin derechos reservados (dominio público)']];
const PRIV=[['private','Privada'],['public','Pública']];
let EST=null,SUB={songs:{},sets:{}},NUM={};

async function estado(me){try{EST=await GM.api(ID,'estado'+(me?'?me=1':''))}catch(e){EST={ok:false}}return EST}
async function cargarSubidas(){try{const r=await GM.api(ID,'subidas');if(r&&r.ok)SUB={songs:r.songs||{},sets:r.sets||{}}}catch(e){}
  try{const r=await GM.api(ID,'numeros');if(r&&r.ok)NUM=r.numeros||{}}catch(e){}}

/* ---------- publications (through GM.pub, the «publicaciones» module; everything here works without it) ---------- */
const fechaDe=t=>String(t||'').slice(0,10);
function entradaDe(v){return {plat:'SoundCloud',tipo:'pre',fecha:fechaDe(v.t),url:v.url||'',urn:v.urn||'',priv:v.sharing==='public'?'public':'private',auto:'sc'}}
/* after an upload/update: create or update the song's «SoundCloud · Adelanto» entry (matched by urn) */
function apuntar(id,v){if(!GM.pub||!v||!v.urn)return;GM.pub.upsert(id,entradaDe(v))}
/* uploads made before (or while the publications module was off) get their entry too, with the numbers already read */
function sincronizar(ids){
  if(!GM.pub)return;
  (ids||Object.keys(SUB.songs||{})).forEach(id=>{const v=(SUB.songs||{})[id];if(!v||!v.urn||!GM.song(id))return;
    if(!GM.pub.list(id).some(e=>e.urn===v.urn)){GM.pub.upsert(id,entradaDe(v));((NUM[id]||{}).hist||[]).forEach(h=>GM.pub.numeros(id,v.urn,h))}})}
/* the SoundCloud tracks of a song: from the upload record and from its publication entries */
function urnsDe(id){const L=[];const v=(SUB.songs||{})[id];if(v&&v.urn)L.push(v.urn);
  if(GM.pub)GM.pub.list(id).forEach(e=>{if(e.urn&&/^soundcloud:tracks:/.test(e.urn)&&!L.includes(e.urn)&&nrm(e.plat)==='soundcloud')L.push(e.urn)});return L}
function todosUrns(){
  const ids=new Set([...Object.keys(SUB.songs||{}),...(GM.pub?GM.songs.map(s=>s.id):[])]);
  return [...ids].flatMap(id=>urnsDe(id).slice(0,1).map(urn=>({id,urn})))}
/* reads plays/likes/comments/reposts (GET /tracks/{urn}, sequential, server side) and keeps them as dated numbers */
async function leerNumeros(items,auto,alAvanzar){
  const r=await GM.api(ID,'numeros',{items,si_no_hoy:!!auto}).catch(e=>({ok:false,error:String(e)}));
  if(!r||!r.ok||r.nada)return r;
  let q=null;
  for(;;){await sleep(auto?1500:800);
    q=await GM.api(ID,'progreso?job='+encodeURIComponent(r.job)).catch(()=>null);
    if(!q)continue;if(!q.ok)break;
    if(alAvanzar)alAvanzar(q);
    if(q.estado==='hecho'||q.estado==='error')break}
  if(q&&q.resultados)Object.entries(q.resultados).forEach(([id,x])=>{const {urn,...fila}=x;
    NUM[id]=NUM[id]||{urn,hist:[]};NUM[id].hist=[...(NUM[id].hist||[]).filter(h=>h.f!==fila.f),fila];
    if(GM.pub)GM.pub.numeros(id,urn,fila)});
  return q}
const hoy=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')};
const vistos={};   // songs whose numbers were already asked for today (this session)
GM.on('cancion',async s=>{
  try{
    if(!s||vistos[s.id]===hoy())return;vistos[s.id]=hoy();
    sincronizar([s.id]);
    const u=urnsDe(s.id)[0];if(!u||!navigator.onLine)return;
    if(!EST)await estado();if(!EST||!EST.conectado)return;
    await leerNumeros([{id:s.id,urn:u}],true);
  }catch(e){}});
GM.on('movidas',pares=>{   // an album folder moved (a project published as an album): its preferences and its set follow it
  const st=S();let n=0;pares.forEach(([a,b])=>{if(st.alb[a]&&!st.alb[b]){st.alb[b]=st.alb[a];delete st.alb[a];n++}});if(n)GM.save();
  GM.api(ID,'claves',{pares}).then(cargarSubidas).catch(()=>{})});
const fmt=n=>n>=1073741824?(n/1073741824).toFixed(2)+' GB':(n/1048576).toFixed(1)+' MB';
const opts=(L,v)=>L.map(([k,n])=>`<option value="${E(k)}"${k===v?' selected':''}>${E(n)}</option>`).join('');
const errHtml=r=>r?`<span>${E(r.error||'Error')}</span>${r.espera?` <span>${E(`Espera ${r.espera} s y vuelve a intentarlo.`)}</span>`:''}${r.detalle?` <span class="notr sc-det">(${E(r.detalle)})</span>`:''}`:'';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

/* ---------- connect screen (menu section) ---------- */
async function render(el){
  el.innerHTML='<h1>SoundCloud</h1><div class="meta">Cargando…</div>';
  await estado(true);await cargarSubidas();pintar(el)}
function pintar(el){
  const st=EST||{};
  const prueba=st.prueba?'<div class="callout">Modo de prueba: el gestor está usando un servidor de SoundCloud simulado, no el de verdad.</div>':'';
  const puerto=st.ok&&!st.puerto_ok?`<div class="callout sc-warn"><b>Otro programa usa el puerto 8765</b><ol class="sc-opc"><li>Cierra el otro programa y vuelve a abrir el gestor.</li><li>O registra también esta dirección en SoundCloud:</li></ol><div class="sc-url"><code class="notr">${E(st.redirect_uri)}</code><button class="chip" data-sc="copiar" data-u="${E(st.redirect_uri)}">Copiar</button></div></div>`:'';
  el.innerHTML=`<h1>SoundCloud</h1><p class="lead">Sube un álbum o una canción a tu cuenta de SoundCloud con sus datos. Antes de subir verás siempre una vista previa: no se sube nada sin que lo confirmes.</p>${prueba}
   ${!st.ok?'<div class="callout">No se pudo leer el estado de SoundCloud.</div>':st.conectado?conectadoHtml(st):pasosHtml(st)}${puerto}
   ${st.conectado?'<ol class="flowbar"><li>Abre un álbum o una canción</li><li>Pulsa «Subir a SoundCloud»</li><li>Revisa la vista previa y confirma</li></ol>':''}
   ${listaSubidas()}
   ${st.conectado?`<div class="sc-cols"><div class="panel"><h3>Números</h3><p class="meta">Reproducciones, me gusta, comentarios y reposts de tus pistas. Se guardan con su fecha (uno por día) para ver cómo crecen. Al abrir una canción se actualizan solos una vez al día.</p>
      <div class="sc-acts"><button class="chip pri" data-sc="numeros">↻ Actualizar números</button><span id="sc-num" class="meta"></span></div></div>
     <div class="panel"><h3>ISRC</h3><p class="meta">Si SoundCloud ya ha asignado un ISRC a tus pistas (por ejemplo al activar la monetización), puedes traerlos aquí y guardarlos como registro «ISRC» de cada canción. No se cambia nada sin que lo confirmes.</p>
      <div class="sc-acts"><button class="chip pri" data-sc="isrc">⇩ Traer los ISRC</button></div></div></div>
     <details class="panel sc-how"><summary>Cómo subir</summary><p class="meta">Abre un álbum y entra en su pestaña «SoundCloud», o en la página de una canción pulsa «Subir a SoundCloud». Las pistas se suben privadas salvo que elijas otra cosa.</p>${GM.pub?'<p class="meta">Cada subida se apunta sola en «Publicado en» de la canción (SoundCloud · Adelanto) con su enlace.</p>':''}</details>`:''}`;
  sincronizar();
  el.onclick=async ev=>{
    const b=ev.target.closest('[data-sc]');if(!b)return;const k=b.dataset.sc;if(k==='copiar'){try{navigator.clipboard.writeText(b.dataset.u||'');GM.ui.toast('Dirección copiada')}catch(e){GM.ui.toast('No se pudo copiar')}return}
    if(k==='numeros'){if(b.disabled)return;const items=todosUrns(),m=el.querySelector('#sc-num');
      if(!items.length)return GM.ui.toast('No hay ninguna pista de SoundCloud con su identificador');
      b.disabled=true;if(m)m.textContent=T('Leyendo…');
      const q=await leerNumeros(items,false,q=>{if(m)m.textContent=q.esperando?T(`SoundCloud pide esperar ${q.esperando} s…`):`${q.hechos} / ${q.total}`});
      b.disabled=false;
      if(!q||!q.ok||q.estado==='error'){if(m)m.innerHTML=`<span class="sc-err">${errHtml(q)}</span>`;return}
      const n=Object.keys(q.resultados||{}).length,mal=(q.errores||[]).length;
      pintar(el);GM.ui.toast(mal?`Números actualizados: ${n} canciones · ${mal} no se pudieron leer`:`Números actualizados: ${n} canciones`);return}
    if(k==='isrc')return traerIsrc(b);
    if(k==='copiar'){try{await navigator.clipboard.writeText(b.dataset.v);GM.ui.toast('Copiado')}catch(e){GM.ui.toast('No se pudo copiar')}return}
    if(k==='song')return GM.ui.go('song',b.dataset.id);
    if(k==='conectar')return conectar(el);
    if(k==='desc'){if(!await GM.ui.ask('¿Desconectar SoundCloud?','Se borran las claves de acceso guardadas en este ordenador. Lo que ya subiste no cambia. El Client ID y el Client Secret se conservan para volver a conectar.','Desconectar'))return;
      await GM.api(ID,'desconectar',{}).catch(()=>{});GM.ui.toast('SoundCloud desconectado');await estado();return pintar(el)}
    if(k==='olvidar'){if(!await GM.ui.ask('¿Borrar las credenciales?','Se borran de este ordenador el Client ID, el Client Secret y las claves de acceso. Para volver a conectar tendrás que pegarlos otra vez.','Borrar'))return;
      await GM.api(ID,'borrar_credenciales',{}).catch(()=>{});GM.ui.toast('Credenciales borradas');await estado();return pintar(el)}}}
async function traerIsrc(b){
  if(!window.DER||!DER.asignar)return GM.ui.toast('Para guardar los ISRC hace falta el módulo Derechos');
  b.disabled=true;const r=await GM.api(ID,'catalogo').catch(()=>null);b.disabled=false;
  if(!r||!r.ok)return GM.ui.toast('No se pudo leer tu catálogo de SoundCloud');
  /* each SoundCloud track → its song: first by the upload recorded here (urn), then by the exact title (without accents or case) */
  const nr=x=>String(x||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
  const porUrn=new Map(Object.entries((SUB&&SUB.songs)||{}).map(([id,v])=>[v.urn,id])),porTit=new Map();
  GM.songs.forEach(s=>{if(GM.isDraft(s))return;const k=nr(GM.title(s));if(k)porTit.set(k,porTit.has(k)?null:s.id)}); // null = two songs with the same title: ambiguous
  const M=new Map(),sin=[];
  (r.pistas||[]).forEach(p=>{const id=porUrn.get(p.urn)||porTit.get(nr(p.titulo));if(!id||!GM.song(id))return sin.push(p.titulo);
    const a=M.get(id)||{v:{isrc:''},n:0,isrcs:new Set()};a.n++;if(p.isrc){a.isrcs.add(p.isrc);a.v=p}else if(!a.v.isrc)a.v=p;M.set(id,a)});
  const rows=[...M.entries()].map(([id,a])=>{const s=GM.song(id),v={isrc:[...a.isrcs][0]||''};
    const ex=DER.regsOf(s).find(e=>String(e.soc).toLowerCase()==='isrc'&&e.cod);
    const st=a.isrcs.size>1?'ambiguo':!v.isrc?'vacio':!ex?'nuevo':String(ex.cod).toUpperCase()===v.isrc?'igual':'distinto';return {s,v,ex,st}})
    .sort((x,y)=>({nuevo:0,distinto:1,ambiguo:2,vacio:3,igual:4}[x.st]-{nuevo:0,distinto:1,ambiguo:2,vacio:3,igual:4}[y.st])||GM.title(x.s).localeCompare(GM.title(y.s),'es'));
  const nuevos=rows.filter(x=>x.st==='nuevo'),tag={nuevo:'se asignará',igual:'ya lo tiene',distinto:'tiene otro distinto: no se toca',vacio:'SoundCloud aún no tiene ISRC',ambiguo:'SoundCloud tiene varios ISRC para ella: revísalo'};
  const mal=sin;
  const o=GM.ui.modal(`<h3>ISRC de SoundCloud</h3><div style="max-height:55vh;overflow:auto">${rows.map(x=>`<div class="meta" style="display:flex;gap:12px;justify-content:space-between;padding:5px 0"><span>${E(GM.title(x.s))}</span><span><b class="notr">${E(x.v.isrc||'—')}</b> · ${E(T(tag[x.st]))}${x.st==='distinto'?` (<span class="notr">${E(x.ex.cod)}</span>)`:''}</span></div>`).join('')||'<div class="meta">No hay pistas subidas desde aquí.</div>'}</div>
   ${mal.length?`<p class="meta">${E(T('Pistas de SoundCloud que no coinciden con ninguna canción (no se tocan)'))}: ${E(mal.join(', '))}</p>`:''}
   <div class="sc-acts" style="margin-top:14px"><button class="chip pri" id="isrc-ok"${nuevos.length?'':' disabled'}>Asignar ${nuevos.length} ISRC</button><button class="chip" id="isrc-chk" title="Pregunta al catálogo público de Deezer (sin cuenta) si cada ISRC está a la venta. Solo salen de aquí los ISRC.">🔎 Comprobar cuáles están publicados</button><button class="chip" id="isrc-no">Cerrar</button></div><div id="isrc-res"></div>`);
  o.querySelector('#isrc-no').onclick=()=>o.remove();
  o.querySelector('#isrc-chk').onclick=async ev=>{
    const btn=ev.target,L=rows.filter(x=>x.v.isrc),res={};btn.disabled=true;
    for(let i=0;i<L.length;i+=30){btn.textContent=`Comprobando ${Math.min(i+30,L.length)} / ${L.length}…`;
      const q=await GM.api(ID,'disponible',{isrcs:L.slice(i,i+30).map(x=>x.v.isrc)}).catch(()=>null);if(q&&q.ok)Object.assign(res,q.res)}
    btn.textContent='🔎 Comprobar cuáles están publicados';btn.disabled=false;
    const g=x=>res[x.v.isrc]||{},si=L.filter(x=>g(x).ok===true),no=L.filter(x=>g(x).ok===false),dudas=L.filter(x=>g(x).ok==null),aPub=si.filter(x=>!GM.isPub(x.s));
    o.querySelector('#isrc-res').innerHTML=`<div class="callout" style="margin-top:12px"><div><b>${si.length}</b> disponibles en Deezer · <b>${no.length}</b> no encontradas${dudas.length?` · ${dudas.length} sin poder comprobar (inténtalo de nuevo)`:''}.</div>
      ${no.length?`<div class="meta" style="margin-top:6px">${E(T('No encontradas'))}: ${E(no.map(x=>GM.title(x.s)).join(', '))}</div>`:''}
      <div class="meta" style="margin-top:6px">${aPub.length?`${aPub.length} de las disponibles no figuran aquí como «Publicada».`:'Todas las disponibles ya figuran como «Publicada».'}</div>
      ${aPub.length&&GM.pub?`<button class="chip pri" id="isrc-pub" style="margin-top:8px">Pasar ${aPub.length} a «Publicada»…</button>`:''}</div>`;
    const bp=o.querySelector('#isrc-pub');if(bp)bp.onclick=()=>{o.remove();GM.pub.fase(aPub.map(x=>x.s.id),'pub',{preguntar:true,titulo:`¿Pasar ${aPub.length} canciones a «Publicada»?`})}};
  o.querySelector('#isrc-ok').onclick=()=>{let n=0;nuevos.forEach(x=>{if(DER.asignar(x.s,'ISRC',x.v.isrc,'Asignado por SoundCloud')==='nuevo')n++});GM.save();o.remove();GM.ui.toast(n+' ISRC guardados')}}
function conectadoHtml(st){
  const u=st.usuario||{};
  return `<div class="panel sc-cuenta"><div class="sc-dot ok"></div><div class="sc-grow"><b>Conectado</b> <span>a la cuenta</span> ${u.permalink_url?`<a class="notr" href="${E(u.permalink_url)}" target="_blank" rel="noopener">${E(u.username||u.permalink_url)}</a>`:`<span class="notr">${E(u.username||'')}</span>`}
    <div class="meta"><span>App</span> <code class="notr">${E(st.client_id)}</code>${st.segundos_libres!=null?` · <span>${E(`Te quedan ${Math.floor(st.segundos_libres/60)} minutos de subida`)}</span>`:''}</div>
    ${st.aviso?`<div class="sc-err">${errHtml(st.aviso)}</div>`:''}</div>
    <button class="chip" data-sc="desc">Desconectar</button></div>`}
function pasosHtml(st){
  return `<div class="sc-pasos">
   <div class="sc-paso"><div class="sc-n">1</div><div class="sc-grow"><b>Crea una app en SoundCloud</b>
     <div class="meta">Necesitas una cuenta de SoundCloud Artist Pro. Abre esta página, inicia sesión y registra una aplicación nueva (el nombre da igual).</div>
     <a class="chip" href="https://soundcloud.com/you/apps" target="_blank" rel="noopener"><code class="notr">soundcloud.com/you/apps</code> ↗</a></div></div>
   <div class="sc-paso"><div class="sc-n">2</div><div class="sc-grow"><b>Pon esta Redirect URI, exactamente igual</b>
     <div class="meta">En los datos de la app, en el campo «Redirect URI».</div>
     <div class="sc-uri"><code class="notr">${E(st.redirect_oficial||'')}</code><button class="chip" data-sc="copiar" data-v="${E(st.redirect_oficial||'')}">Copiar</button></div></div></div>
   <div class="sc-paso"><div class="sc-n">3</div><div class="sc-grow"><b>Pega aquí el Client ID y el Client Secret</b>
     <div class="meta">Los dos aparecen en la página de tu app. Se guardan solo en la carpeta datos de este ordenador.</div>
     <div class="sc-form"><label><span>Client ID</span><input id="sc-cid" autocomplete="off" spellcheck="false" value="${E(st.client_id||'')}"></label>
     <label><span>Client Secret</span><input id="sc-sec" type="password" autocomplete="off" spellcheck="false" placeholder="${st.tiene_secreto?E(T('Guardado')+': '+st.secreto+' · '+T('déjalo vacío para mantenerlo')):''}"></label></div>
     <div class="sc-acts"><button class="chip pri" data-sc="conectar">Conectar</button>${st.client_id?'<button class="chip" data-sc="olvidar">Borrar credenciales</button>':''}<span id="sc-espera" class="meta"></span></div></div></div>
  </div>`}
async function conectar(el){
  const cid=(el.querySelector('#sc-cid').value||'').trim(),sec=(el.querySelector('#sc-sec').value||'').trim();
  if(!cid||(!sec&&!(EST&&EST.tiene_secreto)))return GM.ui.toast('Pega el Client ID y el Client Secret');
  const w=window.open('about:blank','_blank');   // opened now (user gesture) so the browser does not block it
  let r=await GM.api(ID,'credenciales',{client_id:cid,client_secret:sec}).catch(e=>({ok:false,error:String(e)}));
  if(r&&r.ok)r=await GM.api(ID,'conectar',{}).catch(e=>({ok:false,error:String(e)}));
  if(!r||!r.ok){if(w)w.close();return GM.ui.toast(T('No se pudo conectar')+(r&&r.error?': '+T(r.error):''))}
  if(w)w.location.href=r.url;
  const msg=el.querySelector('#sc-espera');
  if(msg)msg.innerHTML=w?'<span>Esperando a que autorices la app en SoundCloud…</span>':`<a href="${E(r.url)}" target="_blank" rel="noopener">Abrir la página de SoundCloud</a>`;
  for(let i=0;i<150;i++){await sleep(2000);if(!el.isConnected)return;
    const st=await estado();if(st&&st.conectado){GM.ui.toast('Conectado a SoundCloud ✓');await estado(true);return pintar(el)}}
  if(msg)msg.textContent='';}
function listaSubidas(){
  const sets=Object.values(SUB.sets||{}),songs=Object.entries(SUB.songs||{});
  if(!sets.length&&!songs.length)return '';
  const row=(t,url,meta,id)=>`<div class="sc-hrow">${id?`<button class="chip" data-sc="song" data-id="${E(id)}" title="Abrir la canción">♪</button>`:'<span class="sc-ic">💿</span>'}<span class="sc-grow notr">${E(t)}</span>${meta}${url?`<a class="chip" href="${E(url)}" target="_blank" rel="noopener">Abrir en SoundCloud ↗</a>`:''}</div>`;
  const priv=x=>`<span class="b ${x.sharing==='public'?'ok':''}">${x.sharing==='public'?'Pública':'Privada'}</span>`;
  return `<h2>Subidas <span class="meta">${songs.length}</span></h2><div class="panel sc-hist">
   ${sets.map(x=>row(x.titulo,x.url,`<span class="b">${x.set_type==='playlist'?'Lista':'Álbum'}</span><span class="meta">${E(`${(x.pistas||[]).length} pistas`)}</span>`)).join('')}
   ${songs.sort((a,b)=>String(b[1].t).localeCompare(String(a[1].t))).map(([id,x])=>row(x.titulo,x.url,`${priv(x)}${numTxt(id)}<span class="meta">${E(x.t||'')}</span>`,GM.song(id)?id:'')).join('')}</div>`}
function numTxt(id){const h=((NUM[id]||{}).hist||[]).slice(-1)[0];if(!h)return '';
  return `<span class="meta" title="${E(h.f)}">${[['plays','▶'],['likes','♥'],['comments','💬'],['reposts','↻']].filter(([k])=>h[k]!=null).map(([k,ic])=>ic+' '+h[k]).join(' · ')}</span>`}

/* ---------- album / song: preview → confirm → upload ---------- */
function versiones(s){return (s.versions||[]).filter(v=>v&&v.p)}
const esMaster=p=>/\/master\//i.test(p||'');
const sinPerdida=p=>/\.(wav|wave|aiff?|flac)$/i.test(p||'');
/* best audio: the master (master/ folder; the final one if it is there, else lossless and newest), else the final or best version */
function fuente(s){
  const v=versiones(s),fin=GM.finalPath(s),M=v.filter(x=>esMaster(x.p));
  if(M.length){const f=M.find(x=>x.p===fin);if(f)return f.p;return [...M].sort((a,b)=>(sinPerdida(b.p)-sinPerdida(a.p))||((b.mt||0)-(a.mt||0)))[0].p}
  return fin||GM.bestVersion(s)||(v[0]&&v[0].p)||''}
function isrcDe(s){try{const r=window.DER&&DER.regsOf?DER.regsOf(s):[];const x=r.find(e=>nrm(e.soc)==='isrc'&&e.cod);return x?x.cod:''}catch(e){return ''}}
function grupoDe(s){return {key:'song:'+s.id,title:GM.title(s),songs:[s],cover:GM.cover(s),kind:'song'}}

function prefs(g){
  const m=(GM.state('masterizado')||{})[g.key]||{},a=S().alb[g.key]||{};
  const tags=[...new Set(g.songs.flatMap(s=>GM.tags(s)||[]))].slice(0,15).join(', ');
  return {priv:a.priv||'private',genre:a.genre!=null?a.genre:(m.genero||''),tags:a.tags!=null?a.tags:tags,desc:a.desc||'',letra:!!a.letra,caratula:a.caratula!==false,
    fecha:a.fecha!=null?a.fecha:((g.album&&g.album.date)||''),sello:a.sello!=null?a.sello:(GM.cfg.titular||GM.cfg.artista||''),lic:a.lic||'all-rights-reserved',
    set:a.set!==false&&g.songs.length>1,setTit:a.setTit||g.title,setTipo:a.setTipo||'album',setPriv:a.setPriv||a.priv||'private'}}

async function panel(el,g,dlg){
  el.innerHTML='<div class="meta">Cargando…</div>';
  await estado();
  if(!EST||!EST.ok||!EST.conectado){
    el.innerHTML=`<div class="panel sc-cuenta"><div class="sc-dot"></div><div class="sc-grow"><b>SoundCloud no está conectado</b><div class="meta">Conecta tu cuenta una vez (tres pasos) y vuelve aquí para subir «${E(g.title)}».</div></div><button class="chip pri" data-x="ir">Conectar SoundCloud</button></div>`;
    el.onclick=ev=>{if(ev.target.closest('[data-x="ir"]')){if(dlg)dlg.remove();GM.ui.go('mod:'+ID)}};return}
  const P={g,o:prefs(g),busy:false,rows:GM.order&&g.songs.length>1?GM.order(g):g.songs.slice()};
  P.rows=P.rows.map((s,i)=>({s,n:i+1,p:fuente(s),titulo:GM.title(s),sharing:P.o.priv,sel:!GM.isDraft(s),isrc:isrcDe(s),accion:'subir',estado:'',pct:0}));
  const cover=g.cover&&g.cover.p?g.cover.p:'';
  let r=await GM.api(ID,'preparar',{key:g.key,portada:cover,items:P.rows.map(x=>({id:x.s.id,p:x.p}))}).catch(e=>({ok:false,error:String(e)}));
  if(!r||!r.ok){el.innerHTML=`<div class="callout">${errHtml(r)}</div>`;return}
  P.portada=r.portada;P.setPrev=r.set;P.setAccion=r.set?'actualizar':'nuevo';
  r.items.forEach((it,i)=>{const x=P.rows[i];x.info=it;if(it.subida){x.accion='saltar';x.res=it.subida}if(!it.ok)x.sel=false});
  P.el=el;P.dlg=dlg;
  try{P.pend=!!(GM.mods&&GM.mods.masterizado&&GM.mods.masterizado.pendiente&&g.songs.length>1&&GM.mods.masterizado.pendiente(g))}catch(e){P.pend=false}
  dibujar(P)}

async function info(P,x){   // re-reads one row after choosing another file
  const r=await GM.api(ID,'preparar',{key:P.g.key,items:[{id:x.s.id,p:x.p}]}).catch(()=>null);
  if(r&&r.ok&&r.items[0]){x.info=r.items[0];if(!x.info.ok)x.sel=false}dibujar(P)}

function filaHtml(P,x,i){
  const it=x.info||{},vs=versiones(x.s),ya=it.subida;
  const st=x.estado==='subiendo'?`<div class="sc-bar"><i style="width:${x.pct}%"></i></div><span class="meta">${E(`Subiendo… ${x.pct} %`)}</span>`
    :x.estado==='ok'?`<span class="b ok">✓ Subida</span>${x.res&&x.res.url?` <a href="${E(x.res.url)}" target="_blank" rel="noopener">Abrir ↗</a>`:''}${x.sinCaratula?'<div class="meta">Sin carátula: SoundCloud no la aceptó.</div>':''}`
    :x.estado==='act'?`<span class="b ok">✓ Datos actualizados</span>${x.res&&x.res.url?` <a href="${E(x.res.url)}" target="_blank" rel="noopener">Abrir ↗</a>`:''}`
    :x.estado==='error'?`<span class="b no">✗ Falló</span><div class="sc-err">${errHtml(x.err)}</div>`
    :x.estado==='saltada'?'<span class="meta">No se vuelve a subir</span>'
    :x.estado==='espera'?'<span class="meta">En cola</span>'
    :!it.ok?`<span class="b no">✗</span> <span class="sc-err">${E(it.error||'')}</span>`
    :ya?'<span class="b warn">Ya subida</span>':'<span class="meta">Lista para subir</span>';
  return `<tr class="${x.sel?'':'sc-off'}" data-i="${i}">
   <td><input type="checkbox" data-f="sel"${x.sel?' checked':''}${it.ok?'':' disabled'}${P.busy?' disabled':''} title="Incluir"></td>
   <td class="meta">${x.n}</td>
   <td><input class="sc-in notr" data-f="titulo" value="${E(x.titulo)}"${P.busy?' disabled':''}>
     ${GM.isDraft(x.s)?'<div class="meta">Boceto: su letra nunca se comparte.</div>':''}${x.isrc?`<div class="meta">ISRC <span class="notr">${E(x.isrc)}</span></div>`:''}
     ${ya?`<div class="sc-ya"><span class="meta">Ya está en SoundCloud</span>${ya.url?` <a href="${E(ya.url)}" target="_blank" rel="noopener">↗</a>`:''}
       <select data-f="accion"${P.busy?' disabled':''}>${opts([['saltar','No subirla otra vez'],['actualizar','Actualizar sus datos'],['subir','Subirla otra vez (duplicada)']],x.accion)}</select></div>`:''}</td>
   <td>${vs.length>1?`<select class="sc-file notr" data-f="p"${P.busy?' disabled':''}>${vs.map(v=>`<option value="${E(v.p)}"${v.p===x.p?' selected':''}>${E(v.p.split('/').pop())}</option>`).join('')}</select>`:`<span class="notr">${E((x.p||'').split('/').pop()||'—')}</span>`}
     ${esMaster(x.p)?' <span class="b ok">Máster</span>':''}</td>
   <td class="meta">${it.ok?fmt(it.bytes):''}</td>
   <td><select data-f="sharing"${P.busy||(ya&&x.accion==='saltar')?' disabled':''}>${opts(PRIV,x.sharing)}</select></td>
   <td class="sc-st">${st}</td></tr>`}

function dibujar(P){
  const {g,o}=P,cv=P.portada,uno=g.songs.length===1;
  const user=(EST.usuario||{}).username||'';
  P.el.innerHTML=`<div class="sc-panel">
   <div class="sc-top"><div><b>${uno?'Subir esta canción a SoundCloud':'Subir este álbum a SoundCloud'}</b><div class="meta"><span>Cuenta</span> <span class="notr">${E(user)}</span>${EST.prueba?' · <span>modo de prueba</span>':''}</div></div>
     ${EST.puerto_ok?'':'<span class="b warn" title="La Redirect URI necesita el puerto 8765">Puerto distinto de 8765</span>'}</div>
   ${P.pend?`<div class="callout"><b>Tu masterizado tiene cambios que aún no están guardados.</b> Si subes ahora, saldrían los archivos anteriores. <div style="margin-top:8px"><button class="chip pri" data-x="masterizar"${P.busy?' disabled':''}>Aplicar mi masterizado y guardar los másters</button></div></div>`:''}
   <div class="sc-scroll"><table class="sc-tab"><thead><tr><th><input type="checkbox" data-f="todas"${P.busy?' disabled':''} title="Todas"></th><th>#</th><th>Título en SoundCloud</th><th>Archivo</th><th>Tamaño</th><th>Privacidad</th><th>Estado</th></tr></thead>
   <tbody>${P.rows.map((x,i)=>filaHtml(P,x,i)).join('')}</tbody></table></div>
   <details class="sc-det-box"${P.busy?'':' open'}><summary>Datos que se envían</summary><div class="sc-grid">
    <label><span>Privacidad de todas</span><select data-o="priv">${opts(PRIV,o.priv)}</select></label>
    <label><span>Género</span><input data-o="genre" value="${E(o.genre)}" maxlength="100"></label>
    <label class="sc-ancho"><span>Etiquetas (separadas por comas)</span><input class="notr" data-o="tags" value="${E(o.tags)}"></label>
    <label><span>Fecha de lanzamiento</span><input type="date" data-o="fecha" value="${E(o.fecha)}"></label>
    <label><span>Sello / copyright</span><input class="notr" data-o="sello" value="${E(o.sello)}"></label>
    <label class="sc-ancho"><span>Licencia</span><select data-o="lic">${opts(LIC,o.lic)}</select></label>
    <label class="sc-ancho"><span>Descripción</span><textarea data-o="desc" rows="3">${E(o.desc)}</textarea></label>
    <label class="sc-chk sc-ancho"><input type="checkbox" data-o="letra"${o.letra?' checked':''}> <span>Poner la letra en la descripción</span></label>
    <label class="sc-chk sc-ancho"><input type="checkbox" data-o="caratula"${o.caratula&&cv&&cv.ok?' checked':''}${cv&&cv.ok?'':' disabled'}>
      ${cv&&cv.ok&&g.cover&&g.cover.t?`<img class="sc-cov" src="${E(GM.thumbUrl(g.cover))}" alt="">`:''}
      <span>${cv&&cv.ok?'Usar la portada como carátula':cv?E(cv.error):'No hay portada'}</span></label>
    ${cv&&cv.ok?'<div class="meta sc-ancho">La carátula necesita Artist Pro: si SoundCloud no la acepta, la pista se sube sin ella y te aviso.</div>':''}
    ${uno?'':`<div class="sc-ancho sc-set"><label class="sc-chk"><input type="checkbox" data-o="set"${o.set?' checked':''}> <b>Crear el álbum en SoundCloud (set) con estas canciones, en este orden</b></label>
      ${P.setPrev?`<div class="meta"><span>Ya subiste este álbum:</span> <a href="${E(P.setPrev.url)}" target="_blank" rel="noopener" class="notr">${E(P.setPrev.titulo)}</a></div>
        <label><span>¿Qué hago con él?</span><select data-p="setAccion">${opts([['actualizar','Actualizar ese álbum (sus pistas y su orden)'],['nuevo','Crear otro álbum nuevo']],P.setAccion)}</select></label>`:''}
      <div class="sc-grid"><label><span>Título del álbum</span><input class="notr" data-o="setTit" value="${E(o.setTit)}"></label>
      <label><span>Tipo</span><select data-o="setTipo">${opts([['album','Álbum'],['playlist','Lista de reproducción']],o.setTipo)}</select></label>
      <label><span>Privacidad del álbum</span><select data-o="setPriv">${opts(PRIV,o.setPriv)}</select></label></div></div>`}
   </div></details>
   <div class="sc-resumen" id="sc-res">${resumenHtml(P)}</div>
   <div class="sc-acts">${P.busy?'<span class="meta">Subiendo… no cierres esta página.</span>':`<button class="chip pri" data-x="subir">Revisar y subir…</button>${P.rows.some(x=>x.estado==='error')?'<button class="chip" data-x="reintentar">Reintentar las que fallaron</button>':''}`}${P.dlg&&!P.busy?'<button class="chip" data-x="cerrar">Cerrar</button>':''}</div>
   <div id="sc-fin">${P.fin||''}</div></div>`;
  const all=P.el.querySelector('[data-f="todas"]');if(all){const ok=P.rows.filter(x=>x.info&&x.info.ok);all.checked=ok.length&&ok.every(x=>x.sel)}
  P.el.onchange=ev=>{if(!ev.target.matches('input[type=text],input:not([type]),textarea'))cambio(P,ev)};P.el.oninput=ev=>{if(ev.target.matches('input[type=text],input:not([type]),textarea'))cambio(P,ev,true)};
  P.el.onclick=ev=>{const b=ev.target.closest('[data-x]');if(!b||P.busy)return;
    if(b.dataset.x==='masterizar'){b.disabled=true;b.textContent='Masterizando… puede tardar unos minutos';
      return GM.mods.masterizado.aplicar(P.g).then(r=>{if(r&&r.ok){GM.ui.toast('Másters guardados: '+r.guardados);if(P.dlg)P.dlg.remove();GM.ui.reload()}else{GM.ui.toast('No se pudo masterizar'+(r&&r.error?': '+r.error:''));b.disabled=false;b.textContent='Aplicar mi masterizado y guardar los másters'}})}
    if(b.dataset.x==='subir')return confirmar(P,false);
    if(b.dataset.x==='reintentar')return confirmar(P,true);
    if(b.dataset.x==='cerrar'&&P.dlg)P.dlg.remove()}}

function cambio(P,ev,suave){
  const t=ev.target,tr=t.closest('tr[data-i]'),x=tr?P.rows[+tr.dataset.i]:null;
  if(t.dataset.f==='todas'){P.rows.forEach(r=>{if(r.info&&r.info.ok)r.sel=t.checked});return dibujar(P)}
  if(x&&t.dataset.f){const f=t.dataset.f;
    if(f==='sel')x.sel=t.checked;else if(f==='titulo')x.titulo=t.value;else if(f==='sharing')x.sharing=t.value;
    else if(f==='accion')x.accion=t.value;else if(f==='p'){x.p=t.value;return info(P,x)}
    if(!suave)dibujar(P);else upd(P);return}
  if(t.dataset.o){const k=t.dataset.o;P.o[k]=t.type==='checkbox'?t.checked:t.value;
    if(k==='priv')P.rows.forEach(r=>r.sharing=t.value);
    if(!suave)dibujar(P);else upd(P);return}
  if(t.dataset.p==='setAccion'){P.setAccion=t.value;upd(P)}}
function upd(P){const r=P.el.querySelector('#sc-res');if(r)r.innerHTML=resumenHtml(P)}

function plan(P,soloFallidas){
  const inc=P.rows.filter(x=>x.sel&&x.info&&x.info.ok&&(!soloFallidas||x.estado==='error'));
  return {inc,sube:inc.filter(x=>x.accion==='subir'),act:inc.filter(x=>x.accion==='actualizar'&&x.res),salta:inc.filter(x=>x.accion==='saltar')}}
function resumenHtml(P){
  const p=plan(P),bytes=p.sube.reduce((a,x)=>a+(x.info.bytes||0),0),pub=p.sube.filter(x=>x.sharing==='public').length;
  const L=[];
  if(p.sube.length)L.push(`<span>${E(`Se subirán ${p.sube.length} canciones (${fmt(bytes)})`)}</span>`);
  if(pub)L.push(`<span class="b warn">${E(`${pub} públicas`)}</span>`);
  if(p.act.length)L.push(`<span>${E(`Se actualizarán los datos de ${p.act.length} ya subidas`)}</span>`);
  if(p.salta.length)L.push(`<span class="meta">${E(`${p.salta.length} ya subidas no se repiten`)}</span>`);
  if(P.o.set&&P.g.songs.length>1)L.push(`<span>${E(P.setPrev&&P.setAccion==='actualizar'?'Se actualizará el álbum en SoundCloud':'Se creará el álbum en SoundCloud')}</span>`);
  return L.join(' · ')||'<span class="meta">No hay nada seleccionado.</span>'}

function guardarPrefs(P){const o=P.o;S().alb[P.g.key]={priv:o.priv,genre:o.genre,tags:o.tags,desc:o.desc,letra:o.letra,caratula:o.caratula,fecha:o.fecha,sello:o.sello,lic:o.lic,set:o.set,setTit:o.setTit,setTipo:o.setTipo,setPriv:o.setPriv};GM.save()}
function datos(P,x){
  const o=P.o,tags=String(o.tags||'').split(',').map(t=>t.trim()).filter(Boolean);
  let desc=String(o.desc||'').trim();
  if(o.letra&&!GM.isDraft(x.s)){const l=String(GM.lyrics(x.s.id)||'').trim();if(l)desc=(desc?desc+'\n\n':'')+l}
  return {id:x.s.id,p:x.p,titulo:x.titulo.trim()||GM.title(x.s),sharing:x.sharing,genre:o.genre,tags,description:desc,label_name:o.sello,
    release_date:o.fecha,license:o.lic,isrc:x.isrc,portada:o.caratula&&P.portada&&P.portada.ok&&P.g.cover?P.g.cover.p:''}}

async function confirmar(P,soloFallidas){
  const p=plan(P,soloFallidas),quiereSet=P.o.set&&P.g.songs.length>1;
  if(!p.inc.length)return GM.ui.toast('No hay ninguna canción seleccionada');
  if(p.inc.some(x=>!x.titulo.trim()))return GM.ui.toast('Hay una canción sin título');
  const bytes=p.sube.reduce((a,x)=>a+(x.info.bytes||0),0),pub=p.sube.filter(x=>x.sharing==='public').length;
  const L=[`<div><b>${E(`Cuenta: ${(EST.usuario||{}).username||''}`)}</b></div>`];
  if(p.sube.length)L.push(`<div>${E(`Se subirán ${p.sube.length} canciones (${fmt(bytes)}), una detrás de otra.`)}</div>`);
  L.push(`<div>${E(`${p.sube.length-pub} privadas · ${pub} públicas`)}</div>`);
  if(p.act.length)L.push(`<div>${E(`Se actualizarán los datos de ${p.act.length} canciones ya subidas (el audio no cambia).`)}</div>`);
  if(quiereSet)L.push(`<div>${E(P.setPrev&&P.setAccion==='actualizar'?`Se actualizará el álbum «${P.o.setTit}» con sus pistas en este orden.`:`Se creará el álbum «${P.o.setTit}» (${P.o.setPriv==='public'?'público':'privado'}) en este orden.`)}</div>`);
  if(P.o.letra)L.push('<div>La letra irá en la descripción de cada canción (nunca la de los bocetos).</div>');
  L.push('<div class="meta">Todavía no se ha subido nada.</div>');
  if(!await GM.ui.ask('¿Subir a SoundCloud?',L.join(''),'Subir ahora'))return;
  guardarPrefs(P);subirTodo(P,p,quiereSet)}

async function subirTodo(P,p,quiereSet){
  P.busy=true;P.fin='';
  if(P.dlg)P.dlg.onclick=()=>{};   // do not close the dialog by clicking outside while uploading
  const cola=[...p.sube,...p.act];cola.forEach(x=>{x.estado='espera';x.err=null;x.pct=0});dibujar(P);
  for(const x of p.salta)if(x.estado!=='ok')x.estado='saltada';
  for(const x of cola){
    x.estado='subiendo';x.pct=0;dibujar(P);
    if(x.accion==='actualizar'){
      const r=await GM.api(ID,'actualizar',{...datos(P,x),urn:x.res.urn}).catch(e=>({ok:false,error:String(e)}));
      if(r&&r.ok){x.estado='act';x.res=r.resultado;apuntar(x.s.id,r.resultado)}else{x.estado='error';x.err=r}
      dibujar(P);continue}
    const r=await GM.api(ID,'subir',datos(P,x)).catch(e=>({ok:false,error:String(e)}));
    if(!r||!r.ok){x.estado='error';x.err=r;dibujar(P);continue}
    for(;;){await sleep(700);
      const q=await GM.api(ID,'progreso?job='+encodeURIComponent(r.job)).catch(()=>null);
      if(!q){continue}
      if(!q.ok){x.estado='error';x.err=q;break}
      if(q.total)x.pct=Math.min(100,Math.round(q.enviados*100/q.total));
      if(q.estado==='hecho'){x.estado='ok';x.res=q.resultado;x.info.subida=q.resultado;x.sinCaratula=!!q.sin_caratula;x.accion='saltar';apuntar(x.s.id,q.resultado);break}
      if(q.estado==='error'){x.estado='error';x.err=q;break}
      const c=P.el.querySelector(`tr[data-i="${P.rows.indexOf(x)}"] .sc-st`);
      if(c)c.innerHTML=`<div class="sc-bar"><i style="width:${x.pct}%"></i></div><span class="meta">${E(`Subiendo… ${x.pct} %`)}</span>`}
    dibujar(P)}
  await cargarSubidas();
  const fallos=P.rows.filter(x=>x.sel&&x.estado==='error');
  let setTxt='';
  if(quiereSet){
    if(fallos.length)setTxt='<div class="callout">El álbum se creará cuando todas las canciones estén subidas: reintenta las que fallaron.</div>';
    else{
      const urns=P.rows.filter(x=>x.sel&&x.res&&x.res.urn).map(x=>x.res.urn);
      const o=P.o,tags=String(o.tags||'').split(',').map(t=>t.trim()).filter(Boolean);
      const r=await GM.api(ID,'crear_set',{key:P.g.key,titulo:o.setTit||P.g.title,set_type:o.setTipo,sharing:o.setPriv,description:o.desc,genre:o.genre,tags,
        release_date:o.fecha,label_name:o.sello,license:o.lic,urns,portada:o.caratula&&P.portada&&P.portada.ok&&P.g.cover?P.g.cover.p:'',
        actualizar:P.setPrev&&P.setAccion==='actualizar'?P.setPrev.urn:''}).catch(e=>({ok:false,error:String(e)}));
      if(r&&r.ok){P.setPrev=r.resultado;P.setAccion='actualizar';
        if(GM.pub)GM.pub.albumUpsert(P.g.key,{plat:'SoundCloud',tipo:'pre',fecha:fechaDe(r.resultado.t),url:r.resultado.url||'',urn:r.resultado.urn||'',
          priv:r.resultado.sharing==='public'?'public':'private',auto:'sc-set',songs:P.rows.filter(x=>x.sel&&x.res&&x.res.urn).map(x=>x.s.id)});
        setTxt=`<div class="sc-hrow"><span class="sc-ic">💿</span><b class="sc-grow notr">${E(r.resultado.titulo)}</b><a class="chip pri" href="${E(r.resultado.url)}" target="_blank" rel="noopener">Abrir el álbum en SoundCloud ↗</a></div>`
          +(r.orden==='corregido'?'<div class="meta">SoundCloud había cambiado el orden: ya está corregido.</div>':r.orden==='distinto'?'<div class="callout">SoundCloud muestra las pistas en otro orden. Revísalo en SoundCloud (puede tardar mientras procesa el audio).</div>':r.orden==='no_verificado'?'<div class="meta">No se pudo comprobar el orden del álbum.</div>':'')
          +(r.sin_caratula?'<div class="meta">El álbum se creó sin carátula: SoundCloud no la aceptó.</div>':'')}
      else setTxt=`<div class="callout"><b>No se pudo crear el álbum.</b> ${errHtml(r)}</div>`}}
  const ok=P.rows.filter(x=>x.estado==='ok'||x.estado==='act');
  P.fin=`<h3>Resultado</h3>${fallos.length?`<div class="callout sc-warn">${E(`${ok.length} bien · ${fallos.length} fallaron`)}: <span class="notr">${fallos.map(x=>E(x.titulo)).join(', ')}</span></div>`:ok.length?`<div class="meta">${E(`${ok.length} canciones listas en SoundCloud.`)}</div>`:''}
    ${setTxt}<div class="sc-hist">${P.rows.filter(x=>x.res&&x.res.url&&x.sel).map(x=>`<div class="sc-hrow"><span class="sc-grow notr">${E(x.titulo)}</span><a href="${E(x.res.url)}" target="_blank" rel="noopener">${E(x.res.url)}</a></div>`).join('')}</div>
    <div class="meta">SoundCloud tarda un poco en procesar el audio: al principio la pista puede aparecer «en proceso».</div>`;
  P.busy=false;
  if(P.dlg)P.dlg.onclick=e=>{if(e.target===P.dlg)P.dlg.remove()};
  dibujar(P);GM.ui.toast(fallos.length?`${fallos.length} canciones fallaron`:'Subida terminada ✓');
  // a PUBLIC upload of a song that was still unreleased: offer to set its phase to «Adelanto» (private uploads change nothing)
  const pub=P.rows.filter(x=>(x.estado==='ok'||x.estado==='act')&&x.res&&x.res.sharing==='public'&&GM.song(x.s.id)&&!GM.isPub(GM.song(x.s.id))&&!GM.isPre(GM.song(x.s.id)));
  if(GM.pub&&pub.length)await GM.pub.fase(pub.map(x=>x.s.id),'pre',{preguntar:true,quieto:true,
    titulo:pub.length>1?'Las subiste públicas: ¿pasarlas a «Adelanto»?':'La subiste pública: ¿pasarla a «Adelanto»?'})}

function abrirCancion(s){
  const o=GM.ui.modal('<div id="sc-modal"></div>');o.querySelector('.dlg').classList.add('sc-dlg');
  panel(o.querySelector('#sc-modal'),grupoDe(s),o)}

GM.register({
  id:ID,
  nav:{label:'SoundCloud',icon:'☁'},
  render(el){render(el)},
  albumTab:{id:'sc',label:'☁ SoundCloud',render(el,g){panel(el,g,null)}},
  songAction:{label:'Subir a SoundCloud',icon:'☁',run(s){abrirCancion(s)}},
  badges(s){const x=!GM.pub&&SUB.songs&&SUB.songs[s.id];return x?`<span class="b" title="${E(T('Subida a SoundCloud'))}">☁ SoundCloud</span>`:''},
  init(){cargarSubidas()},
});
})();
