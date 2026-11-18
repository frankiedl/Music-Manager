/* «publicaciones» module: the PHASE of each song and WHERE it is published.
   - Phase bar at the very top of every song page (GM songTop): Sin publicar · Adelanto (pre-release) · Publicada · ↺ Según la carpeta.
     Stored in the core state ST.release[id] via GM.setRelease, only when it differs from the folder (GM.isPub/isPre keep working).
     Choosing a phase that differs from the folder offers to move the song folder there (GM.moverCanciones: journaled, undoable,
     the song keeps its id) or to change only the state.
   - «Publicado en» section on every song page + album tab «Publicación» («Marcar este álbum como publicado…»: one form for all
     its songs, then the phase, with one confirmation and one journal batch for the folders).
   Storage: GM.state('publicaciones') (= ST.mod.publicaciones in estado.json)
     pubs:  {songId: [entry]}      entry = {id, plat, tipo:'pre'|'lan', fecha, url, upc, isrc, cod, notas, priv?, urn?, auto?, alb?,
                                            num:[{f:'YYYY-MM-DD', plays, likes, comments, reposts}]}   (numbers: one row per day)
     albs:  {groupKey: [entry + songs:[ids]]}   plats: [names] (only once the user edits the preset list)
   Other modules use GM.pub (null when this module is absent): upsert, albumUpsert, numeros, list, fase (o.quieto: no redraw).
   Other files may add read-only entries: PUB.ext.push(song => [{plat, tipo, fecha, url, upc, isrc, notas}]). */
