/* «derechos» (Rights) module.
   - Release status per song (Unreleased / Pre-released / Published), stored in the core state (ST.release via GM.setRelease);
     it overrides the folder-based deduction, folders are never moved.
   - Registrations with collecting societies: GM.state('derechos').reg[songId] = [{id,soc,cod,fecha,est,au,ed,notas}]
     (est: 'pend' | 'env' | 'reg'; au/ed = author/publisher %). Only the user's own notes: no connection to any society.
   - Editable society list with per-country presets (state.socs, state.pais).
   - Registration sheet: CSV export (client side) and CSV/.xlsx/.xls import with preview (the server only parses the file).
   Other files may add read-only registrations: DER.ext.push(song => [{soc,cod,est,notas}]). */
(function(){
const E=s=>GM.ui.esc(s==null?'':String(s));
const T=s=>(window.T||(x=>x))(s);
const nrm=s=>String(s==null?'':s).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const S=()=>{const st=GM.state('derechos');if(!st.reg)st.reg={};return st};
const PRESETS=[['SGAE','ES'],['SACEM','FR'],['GEMA','DE'],['ASCAP','US'],['BMI','US'],['SESAC','US'],['PRS','UK'],['SIAE','IT'],['SADAIC','AR'],['SPA','PT']];
const PAISES=[['ES','España'],['FR','Francia'],['DE','Alemania'],['US','Estados Unidos'],['UK','Reino Unido'],['IT','Italia'],['AR','Argentina'],['PT','Portugal']];
const EST=[['pend','Pendiente'],['env','Enviado'],['reg','Registrado']];
const REL=[['un','Sin publicar','Todavía no ha salido: solo la tienes tú.'],
  ['pre','Pre-released','Adelanto: la has compartido (por ejemplo en SoundCloud) pero sin lanzamiento oficial.'],
  ['pub','Publicada','Lanzada oficialmente en las plataformas (Spotify, Apple Music…).']];
const DER=window.DER=window.DER||{ext:[]};

/* ---------- model ---------- */
const socs=()=>S().socs||PRESETS.map(([n,c])=>({n,c}));
const socsMine=()=>{const st=S();if(!st.socs)st.socs=socs();return st.socs};       // materialize the presets before editing
function socsSorted(){const p=S().pais||'';return socs().map((x,i)=>[x,i]).sort((a,b)=>((b[0].c===p&&p)?1:0)-((a[0].c===p&&p)?1:0)||a[1]-b[1]).map(x=>x[0])}
const own=s=>S().reg[s.id]||[];
function regsOf(s){
  const o=own(s),ext=DER.ext.flatMap(f=>{try{return f(s)||[]}catch(e){return []}})
    .filter(e=>!o.some(x=>nrm(x.soc)===nrm(e.soc)&&nrm(x.cod)===nrm(e.cod))).map(e=>({...e,ro:true}));
  return [...o,...ext]}
const folderRel=s=>{const d=GM.dir(s)||'';return d.startsWith('published')?'pub':d.startsWith('prereleased')?'pre':'un'};
const relOf=s=>GM.isPub(s)?'pub':GM.isPre(s)?'pre':'un';
const sinReg=s=>!GM.isDraft(s)&&GM.isPub(s)&&!regsOf(s).length;
const uid=()=>Date.now().toString(36)+Math.random().toString(36).slice(2,7);
const estOf=k=>EST.find(x=>x[0]===k)||EST[0];
const estCls=k=>k==='reg'?'ok':k==='env'?'warn':'no';
function setRel(s,v){GM.setRelease(s.id,v&&v!==folderRel(s)?v:'')}
function changed(){GM.save();GM.ui.refresh()}
const pubSongs=()=>GM.songs.filter(s=>!GM.isDraft(s)&&GM.isPub(s));

/* ---------- song page ---------- */
function regRow(s,e){
  const sp=[e.au!==''&&e.au!=null?`<span>Autor</span> ${E(e.au)}%`:'',e.ed!==''&&e.ed!=null?`<span>Editor</span> ${E(e.ed)}%`:''].filter(Boolean).join(' · ');
  return `<div class="der-row"><div class="der-main"><b>${E(e.soc)}</b> <span class="b ${estCls(e.est)}">${estOf(e.est)[1]}</span>${e.cod?` <span class="der-cod">${E(e.cod)}</span>`:''}${e.fecha?` <span class="meta">${E(e.fecha)}</span>`:''}${sp?` <span class="meta">${sp}</span>`:''}
    ${e.notas?`<div class="meta">${E(e.notas)}</div>`:''}${e.ro?'<div class="meta">Importado de tus datos · solo lectura</div>':''}</div>
    ${e.ro?'':`<div class="der-acts"><button class="chip" data-der="edit" data-i="${E(e.id)}" title="Editar">✎</button><button class="chip" data-der="del" data-i="${E(e.id)}" title="Borrar">✕</button></div>`}</div>`}
function songSec(el,s){
  const r=GM.release(s.id),eff=relOf(s),regs=regsOf(s);
  el.innerHTML=`<div class="der-rel"><div class="der-lbl">Estado de publicación</div>
    <div class="der-seg">${REL.map(([k,n])=>`<button class="chip${eff===k?' on':''}" data-rel="${k}">${n}</button>`).join('')}${r?'<button class="chip" data-rel="" title="Volver a decidirlo por la carpeta">↺ Según la carpeta</button>':''}</div>
    <div class="der-help">${REL.find(x=>x[0]===eff)[2]}</div>
    <div class="meta">${r?'Elegido por ti: la carpeta no se mueve.':'Deducido de la carpeta donde está la canción.'}</div></div>
   <div class="der-lbl">Registros en sociedades de autores</div>
   <div class="der-regs">${regs.length?regs.map(e=>regRow(s,e)).join(''):'<div class="meta">Sin registros todavía.</div>'}</div>
   ${eff==='pub'&&!regs.length?'<div class="callout">Está publicada y no tiene ningún registro: dala de alta en tu sociedad de autores para cobrar derechos.</div>':''}
   <div style="margin-top:10px"><button class="chip pri" data-der="add">＋ Añadir registro</button></div>`;
  el.onclick=async ev=>{
    const b=ev.target.closest('button');if(!b)return;
    if(b.dataset.rel!==undefined){setRel(s,b.dataset.rel);GM.ui.refresh();return}
    const k=b.dataset.der;if(!k)return;
    if(k==='add')return form(s,null);
    const e=own(s).find(x=>x.id===b.dataset.i);if(!e)return;
    if(k==='edit')return form(s,e);
    if(k==='del'&&await GM.ui.ask('¿Borrar este registro?','Solo se borra tu anotación en el gestor; no cambia nada en la sociedad.','Borrar')){
      S().reg[s.id]=own(s).filter(x=>x!==e);if(!S().reg[s.id].length)delete S().reg[s.id];changed();GM.ui.toast('Registro borrado')}}}
function form(s,e){
  const isNew=!e;e=e||{soc:'',cod:'',fecha:'',est:'pend',au:'',ed:'',notas:''};
  const L=socsSorted(),known=!e.soc||L.some(x=>x.n===e.soc);
  const o=GM.ui.modal(`<h3>${isNew?'Añadir registro':'Editar registro'}</h3><div class="meta">${E(GM.title(s))}</div><div class="der-form">
    <label><span>Sociedad</span><select id="der-soc">${L.map(x=>`<option value="${E(x.n)}"${x.n===e.soc?' selected':''}>${E(x.n)}${x.c?' · '+x.c:''}</option>`).join('')}<option value="__otra"${known?'':' selected'}>Otra…</option></select></label>
    <label id="der-otraL"${known?' hidden':''}><span>Nombre de la sociedad</span><input id="der-otra" value="${known?'':E(e.soc)}"></label>
    <label><span>Código o número</span><input id="der-cod" value="${E(e.cod)}"></label>
    <label><span>Fecha</span><input id="der-fecha" type="date" value="${E(e.fecha)}"></label>
    <label><span>Estado del registro</span><select id="der-est">${EST.map(([k,n])=>`<option value="${k}"${k===e.est?' selected':''}>${n}</option>`).join('')}</select></label>
    <div class="der-split"><label><span>% autor</span><input id="der-au" type="number" min="0" max="100" step="any" value="${E(e.au)}"></label><label><span>% editor</span><input id="der-ed" type="number" min="0" max="100" step="any" value="${E(e.ed)}"></label></div>
    <label><span>Notas</span><textarea id="der-notas" rows="2">${E(e.notas)}</textarea></label></div>
    <div class="acts"><button class="chip" data-x="0">Cancelar</button><button class="chip pri" data-x="1">Guardar</button></div>`);
  const q=id=>o.querySelector('#'+id);
  q('der-soc').onchange=()=>{q('der-otraL').hidden=q('der-soc').value!=='__otra'};
  o.onclick=ev=>{
    if(ev.target===o)return o.remove();
    const x=ev.target.dataset.x;if(x===undefined)return;
    if(x==='0')return o.remove();
    let soc=q('der-soc').value;if(soc==='__otra')soc=q('der-otra').value.trim();
    if(!soc)return GM.ui.toast('Escribe el nombre de la sociedad');
    const au=q('der-au').value.trim(),ed=q('der-ed').value.trim();
    if((+au||0)+(+ed||0)>100)return GM.ui.toast('Los porcentajes suman más de 100');
    const v={soc,cod:q('der-cod').value.trim(),fecha:q('der-fecha').value,est:q('der-est').value,au,ed,notas:q('der-notas').value.trim()};
    addSoc(soc);
    const st=S();st.reg[s.id]=st.reg[s.id]||[];
    if(isNew)st.reg[s.id].push({id:uid(),...v});else Object.assign(e,v);
    o.remove();changed();GM.ui.toast(isNew?'Registro añadido':'Registro guardado')}}
function addSoc(n){if(!socs().some(x=>nrm(x.n)===nrm(n)))socsMine().push({n,c:''})}

/* ---------- section of its own: summary, sheet, societies ---------- */
function render(el){
  const P=pubSongs(),miss=P.filter(sinReg),all=GM.songs.filter(s=>!GM.isDraft(s));
  const rows=all.flatMap(s=>regsOf(s).map(e=>({s,e}))).sort((a,b)=>GM.title(a.s).localeCompare(GM.title(b.s),'es'));
  const pais=S().pais||'';
  el.innerHTML=`<h1>Derechos</h1><p class="lead">Aquí llevas el estado de publicación de tus canciones y su registro en las sociedades de autores (SGAE, SACEM, GEMA, ASCAP…). Son tus propias anotaciones: el gestor no se conecta con ninguna sociedad.</p>
   <div class="tiles"><div class="tile"><div class="n">${P.length}</div><div class="l">publicadas</div></div><div class="tile"><div class="n">${P.length-miss.length}</div><div class="l">con algún registro</div></div><div class="tile der-click" data-der="miss"><div class="n">${miss.length}</div><div class="l">publicadas sin registro</div></div><div class="tile"><div class="n">${rows.length}</div><div class="l">registros en total</div></div></div>
   ${miss.length?`<h2>Publicadas sin registro</h2><div class="der-list">${miss.map(s=>`<button class="chip" data-song="${E(s.id)}">${E(GM.title(s))}</button>`).join('')}</div>`:''}
   <h2>Hoja de registro (Excel / CSV)</h2>
   <div class="panel"><p class="meta">Descarga una hoja con todas tus canciones y una columna para cada dato del registro. Rellénala en Excel (o en cualquier hoja de cálculo) y vuelve a importarla: antes de aplicar verás qué se crea y qué se cambia. Al importar nunca se borra nada.</p>
    <div class="der-list"><button class="chip pri" data-der="csv">⬇ Descargar la hoja (CSV)</button><label class="chip">⬆ Importar una hoja (CSV o Excel)<input type="file" id="der-file" accept=".csv,.txt,.xlsx,.xls" hidden></label></div></div>
   <h2>Registros <span class="meta">${rows.length}</span></h2>
   ${rows.length?`<div class="panel der-tab">${rows.map(({s,e})=>`<div class="der-trow" data-song="${E(s.id)}"><span class="der-t">${E(GM.title(s))}</span><b>${E(e.soc)}</b><span class="b ${estCls(e.est)}">${estOf(e.est)[1]}</span><span class="der-cod">${E(e.cod)}</span><span class="meta">${E(e.fecha)}</span></div>`).join('')}</div>`:'<div class="empty">Todavía no hay registros. Ábrelos desde la página de cada canción (sección Derechos) o importa la hoja.</div>'}
   <h2>Sociedades</h2>
   <div class="panel"><label class="der-pais"><span>Tu país</span> <select id="der-pais"><option value="">Todos los países</option>${PAISES.map(([c,n])=>`<option value="${c}"${c===pais?' selected':''}>${n}</option>`).join('')}</select></label>
    <div class="meta">Las sociedades de tu país salen las primeras al añadir un registro.</div>
    <div class="der-socs">${socsSorted().map(x=>`<div class="der-soc"><b>${E(x.n)}</b> <span class="meta">${E(x.c)}</span><span class="der-acts"><button class="chip" data-soc="ren" data-n="${E(x.n)}" title="Renombrar">✎</button><button class="chip" data-soc="del" data-n="${E(x.n)}" title="Borrar">✕</button></span></div>`).join('')}</div>
    <div class="der-list"><button class="chip" data-soc="add">＋ Añadir sociedad</button><button class="chip" data-soc="reset">Restaurar la lista predefinida</button></div></div>`;
  el.querySelector('#der-pais').onchange=ev=>{S().pais=ev.target.value;GM.save();render(el)};
  el.querySelector('#der-file').onchange=ev=>{const f=ev.target.files[0];ev.target.value='';if(f)importar(f,()=>render(el))};
  el.onclick=async ev=>{
    const t=ev.target.closest('[data-der],[data-song],[data-soc]');if(!t)return;
    if(t.dataset.song)return GM.ui.go('song',t.dataset.song);
    if(t.dataset.der==='csv')return exportar();
    if(t.dataset.der==='miss'&&miss.length)return GM.ui.go('song',miss[0].id);
    const k=t.dataset.soc,n=t.dataset.n;
    if(k==='add'){const v=(prompt(T('Nombre de la nueva sociedad'))||'').trim();if(!v)return;
      if(socs().some(x=>nrm(x.n)===nrm(v)))return GM.ui.toast('Esa sociedad ya está en la lista');
      socsMine().push({n:v,c:S().pais||''});GM.save();render(el)}
    if(k==='ren'){const v=(prompt(T('Nuevo nombre'),n)||'').trim();if(!v||v===n)return;
      const x=socsMine().find(z=>z.n===n);if(x)x.n=v;
      Object.values(S().reg).forEach(L=>L.forEach(e=>{if(e.soc===n)e.soc=v}));   // existing registrations follow the new name
      GM.save();render(el);GM.ui.toast('Sociedad renombrada')}
    if(k==='del'){const used=Object.values(S().reg).some(L=>L.some(e=>e.soc===n));
      if(!await GM.ui.ask('¿Quitar esta sociedad de la lista?',used?'Los registros que ya la usan se conservan con su nombre.':'No la usa ningún registro.','Quitar'))return;
      S().socs=socsMine().filter(z=>z.n!==n);GM.save();render(el)}
    if(k==='reset'&&await GM.ui.ask('¿Restaurar la lista predefinida?','Se recupera la lista inicial de sociedades. Tus registros no cambian.','Restaurar')){delete S().socs;GM.save();render(el)}}}

/* ---------- registration sheet (CSV) ---------- */
const COLS=[['id','ID'],['titulo','Título'],['rel','Estado de publicación'],['soc','Sociedad'],['cod','Código o número'],['fecha','Fecha'],['est','Estado del registro'],['au','% autor'],['ed','% editor'],['notas','Notas']];
// header names accepted on import, in the four languages (normalized: no accents, no spaces or symbols)
const ALIAS={id:['id'],titulo:['titulo','title','titel','cancion','song','musica','tema'],
  rel:['estadodepublicacion','releasestatus','veroffentlichungsstatus','estadodepublicacao','publicacion','release'],
  soc:['sociedad','society','gesellschaft','verwertungsgesellschaft','sociedade'],
  cod:['codigoonumero','codigo','code','codeornumber','codeodernummer','nummer','codigoounumero','numero','number'],
  fecha:['fecha','date','datum','data'],
  est:['estadodelregistro','registrationstatus','registrierungsstatus','estadodoregistro','estadodoregisto','statusdoregistro','estado','status'],
  au:['autor','author','urheber','autorpct','writer','composer'],ed:['editor','publisher','verlag','editora','herausgeber'],
  notas:['notas','notes','notizen','anmerkungen','observaciones','observacoes']};
const VAL_EST={pend:['pendiente','pending','ausstehend','offen','pendente'],env:['enviado','sent','gesendet','eingereicht','submitted'],reg:['registrado','registered','registriert','registada','registrada']};
const VAL_REL={un:['sinpublicar','unreleased','unveroffentlicht','naopublicada','inedita','inedito'],pre:['prereleased','prerelease','adelanto','vorabveroffentlicht','vorab'],pub:['publicada','published','veroffentlicht','publicado','released']};
function exportar(){
  const sep=(window.GM&&GM.idioma==='en')?',':';';   // what Excel expects in each locale (comma decimal → semicolon)
  const q=v=>{v=v==null?'':String(v);return /[";,\n\r]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v};
  const L=[COLS.map(c=>q(T(c[1]))).join(sep)];
  const relN=s=>T(REL.find(x=>x[0]===relOf(s))[1]);
  GM.songs.filter(s=>!GM.isDraft(s)).sort((a,b)=>GM.title(a).localeCompare(GM.title(b),'es')).forEach(s=>{
    const R=regsOf(s);
    (R.length?R:[null]).forEach(e=>L.push([s.id,GM.title(s),relN(s),e?e.soc:'',e?e.cod:'',e?e.fecha:'',e?T(estOf(e.est)[1]):'',e?e.au:'',e?e.ed:'',e?e.notas:''].map(q).join(sep)))});
  const b=new Blob(['﻿'+L.join('\r\n')+'\r\n'],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=T('Derechos')+'.csv';document.body.appendChild(a);a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove()},1500);GM.ui.toast('Hoja descargada')}

/* ---------- import: read → preview → apply ---------- */
function valOf(map,v,labels){const n=nrm(v);if(!n)return '';for(const [k,L] of Object.entries(map)){if(L.includes(n)||nrm(T(labels(k)))===n||nrm(labels(k))===n)return k}return null}
function fecha(v){v=String(v||'').trim();if(!v)return '';
  if(/^\d{4,5}(\.\d+)?$/.test(v)&&+v>20000){const d=new Date(Date.UTC(1899,11,30)+Math.round(+v)*864e5);return d.toISOString().slice(0,10)}  // Excel serial date
  let m=v.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);if(m)return `${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`;
  m=v.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$/);if(m){let [_,d,mo,y]=m;if(+mo>12&&+d<=12)[d,mo]=[mo,d];if(y.length===2)y='20'+y;return `${y}-${mo.padStart(2,'0')}-${d.padStart(2,'0')}`}
  return v}
const pct=v=>{v=String(v==null?'':v).replace('%','').replace(',','.').trim();if(!v)return '';const n=+v;return isFinite(n)?String(Math.round(n*100)/100):''};
async function importar(file,done){
  const buf=await file.arrayBuffer();
  const r=await GM.api('derechos','leer?nombre='+encodeURIComponent(file.name),buf).catch(e=>({ok:false,error:String(e)}));
  if(!r||!r.ok)return GM.ui.toast(T('No se pudo leer el archivo')+(r&&r.error?': '+T(r.error):''));
  const F=(r.filas||[]).filter(f=>f.some(c=>String(c).trim()));
  if(F.length<2)return GM.ui.toast('La hoja no tiene filas');
  const H=F[0].map(nrm),col={};
  for(const [k,al] of Object.entries(ALIAS)){
    const cands=[...al,nrm(T((COLS.find(c=>c[0]===k)||[])[1]||''))];
    const i=H.findIndex((h,j)=>cands.includes(h)&&!Object.values(col).includes(j));if(i>=0)col[k]=i}
  if(col.id===undefined&&col.titulo===undefined)return GM.ui.toast('No encuentro la columna del título ni la del ID');
  const plan=planear(F.slice(1),col);preview(plan,done)}
function planear(rows,col){
  const st=S(),reg=JSON.parse(JSON.stringify(st.reg)),byT={},newSocs=[],acts=[],warn=[];let same=0;
  GM.all.forEach(s=>{const k=nrm(GM.title(s));(byT[k]=byT[k]||[]).push(s)});
  const g=(row,k)=>col[k]===undefined?'':String(row[col[k]]==null?'':row[col[k]]).trim();
  const relDone={};
  rows.forEach((row,i)=>{
    const n=i+2,id=g(row,'id'),tit=g(row,'titulo');
    let s=id?GM.song(id):null;
    if(!s&&tit){const c=byT[nrm(tit)]||[];if(c.length>1)return warn.push([n,'hay varias canciones con ese título',tit]);s=c[0]}
    if(!s)return warn.push([n,'no encuentro la canción',tit||id]);
    const rv=g(row,'rel');
    if(rv){const v=valOf(VAL_REL,rv,k=>REL.find(x=>x[0]===k)[1]);
      if(v===null)warn.push([n,'estado de publicación desconocido',rv]);
      else if(v&&v!==relOf(s)&&relDone[s.id]!==v){relDone[s.id]=v;acts.push({t:'rel',s,v})}}
    const soc=g(row,'soc'),v={cod:g(row,'cod'),fecha:fecha(g(row,'fecha')),au:pct(g(row,'au')),ed:pct(g(row,'ed')),notas:g(row,'notas')};
    const ev=g(row,'est'),est=ev?valOf(VAL_EST,ev,k=>estOf(k)[1]):'';
    if(est===null)warn.push([n,'estado del registro desconocido',ev]);
    if(!soc){if(v.cod||v.fecha||v.notas||v.au||v.ed||est)warn.push([n,'fila sin sociedad: se ignora',tit||id]);return}
    let socN=(socs().find(x=>nrm(x.n)===nrm(soc))||{}).n;
    if(!socN){socN=(newSocs.find(x=>nrm(x)===nrm(soc)))||soc;if(!newSocs.includes(socN)){newSocs.push(socN);warn.push([n,'sociedad nueva, se añadirá a tu lista',soc])}}
    if(regsOf(s).some(e=>e.ro&&nrm(e.soc)===nrm(socN)&&(!v.cod||nrm(e.cod)===nrm(v.cod)))){same++;return}
    const L=reg[s.id]=reg[s.id]||[];
    const ex=L.find(e=>nrm(e.soc)===nrm(socN)&&(nrm(e.cod)===nrm(v.cod)||!e.cod||!v.cod));
    if(ex){const ch={};Object.entries(v).forEach(([k,x])=>{if(x!==''&&x!==String(ex[k]??''))ch[k]=x});if(est&&est!==ex.est)ch.est=est;
      if(Object.keys(ch).length){Object.assign(ex,ch);acts.push({t:'upd',s,soc:socN,ch})}else same++}
    else{const e={id:uid(),soc:socN,est:est||'pend',...v};L.push(e);acts.push({t:'new',s,soc:socN,e})}});
  Object.keys(reg).forEach(k=>{if(!reg[k].length)delete reg[k]});
  return {reg,newSocs,acts,warn,same}}
function preview(p,done){
  const nn=p.acts.filter(a=>a.t==='new').length,nu=p.acts.filter(a=>a.t==='upd').length,nr=p.acts.filter(a=>a.t==='rel').length;
  const relN=v=>REL.find(x=>x[0]===v)[1];
  const o=GM.ui.modal(`<h3>Importar la hoja de registro</h3>
    <div class="der-sum"><div><b>${nn}</b> <span>registros nuevos</span></div><div><b>${nu}</b> <span>registros que cambian</span></div><div><b>${nr}</b> <span>cambios de estado de publicación</span></div><div><b>${p.same}</b> <span>filas sin cambios</span></div></div>
    ${p.acts.length?`<div class="der-prev">${p.acts.slice(0,200).map(a=>`<div><span class="b ${a.t==='new'?'ok':'warn'}">${a.t==='new'?'Nuevo':a.t==='upd'?'Cambia':'Estado'}</span> <b>${E(GM.title(a.s))}</b> · ${a.t==='rel'?`<span>${relN(a.v)}</span>`:E(a.soc)+(a.t==='new'&&a.e.cod?' '+E(a.e.cod):'')+(a.t==='upd'?' <span class="meta">('+Object.keys(a.ch).map(k=>E(T((COLS.find(c=>c[0]===k)||[k,k])[1]))).join(', ')+')</span>':'')}</div>`).join('')}</div>`:'<div class="meta">No hay nada que cambiar.</div>'}
    ${p.warn.length?`<h4>Avisos <span class="meta">${p.warn.length}</span></h4><div class="der-prev der-warn">${p.warn.slice(0,200).map(([n,t,x])=>`<div><span>Fila</span> ${n}: <span>${t}</span> «${E(x)}»</div>`).join('')}</div>`:''}
    <div class="meta">Al importar no se borra ningún registro.</div>
    <div class="acts"><button class="chip" data-x="0">Cancelar</button>${p.acts.length||p.newSocs.length?'<button class="chip pri" data-x="1">Aplicar</button>':''}</div>`);
  o.querySelector('.dlg').classList.add('wide');
  o.onclick=ev=>{if(ev.target===o)return o.remove();const x=ev.target.dataset.x;if(x===undefined)return;o.remove();if(x!=='1')return;
    const st=S();st.reg=p.reg;p.newSocs.forEach(addSoc);
    p.acts.filter(a=>a.t==='rel').forEach(a=>setRel(a.s,a.v));
    changed();GM.ui.toast('Hoja importada ✓');if(done)done()}}

/* ---------- home: registered vs missing ---------- */
function home(el){
  const P=pubSongs();if(!P.length){el.closest('section')&&el.closest('section').remove();return}
  const m=P.filter(sinReg).length,ok=P.length-m,a=ok*100/P.length;
  el.innerHTML=`<div class="charts"><div class="panel ch der-click" data-der="go"><h4>Registro de lo publicado</h4><div class="row"><div class="der-donut" style="background:conic-gradient(var(--good) 0 ${a}%,var(--bad) ${a}% 100%)"><i></i></div>
    <div class="meta" style="line-height:1.9">🟢 <span>Con algún registro</span> ${ok}<br>🔴 <span>Sin registro</span> ${m}</div></div></div></div>`;
  el.onclick=ev=>{if(ev.target.closest('[data-der="go"]'))GM.ui.go('mod:derechos')}}

GM.register({
  id:'derechos',
  nav:{label:'Derechos',icon:'©'},
  render(el){render(el)},
  songSection:{title:'Derechos',render(el,s){songSec(el,s)}},
  home:{title:'Derechos',render(el){home(el)}},
  badges(s){return own(s).map(e=>`<span class="b ${estCls(e.est)}">${E(e.soc)}</span>`).join('')},
  tasks(){const n=GM.songs.filter(sinReg).length;
    return [{k:'pubsinreg',ic:'🏛',n,t:'publicadas sin ningún registro',d:'No tienen ningún registro en una sociedad de autores. Añádelo en la página de la canción, sección Derechos.'}]},
  filters:[{k:'pubsinreg',label:'Publicadas sin registro',fn:s=>sinReg(s),pend:true}],
});
DER.regsOf=regsOf;DER.relOf=relOf;
})();