(function(){
const ID='publicaciones';
const E=s=>GM.ui.esc(s==null?'':String(s));
const T=s=>(window.T||(x=>x))(s);
const nrm=s=>String(s==null?'':s).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const S=()=>{const st=GM.state(ID);if(!st.pubs)st.pubs={};if(!st.albs)st.albs={};return st};
const PRESETS=['SoundCloud','Spotify','Apple Music','YouTube Music','Bandcamp','DistroKid','Ditto','TuneCore','CD Baby','Amuse','Otra'];
const FASES=[['un','Sin publicar','○','Solo la tienes tú','Todavía no ha salido: solo la tienes tú.'],
  ['pre','Adelanto','◐','Pre-release','La has compartido antes del lanzamiento (por ejemplo en SoundCloud), sin lanzamiento oficial.'],
  ['pub','Publicada','●','Lanzamiento oficial','Lanzada oficialmente en las tiendas y plataformas (Spotify, Apple Music…).']];
const TIPOS=[['pre','Adelanto'],['lan','Lanzamiento']];
const NUMS=[['plays','Reproducciones','▶'],['likes','Me gusta','♥'],['comments','Comentarios','💬'],['reposts','Reposts','↻']];
const TOP={un:'unreleased/',pre:'prereleased/',pub:'published/'};
const PUB=window.PUB=window.PUB||{ext:[]};
const uid=()=>Date.now().toString(36)+Math.random().toString(36).slice(2,7);
const hoy=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')};
const fN=k=>(FASES.find(x=>x[0]===k)||FASES[0])[1];
const tN=k=>(TIPOS.find(x=>x[0]===k)||TIPOS[0])[1];
const pn=x=>x==='Otra'?T('Otra'):x;   // the preset «Otra» is shown in the UI language (names are data, not translated)
const fmtN=n=>Number(n).toLocaleString(GM.idioma||'es');
let VIVO=null;   // the «Publicado en» section on screen {el, s}

/* ---------- model ---------- */
const faseDe=s=>GM.isPub(s)?'pub':GM.isPre(s)?'pre':'un';
const carpeta=s=>GM.faseCarpeta(s);
const plats=()=>S().plats||PRESETS.slice();
const platsMine=()=>{const st=S();if(!st.plats)st.plats=plats();return st.plats};
const own=s=>S().pubs[s.id]||[];
function entradas(s){
  const o=own(s),ext=PUB.ext.flatMap(f=>{try{return f(s)||[]}catch(e){return []}})
    .filter(e=>!o.some(x=>nrm(x.plat)===nrm(e.plat)&&((e.url&&x.url===e.url)||(e.upc&&x.upc===e.upc))))
    .map((e,i)=>({id:'ext'+i,num:[],...e,ro:true}));
  return [...o,...ext]}
const ultimo=e=>(e.num||[]).slice().sort((a,b)=>String(a.f).localeCompare(String(b.f))).pop();
const incompleta=s=>!GM.isDraft(s)&&own(s).some(e=>!e.fecha||!e.url);
function fijar(L,f){L.forEach(s=>{const x=GM.song(s.id)||s;GM.setRelease(x.id,f===carpeta(x)?'':f)})}
function addPlat(n){if(n&&!plats().some(x=>nrm(x)===nrm(n)))platsMine().push(n)}
function upsert(id,e,match){
  const st=S(),L=st.pubs[id]=st.pubs[id]||[];
  const x=L.find(match||(z=>(e.urn&&z.urn===e.urn)||(e.auto&&z.auto===e.auto&&nrm(z.plat)===nrm(e.plat))));
  if(x){const num=x.num;Object.assign(x,e);x.num=num||[]}else L.push({id:uid(),num:[],...e});
  addPlat(e.plat);GM.save();repintar();return x||L[L.length-1]}
function addNum(e,n){
  e.num=(e.num||[]).filter(r=>r.f!==n.f);
  const r={f:n.f||hoy()};NUMS.forEach(([k])=>{if(n[k]!=null&&n[k]!==''&&isFinite(+n[k]))r[k]=+n[k]});
  if(Object.keys(r).length>1)e.num.push(r);e.num.sort((a,b)=>String(a.f).localeCompare(String(b.f)))}
function albsDe(s){
  const st=S();return Object.entries(st.albs).filter(([k,L])=>L.some(e=>(e.songs||[]).includes(s.id))).map(([k,L])=>({k,L:L.filter(e=>(e.songs||[]).includes(s.id))}))}

/* ---------- dialogs ---------- */
function dialogo(titulo,cuerpo,botones){return new Promise(res=>{
  const o=GM.ui.modal(`<h3>${E(titulo)}</h3>${cuerpo}<div class="acts">${botones.map(([k,t,pri])=>`<button class="chip${pri?' pri':''}" data-k="${k}">${E(t)}</button>`).join('')}</div>`);
  o.querySelector('.dlg').classList.add('wide');
  o.onclick=ev=>{if(ev.target===o){o.remove();return res(null)}const b=ev.target.closest('[data-k]');if(!b)return;o.remove();res(b.dataset.k||null)}})}

/* Changes the phase of one or more songs. If a folder does not match the new phase it offers to move it (from → to shown
   first, one confirmation, one journal batch). o: {preguntar:true (always ask), titulo, album:{nombre, orden:{id:n}, grupo}} */
async function cambiarFase(L,f,o={}){
  L=L.filter(Boolean);if(!L.length)return null;
  const alb=o.album&&f==='pub'?o.album:null;
  const items=L.filter(s=>GM.dir(s)&&carpeta(s)!==f).map(s=>({id:s.id,fase:f,...(alb?{album:alb.nombre,pista:(alb.orden||{})[s.id]||0}:{})}));
  let plan=[];
  if(items.length){const r=await GM.moverCanciones(items,{simular:true});
    plan=r&&r.ok?(r.plan||[]).filter(p=>!p.igual):items.map(i=>({id:i.id,titulo:GM.title(GM.song(i.id)),error:(r&&r.error)||'Error'}))}
  const ok=plan.filter(p=>p.a&&!p.error);
  if(!plan.length&&!o.preguntar){fijar(L,f);GM.ui.refresh();GM.ui.toast(`${T('Fase')}: ${T(fN(f))}`);return 'estado'}
  const titulo=o.titulo||(plan.length>1?`¿Mover también las carpetas a ${TOP[f]}?`:plan.length?`¿Mover también la carpeta a ${TOP[f]}?`:`¿Pasar a «${fN(f)}»?`);
  const cuerpo=`<p class="meta" style="font-size:14px"><span>${E(L.length>1?`La fase de ${L.length} canciones pasa a «${T(fN(f))}».`:`La fase pasa a «${T(fN(f))}».`)}</span>${plan.length?' <span>Además puedo mover la carpeta a la de esa fase:</span>':''}</p>
   ${plan.length?`<div class="pub-mv">${plan.map(p=>`<div><b class="notr">${E(p.titulo)}</b><br>${p.error?`<span class="pub-err">${E(T(p.error))}</span>${p.a?` <code class="notr">${E(p.a)}</code>`:''}`:`<code class="notr">${E(p.de)}</code> → <code class="notr">${E(p.a)}</code>`}</div>`).join('')}</div>`:''}
   ${ok.length?'<div class="meta">Se apunta en el diario de movimientos: se puede deshacer. Las estrellas, notas, registros y subidas de la canción se conservan.</div>':''}`;
  const B=[['','Cancelar']];
  if(plan.length){B.push(['estado','Solo cambiar el estado']);if(ok.length)B.push(['mover',ok.length>1?'Sí, mover las carpetas':'Sí, mover la carpeta',1])}
  else B.push(['estado','Sí, cambiar la fase',1]);
  const k=await dialogo(titulo,cuerpo,B);if(!k)return null;
  if(k==='mover'){
    GM.ui.toast('Moviendo…');
    const r=await GM.moverCanciones(items.filter(i=>ok.some(p=>p.id===i.id)),alb&&alb.grupo?{grupo:{de:alb.grupo,album:alb.nombre}}:{});
    if(!r||!r.ok)GM.ui.toast(T('No se pudo mover')+(r&&r.error?': '+T(r.error):''));
    else{const mal=(r.plan||[]).filter(p=>p.error),n=(r.plan||[]).filter(p=>p.movida).length;
      if(mal.length)await dialogo('Algunas carpetas no se movieron',`<div class="pub-mv">${mal.map(p=>`<div><b class="notr">${E(p.titulo)}</b><br><span class="pub-err">${E(T(p.error))}</span></div>`).join('')}</div>`,[['','Entendido',1]]);
      else GM.ui.toast(n===1?'Carpeta movida ✓':`${n} carpetas movidas ✓`)}}
  fijar(L,f);if(!o.quieto)GM.ui.refresh();
  if(k!=='mover')GM.ui.toast(`${T('Fase')}: ${T(fN(f))}`);
  return k}

/* ---------- phase bar (top of the song page) ---------- */
function barra(el,s){
  const f=faseDe(s),c=carpeta(s),r=GM.release(s.id),d=GM.dir(s);
  el.innerHTML=`<div class="pub-fase"><div class="pub-fhead"><span class="pub-flbl">Fase</span><span class="meta">Dónde está la canción en su vida.</span>${GM.mods.derechos?'<span class="meta">Los registros de derechos van aparte, en la sección Derechos.</span>':''}</div>
   <div class="pub-seg">${FASES.map(([k,n,ic,sub])=>`<button class="pub-fb${f===k?' on':''}" data-f="${k}"><span class="pub-ic">${ic}</span><span><b>${n}</b><small>${sub}</small></span></button>`).join('')}</div>
   <div class="pub-finfo"><span>${FASES.find(x=>x[0]===f)[4]}</span></div>
   <div class="pub-finfo meta">${d?(r?`<span>${E(`Elegida por ti · la carpeta está en ${TOP[c]}`)}</span>`:`<span>${E(`Según su carpeta (${TOP[c]})`)}</span>`):'<span>Esta canción no tiene carpeta.</span>'}
    ${r&&d&&c!==f?`<button class="chip" data-x="mover">${E(`Mover la carpeta a ${TOP[f]}`)}</button>`:''}${r?'<button class="chip" data-x="carpeta" title="Volver a decidirlo por la carpeta">↺ Según la carpeta</button>':''}</div></div>`;
  el.onclick=async ev=>{
    const b=ev.target.closest('[data-f],[data-x]');if(!b)return;
    if(b.dataset.f){if(b.dataset.f!==f)await cambiarFase([s],b.dataset.f);return}
    if(b.dataset.x==='carpeta'){GM.setRelease(s.id,'');GM.ui.refresh();GM.ui.toast(`${T('Fase')}: ${T(fN(c))}`);return}
    if(b.dataset.x==='mover')await cambiarFase([s],f)}}

/* ---------- «Publicado en» (song page) ---------- */
function codigos(e){return [e.upc?`<span>UPC</span> <span class="pub-cod notr">${E(e.upc)}</span>`:'',e.isrc?`<span>ISRC</span> <span class="pub-cod notr">${E(e.isrc)}</span>`:'',
  e.cod?`<span>ID</span> <span class="pub-cod notr">${E(e.cod)}</span>`:'',e.urn?`<span class="pub-cod notr">${E(e.urn)}</span>`:''].filter(Boolean).join(' · ')}
function numsHtml(e){
  const n=ultimo(e);if(!n)return '';
  const H=(e.num||[]).slice().reverse();
  return `<div class="pub-nums">${NUMS.filter(([k])=>n[k]!=null).map(([k,l,ic])=>`<span title="${l}">${ic} ${fmtN(n[k])}</span>`).join('')}<span class="meta">${E(n.f)}</span>
    ${H.length>1?`<details><summary>${E(`Historial (${H.length})`)}</summary><div class="pub-hist"><b>Fecha</b>${NUMS.map(([k,l,ic])=>`<b title="${l}">${ic}</b>`).join('')}
      ${H.map(r=>`<span>${E(r.f)}</span>${NUMS.map(([k])=>`<span>${r[k]!=null?fmtN(r[k]):'·'}</span>`).join('')}`).join('')}</div></details>`:''}</div>`}
function fila(e,extra,soloVer){
  const c=codigos(e);if(soloVer)e={...e,ro:false};
  return `<div class="pub-row"><div class="pub-main"><div class="pub-line"><span class="pub-chip notr">${E(pn(e.plat))}</span><span class="b ${e.tipo==='lan'?'ok':'warn'}">${tN(e.tipo)}</span>${e.priv==='private'?'<span class="b">Privada</span>':''}${e.fecha?`<span class="meta">${E(e.fecha)}</span>`:''}${e.url?`<a href="${E(e.url)}" target="_blank" rel="noopener">Abrir ↗</a>`:''}${extra||''}</div>
    ${c?`<div class="meta">${c}</div>`:''}${numsHtml(e)}
    ${e.notas?`<div class="meta notr">${E(e.notas)}</div>`:''}${e.ro?'<div class="meta">Importado de tus datos · solo lectura</div>':''}</div>
    ${e.ro||soloVer?'':`<div class="pub-acts"><button class="chip" data-x="edit" data-i="${E(e.id)}" title="Editar">✎</button><button class="chip" data-x="del" data-i="${E(e.id)}" title="Borrar">✕</button></div>`}</div>`}
function seccion(el,s){
  VIVO={el,s};
  const L=entradas(s),A=albsDe(s),G=A.length?GM.groups():[];
  el.innerHTML=`<div class="pub-help">Dónde la has publicado: plataforma, fecha, enlace, códigos y números. Lo apuntas tú; al subirla a SoundCloud desde el gestor se apunta sola.</div>
   <div class="pub-list">${L.length?L.map(e=>fila(e)).join(''):'<div class="meta">Todavía no hay ninguna publicación apuntada.</div>'}</div>
   ${A.map(({k,L})=>{const g=G.find(x=>x.key===k);return `<div class="pub-help" style="margin-top:10px">${E(`Del álbum «${g?g.title:k.split('/').pop()}»`)}</div><div class="pub-list">${L.map(e=>fila(e,'',true)).join('')}</div>`}).join('')}
   <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap"><button class="chip pri" data-x="add">＋ Añadir publicación</button><button class="chip" data-x="limpio" title="Hace una copia del audio sin ninguna etiqueta (título, artista, comentarios, datos de Suno…) en la carpeta _para_subir">🧼 Copia sin etiquetas para distribuidora</button></div>`;
  el.onclick=async ev=>{
    const b=ev.target.closest('button[data-x]');if(!b)return;const k=b.dataset.x;
    if(k==='add')return form(s,null);
    if(k==='limpio'){const v=GM.bestVersion(s);if(!v)return GM.ui.toast('Esta canción no tiene archivos de audio');
      const r=await GM.api(ID,'limpio',{p:v,nombre:GM.title(s)}).catch(()=>({ok:false}));
      if(!r.ok)return GM.ui.toast(r.error||'No se pudo hacer la copia');
      GM.ui.toast('Copia sin etiquetas creada: _para_subir/'+r.nombre);
      fetch('/api/abrir',{method:'POST',body:JSON.stringify({p:r.p})}).catch(()=>{});return}
    const e=own(s).find(x=>x.id===b.dataset.i);if(!e)return;
    if(k==='edit')return form(s,e);
    if(k==='del'&&await GM.ui.ask('¿Borrar esta publicación?','Solo se borra tu anotación en el gestor; no cambia nada en la plataforma.','Borrar')){
      S().pubs[s.id]=own(s).filter(x=>x!==e);if(!S().pubs[s.id].length)delete S().pubs[s.id];GM.save();GM.ui.refresh();GM.ui.toast('Publicación borrada')}}}
function repintar(){if(VIVO&&VIVO.el.isConnected){const s=GM.song(VIVO.s.id);if(s)seccion(VIVO.el,s)}}

function campos(e,titulo,sub){
  const L=plats(),known=!e.plat||L.some(x=>x===e.plat),n=ultimo(e)||{};
  return `<h3>${titulo}</h3>${sub?`<div class="meta notr">${E(sub)}</div>`:''}<div class="pub-form">
    <div class="pub-g2"><label><span>Plataforma</span><select id="pub-plat">${L.map(x=>`<option value="${E(x)}"${x===e.plat?' selected':''}>${E(x)}</option>`).join('')}<option value="__otra"${known?'':' selected'}>Otra…</option></select></label>
    <label><span>Tipo</span><select id="pub-tipo">${TIPOS.map(([k,n])=>`<option value="${k}"${k===e.tipo?' selected':''}>${n}</option>`).join('')}</select></label></div>
    <label id="pub-otraL"${known?' hidden':''}><span>Nombre de la plataforma</span><input id="pub-otra" value="${known?'':E(e.plat)}"></label>
    <div class="pub-g2"><label><span>Fecha</span><input id="pub-fecha" type="date" value="${E(e.fecha)}"></label><label><span>Enlace (URL)</span><input id="pub-url" type="url" class="notr" value="${E(e.url)}" placeholder="https://"></label></div>
    <div class="pub-g2"><label><span>UPC</span><input id="pub-upc" class="notr" value="${E(e.upc)}"></label><label><span>ISRC</span><input id="pub-isrc" class="notr" value="${E(e.isrc)}"></label></div>
    <label><span>ID en la tienda o la distribuidora</span><input id="pub-cod" class="notr" value="${E(e.cod)}"></label>
    <label><span>Notas</span><textarea id="pub-notas" rows="2">${E(e.notas)}</textarea></label>
    <details${n.f?' open':''}><summary>Números (reproducciones, me gusta…)</summary><div class="pub-form" style="margin-top:6px"><label><span>Fecha de los números</span><input id="pub-nf" type="date" value="${E(n.f||hoy())}"></label>
     <div class="pub-g4">${NUMS.map(([k,l,ic])=>`<label><span>${ic} ${l}</span><input id="pub-n-${k}" type="number" min="0" step="1" value="${n[k]!=null?E(n[k]):''}"></label>`).join('')}</div>
     <div class="meta">Se guarda un apunte por día: así ves cómo crecen.</div></div></details></div>
    <div class="acts"><button class="chip" data-x="0">Cancelar</button><button class="chip pri" data-x="1">Guardar</button></div>`}
function leer(o){
  const q=id=>o.querySelector('#'+id);
  let plat=q('pub-plat').value;if(plat==='__otra')plat=q('pub-otra').value.trim();
  const v={plat,tipo:q('pub-tipo').value,fecha:q('pub-fecha').value,url:q('pub-url').value.trim(),upc:q('pub-upc').value.trim(),isrc:q('pub-isrc').value.trim(),
    cod:q('pub-cod').value.trim(),notas:q('pub-notas').value.trim()};
  const n={f:q('pub-nf').value||hoy()};NUMS.forEach(([k])=>{const x=q('pub-n-'+k).value.trim();if(x!=='')n[k]=x});
  return {v,n}}
function enlazar(o){const q=id=>o.querySelector('#'+id);q('pub-plat').onchange=()=>{q('pub-otraL').hidden=q('pub-plat').value!=='__otra'}}
function form(s,e){
  const nuevo=!e;e=e||{plat:plats()[0]||'',tipo:'lan',fecha:hoy(),url:'',upc:'',isrc:'',cod:'',notas:'',num:[]};
  const o=GM.ui.modal(campos(e,nuevo?'Añadir publicación':'Editar publicación',GM.title(s)));enlazar(o);
  o.onclick=async ev=>{
    if(ev.target===o)return o.remove();
    const x=ev.target.dataset.x;if(x===undefined)return;
    if(x==='0')return o.remove();
    const {v,n}=leer(o);
    if(!v.plat)return GM.ui.toast('Escribe el nombre de la plataforma');
    if(v.url&&!/^https?:\/\//i.test(v.url))return GM.ui.toast('El enlace tiene que empezar por http:// o https://');
    addPlat(v.plat);
    const st=S();st.pubs[s.id]=st.pubs[s.id]||[];
    let ent=e;if(nuevo){ent={id:uid(),num:[],...v};st.pubs[s.id].push(ent)}else Object.assign(e,v);
    if(Object.keys(n).length>1)addNum(ent,n);
    o.remove();GM.save();GM.ui.refresh();GM.ui.toast(nuevo?'Publicación añadida':'Publicación guardada');
    if(nuevo){const f=faseDe(s);
      if(v.tipo==='lan'&&f!=='pub')await cambiarFase([s],'pub',{preguntar:true,titulo:'¿Pasar la canción a «Publicada»?'});
      else if(v.tipo==='pre'&&f==='un')await cambiarFase([s],'pre',{preguntar:true,titulo:'¿Pasar la canción a «Adelanto»?'})}}}

/* ---------- album tab: «Marcar este álbum como publicado» ---------- */
function albumTab(el,g){
  const st=S(),L=st.albs[g.key]||[],songs=(GM.order&&g.songs.length>1?GM.order(g):g.songs.slice()).filter(Boolean);
  el.innerHTML=`<div class="pub-help">La publicación de todo el álbum: lo que apuntes aquí se copia a cada canción (luego puedes cambiar cada una en su página).</div>
   <div class="pub-list">${L.length?L.map(e=>fila(e)).join(''):'<div class="meta">Este álbum todavía no tiene ninguna publicación apuntada.</div>'}</div>
   <div style="margin:10px 0;display:flex;gap:6px;flex-wrap:wrap"><button class="chip pri" data-x="marcar">🚀 Marcar este álbum como publicado…</button></div>
   <div class="pub-flbl" style="margin:12px 0 6px">Canciones</div>
   <div class="pub-list">${songs.map(s=>{const f=faseDe(s),P=[...new Set(entradas(s).map(e=>e.plat))];
     return `<div class="pub-row" data-song="${E(s.id)}" style="cursor:pointer"><div class="pub-main"><div class="pub-line"><b class="notr">${E(GM.title(s))}</b><span class="b ${f==='pub'?'ok':f==='pre'?'warn':''}">${fN(f)}</span>${P.map(p=>`<span class="b pub-b notr">${E(pn(p))}</span>`).join('')}</div></div></div>`}).join('')||'<div class="meta">No hay canciones.</div>'}</div>`;
  el.onclick=async ev=>{
    const r=ev.target.closest('[data-song]');if(r&&!ev.target.closest('button'))return GM.ui.go('song',r.dataset.song);
    const b=ev.target.closest('button[data-x]');if(!b)return;const k=b.dataset.x;
    if(k==='marcar')return marcarAlbum(el,g,songs);
    const e=L.find(x=>x.id===b.dataset.i);if(!e)return;
    if(k==='edit')return editarAlbum(el,g,e);
    if(k==='del'&&await GM.ui.ask('¿Borrar esta publicación?','Se borra la anotación del álbum. Las de cada canción se quedan (bórralas en su página si quieres).','Borrar')){
      st.albs[g.key]=L.filter(x=>x!==e);if(!st.albs[g.key].length)delete st.albs[g.key];GM.save();albumTab(el,g)}}}
function editarAlbum(el,g,e){
  const o=GM.ui.modal(campos(e,'Editar publicación',g.title));enlazar(o);
  o.onclick=ev=>{if(ev.target===o)return o.remove();const x=ev.target.dataset.x;if(x===undefined)return;if(x==='0')return o.remove();
    const {v,n}=leer(o);if(!v.plat)return GM.ui.toast('Escribe el nombre de la plataforma');addPlat(v.plat);
    Object.assign(e,v);if(Object.keys(n).length>1)addNum(e,n);o.remove();GM.save();albumTab(el,g);GM.ui.toast('Publicación guardada')}}
function marcarAlbum(el,g,songs){
  if(!songs.length)return GM.ui.toast('No hay canciones');
  const e={plat:(plats().find(x=>x!=='SoundCloud')||plats()[0]||''),tipo:'lan',fecha:hoy(),url:'',upc:'',isrc:'',cod:'',notas:'',num:[]};
  const o=GM.ui.modal(campos(e,'Marcar este álbum como publicado',`${g.title} · ${songs.length} ${T('canciones')}`).replace('<div class="acts">',
    `<div class="meta" style="margin-top:8px">${E(`Se apunta en las ${songs.length} canciones. Después te pregunto si cambio su fase y muevo sus carpetas.`)}</div><div class="acts">`));
  enlazar(o);o.querySelector('#pub-isrc').closest('label').hidden=true;
  o.onclick=async ev=>{if(ev.target===o)return o.remove();const x=ev.target.dataset.x;if(x===undefined)return;if(x==='0')return o.remove();
    const {v,n}=leer(o);delete v.isrc;
    if(!v.plat)return GM.ui.toast('Escribe el nombre de la plataforma');
    if(v.url&&!/^https?:\/\//i.test(v.url))return GM.ui.toast('El enlace tiene que empezar por http:// o https://');
    o.remove();addPlat(v.plat);
    const st=S(),A=st.albs[g.key]=st.albs[g.key]||[],ent={id:uid(),num:[],...v,songs:songs.map(s=>s.id)};A.push(ent);
    if(Object.keys(n).length>1)addNum(ent,n);
    songs.forEach(s=>upsert(s.id,{...v,alb:g.key},z=>z.alb===g.key&&nrm(z.plat)===nrm(v.plat)&&z.tipo===v.tipo));
    GM.save();GM.ui.toast(`Apuntado en ${songs.length} canciones`);
    const f=v.tipo==='lan'?'pub':'pre';
    const pend=songs.filter(s=>f==='pub'?faseDe(s)!=='pub'||carpeta(s)!=='pub':faseDe(s)==='un');
    const proy=g.kind==='proyecto'&&g.key.split('/').length===2;
    if(pend.length)await cambiarFase(pend,f,{preguntar:true,titulo:f==='pub'?'¿Pasar las canciones del álbum a «Publicada»?':'¿Pasar las canciones del álbum a «Adelanto»?',
      album:proy?{nombre:g.title,orden:Object.fromEntries(songs.map((s,i)=>[s.id,i+1])),grupo:g.key}:null});
    else GM.ui.refresh();
    if(el.isConnected){const ng=GM.groups().find(x=>x.key===g.key)||g;albumTab(el,ng)}}}

/* ---------- own section: summary, all publications, platforms ---------- */
function render(el){
  const SS=GM.songs.filter(s=>!GM.isDraft(s)),cnt={un:0,pre:0,pub:0};SS.forEach(s=>cnt[faseDe(s)]++);
  const rows=SS.flatMap(s=>entradas(s).map(e=>({s,e}))).sort((a,b)=>String(b.e.fecha||'').localeCompare(String(a.e.fecha||''))||GM.title(a.s).localeCompare(GM.title(b.s),'es'));
  const con=SS.filter(s=>entradas(s).length).length;
  el.innerHTML=`<h1>Publicaciones</h1><p class="lead">La fase de cada canción y dónde está publicada. Son tus propias anotaciones (salvo SoundCloud, que se apunta solo al subir desde el gestor).</p>
   <div class="callout"><b>Fase</b> = dónde está la canción en su vida: sin publicar, adelanto (por ejemplo en SoundCloud) o publicada (lanzamiento oficial con una distribuidora). Se elige arriba en la página de cada canción.${GM.mods.derechos?' <b>Registros</b> (sección Derechos) = proteger la obra en una sociedad de autores o en Safe Creative: es otra cosa.':''}</div>
   <div class="tiles"><div class="tile"><div class="n">${cnt.un}</div><div class="l">sin publicar</div></div><div class="tile"><div class="n">${cnt.pre}</div><div class="l">adelantos</div></div><div class="tile"><div class="n">${cnt.pub}</div><div class="l">publicadas</div></div><div class="tile"><div class="n">${con}</div><div class="l">con alguna publicación apuntada</div></div></div>
   <h2>Publicaciones apuntadas <span class="meta">${rows.length}</span></h2>
   ${rows.length?`<div class="panel pub-tab">${rows.slice(0,500).map(({s,e})=>`<div class="pub-trow" data-song="${E(s.id)}"><span class="pub-t notr">${E(GM.title(s))}</span><b class="notr">${E(pn(e.plat))}</b><span class="b ${e.tipo==='lan'?'ok':'warn'}">${tN(e.tipo)}</span><span class="meta">${E(e.fecha||'')}</span></div>`).join('')}</div>`:'<div class="empty">Todavía no hay publicaciones. Apúntalas en la página de cada canción (sección «Publicado en») o en la pestaña «Publicación» de un álbum.</div>'}
   <h2>Plataformas</h2>
   <div class="panel"><div class="meta">La lista que sale al apuntar una publicación.</div>
    <div class="pub-plats">${plats().map(x=>`<div class="pub-plat"><b class="notr">${E(pn(x))}</b><span class="pub-acts"><button class="chip" data-p="ren" data-n="${E(x)}" title="Renombrar">✎</button><button class="chip" data-p="del" data-n="${E(x)}" title="Borrar">✕</button></span></div>`).join('')}</div>
    <div class="der-list" style="display:flex;gap:6px;flex-wrap:wrap"><button class="chip" data-p="add">＋ Añadir plataforma</button><button class="chip" data-p="reset">Restaurar la lista predefinida</button></div></div>`;
  el.onclick=async ev=>{
    const t=ev.target.closest('[data-song],[data-p]');if(!t)return;
    if(t.dataset.song)return GM.ui.go('song',t.dataset.song);
    const k=t.dataset.p,n=t.dataset.n;
    if(k==='add'){const v=(prompt(T('Nombre de la nueva plataforma'))||'').trim();if(!v)return;
      if(plats().some(x=>nrm(x)===nrm(v)))return GM.ui.toast('Esa plataforma ya está en la lista');
      platsMine().push(v);GM.save();render(el)}
    if(k==='ren'){const v=(prompt(T('Nuevo nombre'),n)||'').trim();if(!v||v===n)return;
      const L=platsMine(),i=L.indexOf(n);if(i>=0)L[i]=v;
      const st=S();[...Object.values(st.pubs),...Object.values(st.albs)].forEach(L=>L.forEach(e=>{if(e.plat===n)e.plat=v}));   // entries follow the new name
      GM.save();render(el);GM.ui.toast('Plataforma renombrada')}
    if(k==='del'){const st=S(),used=[...Object.values(st.pubs),...Object.values(st.albs)].some(L=>L.some(e=>e.plat===n));
      if(!await GM.ui.ask('¿Quitar esta plataforma de la lista?',used?'Las publicaciones que ya la usan se conservan con su nombre.':'No la usa ninguna publicación.','Quitar'))return;
      st.plats=platsMine().filter(z=>z!==n);GM.save();render(el)}
    if(k==='reset'&&await GM.ui.ask('¿Restaurar la lista predefinida?','Se recupera la lista inicial de plataformas. Tus publicaciones no cambian.','Restaurar')){delete S().plats;GM.save();render(el)}}}

/* ---------- API for other modules (SoundCloud…) ---------- */
GM.pub={
  list:id=>{const s=GM.song(id);return s?entradas(s):[]},
  /* create or update a song's entry (matched by urn, or by `auto` + platform); returns the entry */
  upsert:(id,e,match)=>upsert(id,e,match),
  /* album/release-level entry (e.g. a SoundCloud set), matched by urn or `auto` */
  albumUpsert(key,e){const st=S(),L=st.albs[key]=st.albs[key]||[];
    const x=L.find(z=>(e.urn&&z.urn===e.urn)||(e.auto&&z.auto===e.auto&&nrm(z.plat)===nrm(e.plat)));
    if(x)Object.assign(x,e,{num:x.num||[]});else L.push({id:uid(),num:[],...e});addPlat(e.plat);GM.save()},
  /* dated numbers for the entry with that urn ({f, plays, likes, comments, reposts}); one row per day */
  numeros(id,urn,n){const e=(S().pubs[id]||[]).find(z=>z.urn===urn);if(!e)return false;addNum(e,n);GM.save();repintar();return true},
  fase:(ids,f,o)=>cambiarFase(ids.map(i=>GM.song(i)),f,o||{}),
  faseDe:s=>faseDe(s),
};
GM.on('movidas',pares=>{   // a project published as an album changes its key: its album entries follow it
  const st=S();pares.forEach(([a,b])=>{if(st.albs[a]){st.albs[b]=[...(st.albs[b]||[]),...st.albs[a]];delete st.albs[a]}
    Object.values(st.pubs).forEach(L=>L.forEach(e=>{if(e.alb===a)e.alb=b}))})});

/* Release date reached → the album and its songs pass to «Publicada» by themselves (only the status: no folder is moved, nothing is deleted).
   The date is the one set in the SoundCloud tab of the album (or, if there is none, the album's planned release date).
   It is applied once per album and date: if you later put a song back to another phase it is not forced again, unless you change the date. */
function autoFecha(){
  try{
    const sc=GM.state('soundcloud')||{},st=S();if(!st.auto)st.auto={};
    const h=hoy(),hechas=[];
    GM.groups().forEach(g=>{
      const f=((sc.alb&&sc.alb[g.key]&&sc.alb[g.key].fecha)||(g.album&&g.album.date)||'').slice(0,10);
      if(!/^\d{4}-\d{2}-\d{2}$/.test(f)||f>h||st.auto[g.key]===f)return;
      const L=g.songs.filter(x=>!GM.isDraft(x)&&!GM.isPub(x));
      st.auto[g.key]=f;if(!L.length)return;
      fijar(L,'pub');hechas.push([g,L.length,f])});
    if(hechas.length){GM.save();GM.ui.refresh();
      hechas.forEach(([g,n,f])=>GM.ui.toast(`«${g.title}»: ${n} ${n===1?'canción pasa':'canciones pasan'} a Publicada (fecha de lanzamiento ${f})`))}
  }catch(e){console.error('publicaciones: fecha de lanzamiento',e)}}

GM.register({
  id:ID,
  init(G){G.mods.publicaciones.autoFecha=autoFecha},
  nav:{label:'Publicaciones',icon:'🚀'},
  render(el){render(el)},
  songTop:{render(el,s){barra(el,s)}},
  songSection:{title:'Publicado en',order:5,render(el,s){seccion(el,s)}},
  albumTab:{id:'pub',label:'🚀 Publicación',render(el,g){albumTab(el,g)}},
  badges(s){const P=[...new Set(entradas(s).map(e=>e.plat))];
    return P.slice(0,3).map(p=>`<span class="b pub-b notr">${E(pn(p))}</span>`).join('')+(P.length>3?`<span class="b">+${P.length-3}</span>`:'')},
  tasks(){return [{k:'pubsindatos',ic:'🔗',n:GM.songs.filter(incompleta).length,t:'publicaciones sin fecha o enlace',d:'Tienen una publicación apuntada a la que le falta la fecha o el enlace. Complétala en la página de la canción, sección «Publicado en».'}]},
  filters:[{k:'pubsindatos',label:'Publicaciones sin fecha o enlace',fn:s=>incompleta(s),pend:true}],
});
})();
