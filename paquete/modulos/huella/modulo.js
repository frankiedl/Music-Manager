/* «huella» module: asks AudD (audio recognition) whether a master already sounds like a known song, BEFORE you publish it.
   - Menu section «Huella»: paste your own AudD token once (kept only in datos/modulos/huella/cuenta.json), choose songs, confirm, wait.
   - Per song it sends three 12-second clips cut with ffmpeg (never the whole song), and shows the matches (artist, title, link).
   - A match is a warning, not a verdict: it may be your own published version, a sample, or a false positive.
   Nothing is sent unless the user confirms in the dialog. Results are kept in resultados.json.
   - Song page, section «Huella · inspección y etiquetado»: local only. Inspects ONE audio file (tags, blocks, covers, hashes, signal) and writes the
     author's own metadata on a safe copy in _etiquetados/ (see the block below the AudD code). */
(function(){
const ID='huella';
const E=s=>GM.ui.esc(s==null?'':String(s));
let EST=null,RES={},SEL=new Set(),ABIERTO=null,EJEC=null;
const versiones=s=>(s.versions||[]).filter(v=>v&&v.p);
const esMaster=p=>/\/master\//i.test(p||'');
function fuente(s){const v=versiones(s),fin=GM.finalPath(s),M=v.filter(x=>esMaster(x.p));
  if(M.length){const f=M.find(x=>x.p===fin);return f?f.p:M[0].p}
  return fin||GM.bestVersion(s)||(v[0]&&v[0].p)||''}
const nombre=p=>String(p||'').split('/').pop();

async function cargar(){
  try{EST=await GM.api(ID,'estado')}catch(e){EST={ok:false}}
  try{const r=await GM.api(ID,'resultados');RES=(r&&r.resultados)||{}}catch(e){RES={}}
}
function pastilla(r){
  if(!r)return '<span class="b">sin comprobar</span>';
  if(r.error)return `<span class="b warn" title="${E(r.error)}">no se pudo</span>`;
  if(!r.coincidencias.length)return '<span class="b ok">sin coincidencias</span>';
  return `<span class="b warn">coincide con ${r.coincidencias.length===1?'1 canción':r.coincidencias.length+' canciones'}</span>`}
function detalle(s,r){
  if(!r)return '';
  if(r.error)return `<div class="hf-det">${E(r.error)}</div>`;
  if(!r.coincidencias.length)return `<div class="hf-det">${r.clips} fragmentos comprobados el ${E(r.t)}. AudD no reconoce nada parecido. Eso no garantiza que nadie más tenga algo igual, solo que su catálogo no lo detecta.</div>`;
  return `<div class="hf-det">${r.coincidencias.map(c=>`<div><b>${E(c.artista)}, ${E(c.titulo)}</b>${c.album?' · álbum «'+E(c.album)+'»':''}${c.sello?' · '+E(c.sello):''}${c.fecha?' · '+E(c.fecha):''} ${c.link?`<a href="${E(c.link)}" target="_blank" rel="noopener">ver</a>`:''}</div>`).join('')}<div style="margin-top:6px">Puede ser una versión tuya ya publicada, un sample o un falso positivo. Escucha la coincidencia antes de decidir.</div></div>`}

function pintar(el){
  const L=GM.songs.map(s=>({s,p:fuente(s)})).filter(x=>x.p);
  const tok=EST&&EST.token;
  el.innerHTML=`<h1>Huella</h1><p class="lead">Comprueba si un máster ya suena a algo conocido antes de publicarlo. Se envían tres fragmentos de 12 segundos de cada canción, nunca la canción entera.</p>
  <div class="panel"><h2>Tu cuenta de AudD</h2>
    ${tok?`<p class="meta">Token guardado en este ordenador. Nunca se muestra ni se sube a ningún sitio.</p><div class="hf-tok"><button class="chip" id="hf-borrar">Olvidar el token</button></div>`
        :`<p class="meta">Crea una cuenta en <b>dashboard.audd.io</b>, copia tu token y pégalo aquí. El servicio puede tener coste según tu plan. Mira sus tarifas en su web.</p><div class="hf-tok"><input type="password" id="hf-tok" placeholder="Token de AudD" autocomplete="off" aria-label="Token de AudD"><button class="chip pri" id="hf-guardar">Guardar</button></div>`}
    ${EST&&!EST.ffmpeg?'<p class="meta" style="color:var(--warn)">No encuentro ffmpeg: solo se pueden comprobar archivos de menos de 9 MB.</p>':''}
  </div>
  <div class="panel"><h2>Qué comprobar</h2>
    ${L.length?'':'<p class="meta">Aún no hay canciones con audio.</p>'}
    <div id="hf-lista">${L.map(({s,p})=>`<div class="hf-row"><input type="checkbox" data-id="${E(s.id)}" ${SEL.has(String(s.id))?'checked':''} aria-label="Elegir ${E(GM.title(s))}"><div class="hf-t" data-ver="${E(s.id)}" style="cursor:pointer">${E(GM.title(s))}</div><div class="meta" title="${E(p)}">${E(nombre(p))}</div><div>${pastilla(RES[s.id])}</div></div>${ABIERTO===String(s.id)?detalle(s,RES[s.id]):''}`).join('')}</div>
    <div class="hf-tok" style="margin-top:12px"><button class="chip pri" id="hf-go" ${tok&&SEL.size&&!EJEC?'':'disabled'}>Comprobar ${SEL.size||''} ${SEL.size===1?'canción':'canciones'}</button><button class="chip" id="hf-todas">Elegir todas</button><span id="hf-prog" class="meta"></span></div>
    <div class="hf-bar" id="hf-bar" hidden><i></i></div>
  </div>`;
  el.querySelector('#hf-guardar')&&(el.querySelector('#hf-guardar').onclick=async()=>{
    const v=el.querySelector('#hf-tok').value;const r=await GM.api(ID,'token',{token:v}).catch(()=>({ok:false,error:'Error'}));
    if(!r.ok)return GM.ui.toast(r.error||'No se pudo guardar');await cargar();pintar(el);GM.ui.toast('Token guardado')});
  el.querySelector('#hf-borrar')&&(el.querySelector('#hf-borrar').onclick=async()=>{
    if(!await GM.ui.ask('¿Olvidar el token?','Se borra de este ordenador. Los resultados ya guardados se conservan.','Olvidar'))return;
    await GM.api(ID,'borrar_token',{});await cargar();pintar(el)});
  el.querySelectorAll('#hf-lista input[type=checkbox]').forEach(c=>c.onchange=()=>{const id=c.dataset.id;c.checked?SEL.add(id):SEL.delete(id);pintar(el)});
  el.querySelectorAll('[data-ver]').forEach(b=>b.onclick=()=>{ABIERTO=ABIERTO===b.dataset.ver?null:b.dataset.ver;pintar(el)});
  el.querySelector('#hf-todas').onclick=()=>{L.forEach(({s})=>SEL.add(String(s.id)));pintar(el)};
  el.querySelector('#hf-go').onclick=()=>lanzar(el,L);
}
async function lanzar(el,L){
  const items=L.filter(x=>SEL.has(String(x.s.id))).map(x=>({id:x.s.id,p:x.p}));if(!items.length)return;
  if(!await GM.ui.ask('¿Enviar fragmentos a AudD?',`Se enviarán a AudD (api.audd.io) tres fragmentos de 12 segundos de ${items.length} ${items.length===1?'canción':'canciones'}, no las canciones enteras, para saber si coinciden con alguna conocida. Los originales no se tocan. Esto puede consumir peticiones de tu plan de AudD.`,'Enviar'))return;
  const r=await GM.api(ID,'comprobar',{items}).catch(()=>({ok:false,error:'Error'}));
  if(!r.ok)return GM.ui.toast(r.error||'No se pudo empezar');
  EJEC=r.job;pintar(el);const bar=el.querySelector('#hf-bar'),pg=el.querySelector('#hf-prog');bar.hidden=false;
  const t=setInterval(async()=>{
    const j=await GM.api(ID,'progreso?job='+r.job).catch(()=>null);
    if(!j||!j.ok){clearInterval(t);EJEC=null;return}
    const b=el.querySelector('#hf-bar i'),p=el.querySelector('#hf-prog');
    if(b)b.style.setProperty('--v',j.total?j.hechos/j.total:0);if(p)p.textContent=j.hechos+' de '+j.total;
    if(j.estado==='listo'){clearInterval(t);EJEC=null;SEL.clear();await cargar();if(el.isConnected)pintar(el);
      const n=Object.values(j.resultados||{}).filter(x=>x.coincidencias&&x.coincidencias.length).length;
      GM.ui.toast(n?`Hecho: ${n} ${n===1?'canción tiene':'canciones tienen'} coincidencias`:'Hecho: sin coincidencias')}
  },1000)}

/* ================= Inspección y etiquetado de UN archivo (sección de la página de cada canción) =================
   Regla de oro: ver primero → limpiar lo ajeno por defecto → poner lo tuyo → verificar que el audio no cambia.
   · POST inspeccionar {p, senal}                      → etiquetas, bloques, carátulas, avisos, hashes, señal (con «rasgos»: valor, umbral, margen)
   · POST etiquetar {p, poner, creditos, conservar, nombre, simular}  → plan (simular:true) o copia en _etiquetados/ con verificación estricta
   Todo lo que se pinta sale del servidor (el plan dice cómo se marca cada elemento para conservar: «como»). Nada se envía fuera del equipo. */
const AUD=/\.(wav|mp3|m4a|flac|aiff?)$/i;
const ROLES=[['letra','Letra'],['musica','Música / melodía'],['arreglos','Arreglos'],['produccion','Producción'],['grabacion','Grabación'],['mezcla','Mezcla'],['masterizacion','Masterización'],['asistencia','Asistencia'],['otro','Otro']];
const RASGOS={corte_espectral:['Corte espectral','Caída más brusca del espectro por encima de 8 kHz'],energia_ultrasonica:['Energía ultrasónica','Nivel por encima de 20 kHz frente a los medios'],
  pico_tonal_hf:['Pico tonal en alta frecuencia','Tono estrecho y estable por encima de 16 kHz'],picos_equiespaciados_hf:['Picos equiespaciados en alta frecuencia','Varios picos separados de forma regular']};
const CAMPOS=[['title','Título',''],['artist','Artista',''],['album','Álbum',''],['date','Fecha','AAAA o AAAA-MM-DD'],['genre','Género',''],['isrc','ISRC','ES-XXX-26-00001'],['copyright','Copyright','2026 Tu nombre']];
const CAMPO={title:'Título',artist:'Artista',album:'Álbum',album_artist:'Artista del álbum',date:'Fecha',genre:'Género',track:'Pista',disc:'Disco',composer:'Compositor',lyricist:'Autoría de la letra',publisher:'Editorial',copyright:'Copyright',isrc:'ISRC',comment:'Comentario',lyrics:'Letra',language:'Idioma',creditos:'Créditos',caratula:'Carátula'};
const campoTxt=c=>/^personalizado:/.test(c)?'Campo propio: '+c.slice(13):(CAMPO[c]||c);
const pic=n=>n===1?'pico':'picos';
const HI=new Map();let GUARDA=null;
const kb=n=>n==null?'':(n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB');
const num=(n,d)=>n==null?'—':Number(n).toFixed(d==null?1:d);
const corto=(t,n)=>{t=String(t==null?'':t);return t.length>n?t.slice(0,n)+'…':t};
const rolTxt=r=>(ROLES.find(x=>x[0]===r)||[0,r])[1];

function defecto(s){const t=(GM.cfg.titular||GM.cfg.artista||'').trim();
  return {title:GM.title(s),artist:GM.cfg.artista||'',album:'',date:'',genre:'',isrc:'',copyright:t?new Date().getFullYear()+' '+t:'',lyrics:GM.lyrics(s.id)||'',nombre:'',cred:[]}}
function estado(s){
  let e=HI.get(s.id);if(e)return e;
  const aud=versiones(s).map(v=>v.p).filter(p=>AUD.test(p)),pref=fuente(s),b=((GM.state(ID).borradores||{})[s.id])||null;
  e={s,aud,p:aud.includes(pref)?pref:(aud[0]||''),insp:null,plan:null,cons:new Set(),sim:null,simKey:'',res:null,busy:'',f:Object.assign(defecto(s),b||{}),extra:null,lyricsAuto:!(b&&b.lyrics)};
  HI.set(s.id,e);return e}
function guardarBorrador(e){
  clearTimeout(GUARDA);GUARDA=setTimeout(()=>{const st=GM.state(ID),b=JSON.parse(JSON.stringify(e.f));
    if(b.lyrics===(GM.lyrics(e.s.id)||''))delete b.lyrics;delete b.nombre;(st.borradores=st.borradores||{})[e.s.id]=b;GM.save()},700)}

/* ---- qué se conserva: la clave la da el plan («como»), la interfaz no adivina ---- */
const kAcc=a=>a.como==='bloque'?'k|'+a.bloque:a.como==='binario'?'b|'+a.bloque+'|'+a.id+'|'+(a.propietario||''):a.como==='caratula'?'c|'+a.indice:'e|'+a.bloque+'|'+a.clave;
function conservarDe(e){
  const out=[],vistos=new Set();
  ((e.plan&&e.plan.acciones)||[]).forEach(a=>{const k=kAcc(a);if(!a.conservable||!e.cons.has(k)||vistos.has(k))return;vistos.add(k);
    out.push(a.como==='etiqueta'?{tipo:'etiqueta',bloque:a.bloque,clave:a.clave}:a.como==='binario'?{tipo:'binario',bloque:a.bloque,id:a.id,propietario:a.propietario}
      :a.como==='bloque'?{tipo:'bloque',bloque:a.bloque}:{tipo:'caratula',indice:a.indice})});
  return out}
function cuerpo(e,simular){
  const f=e.f,poner={};['title','artist','album','date','genre','isrc','copyright','lyrics'].forEach(k=>{if(String(f[k]||'').trim())poner[k]=f[k]});
  const creditos=f.cred.filter(c=>String(c.nombre||'').trim()).map(c=>({rol:c.rol,nombre:c.nombre,tipo:c.tipo,nota:c.nota||''}));
  const stem=nombre(e.p).replace(/\.[^.]+$/,'');
  return {p:e.p,poner,creditos,conservar:conservarDe(e),nombre:String(f.nombre||'').trim()||stem+'_etiquetado',simular}}
const claveCambios=e=>{const c=cuerpo(e,true);delete c.simular;return JSON.stringify(c)};

/* ---- lectura del formulario antes de volver a pintar (no se pierde nada de lo escrito) ---- */
function leerForm(el,e){
  if(!el.querySelector('#hi-f-title'))return;
  CAMPOS.forEach(([k])=>{const i=el.querySelector('#hi-f-'+k);if(i)e.f[k]=i.value});
  const l=el.querySelector('#hi-f-lyrics');if(l)e.f.lyrics=l.value;
  const n=el.querySelector('#hi-f-nombre');if(n)e.f.nombre=n.value;
  el.querySelectorAll('.hi-cred').forEach(r=>{const c=e.f.cred[+r.dataset.i];if(!c)return;
    c.rol=r.querySelector('.hi-c-rol').value;c.nombre=r.querySelector('.hi-c-nom').value;c.tipo=r.querySelector('.hi-c-tipo').value;c.nota=r.querySelector('.hi-c-nota').value})}

function nomAcc(e,a){
  if(a.como==='bloque'){const b=((e.insp&&e.insp.bloques_etiqueta)||[]).find(x=>x.id===a.bloque);return b?b.tipo:'bloque '+a.bloque}
  return a.tipo==='etiqueta'?a.clave:a.tipo==='binario'?a.id+(a.propietario?' · '+a.propietario:''):'Carátula ('+a.clave+')'}
const unicos=(e,L)=>{const v=new Set(),o=[];L.forEach(a=>{const n=nomAcc(e,a);if(!v.has(n)){v.add(n);o.push({a,n})}});return o};
const FORMATOS={wav:'WAV',mp3:'MP3',flac:'FLAC',mp4:'MP4 / M4A'};

/* ---- cabecera: archivo, acciones y ficha de integridad ---- */
function estadoFicha(insp){
  const av=(insp&&insp.avisos)||[],graves=av.filter(a=>a.nivel==='error').length,n=av.filter(a=>a.nivel!=='info').length;
  if(!insp)return '<span class="b">sin inspeccionar</span>';
  if(graves)return `<span class="b hi-bad">Atención · ${graves} ${graves===1?'problema de integridad':'problemas de integridad'}</span>`;
  return n?`<span class="b warn">OK · Con avisos (${n})</span>`:'<span class="b ok">OK</span>'}
function cabecera(e){
  const i=e.insp,a=i&&i.archivo,au=i&&i.audio,c=i&&i.contenedor,opts=e.aud.concat(e.extra&&!e.aud.includes(e.extra)?[e.extra]:[]);
  const av=(i&&i.avisos)||[],hay=!!(i&&i.ok);
  return `<div class="hi-card"><div class="hi-top"><div class="hi-file"><label class="meta" for="hi-sel">Archivo</label>
    ${opts.length?`<select id="hi-sel" ${e.busy?'disabled':''}>${opts.map(p=>`<option value="${E(p)}" ${p===e.p?'selected':''}>${E(p===e.extra?'🏷 ':'')}${E(nombre(p))}</option>`).join('')}</select>`:'<span class="meta">Esta canción no tiene archivos de audio.</span>'}
    <span class="meta hi-ruta" title="${E(e.p)}"><code class="hi-d">${E(e.p)}</code></span></div>
    <div class="hi-acts">${estadoFicha(hay?i:null)}
      <button class="chip pri" data-hi="insp-senal" ${e.busy||!e.p?'disabled':''}>Inspeccionar con señal</button>
      <button class="chip" data-hi="insp" ${e.busy||!e.p?'disabled':''} title="Más rápido: solo etiquetas, bloques y datos del contenedor">Inspeccionar sin señal</button>
      <button class="chip" data-hi="reset" ${e.busy?'disabled':''}>Resetear</button></div></div>
    ${e.busy==='insp'?'<div class="meta hi-busy">Inspeccionando…</div>':''}
    ${i&&!i.ok?`<div class="callout">${E((i.errores||[]).join(' · ')||'No se pudo inspeccionar el archivo.')}</div>`:''}
    ${hay?`<div class="hi-hashes"><div class="hi-hash" data-hi="copiar" data-v="${E(a.sha256)}" title="Pulsa para copiar"><div class="meta">SHA-256 del archivo</div><div class="meta">cambia si cambian las etiquetas o el contenedor</div><div class="hi-mono">${E(a.sha256)}</div></div>
      <div class="hi-hash" data-hi="copiar" data-v="${E(a.sha256_audio||'')}" title="Pulsa para copiar"><div class="meta">sha256_audio</div><div class="meta">la huella del sonido: debe quedar idéntica al etiquetar</div><div class="hi-mono">${a.sha256_audio?E(a.sha256_audio):'<span class="meta">no se pudo calcular</span>'}</div></div></div>
      <div class="hi-tec">${[['Formato',(FORMATOS[c.familia]||c.formato||c.familia||'—')],['Códec',au.codec||'—'],['Tasa de muestreo',au.tasa_muestreo_hz?au.tasa_muestreo_hz+' Hz':'—'],['Canales',au.canales||'—'],['Duración',c.duracion_s!=null?num(c.duracion_s,2)+' s':'—'],['Tamaño',kb(a.tamano_bytes)]]
        .map(([k,v])=>`<span class="hi-kv"><span class="meta">${k}</span> <b>${E(v)}</b></span>`).join('')}</div>
      ${av.length?`<details class="hi-avisos" ${av.some(x=>x.nivel==='error')?'open':''}><summary>Avisos (${av.length})</summary>${av.map(x=>`<div class="hi-aviso"><span class="b ${x.nivel==='error'?'hi-bad':x.nivel==='aviso'?'warn':''}">${x.nivel==='error'?'error':x.nivel==='aviso'?'aviso':'info'}</span> <span>${E(x.mensaje)}</span></div>`).join('')}</details>`:''}`:''}</div>`}

/* ---- bloque 1: inspección y señal ---- */
function filasElementos(e){
  const A=(e.plan&&e.plan.acciones)||[],i=e.insp,bl=new Map(((i&&i.bloques_etiqueta)||[]).map(b=>[b.id,b.tipo])),
    et=new Map(((i&&i.etiquetas)||[]).map(x=>[x.bloque+'|'+x.clave_original,x])),
    bin=new Map(((i&&i.incrustados&&i.incrustados.bloques_binarios)||[]).map(x=>[x.bloque+'|'+x.id+'|'+(x.propietario||''),x])),car=(i&&i.incrustados&&i.incrustados.caratulas)||[];
  return A.map(a=>{
    let el,val,org,est;
    if(a.tipo==='etiqueta'){const it=et.get(a.bloque+'|'+a.clave)||{};el=a.clave;val=a.valor==null?'<span class="meta">contenido binario</span>':`<code class="hi-d">${E(corto(a.valor,90))}</code>`;org=bl.get(a.bloque)||'';
      est=it.editable===false?'solo lectura':'editable'}
    else if(a.tipo==='binario'){const b=bin.get(a.bloque+'|'+a.id+'|'+(a.propietario||''))||{};el=a.id+(a.propietario?' · '+a.propietario:'');
      val=b.texto_legible?'<span class="meta">contiene texto legible</span>':`<span class="meta">${kb(a.bytes)}</span>`;org=bl.get(a.bloque)||'';est=a.conservable?'opaco · solo lectura':'estructural'}
    else{const c=car[a.indice]||{};el='Carátula';val=`${E(c.mime||'imagen')} · ${c.ancho?c.ancho+'×'+c.alto+' · ':''}${kb(a.bytes)}`;org=a.clave;est='imagen incrustada'}
    return {a,el,val,org,est,k:kAcc(a)}})}
function bloque1(e){
  const i=e.insp,rows=filasElementos(e),sen=i&&i.senal;
  let h=`<section class="hi-card"><div class="hi-h"><h3>1. Inspección y señal</h3><span class="b">senal: ${sen?'true':'false'}</span></div>`;
  if(!i||!i.ok)return h+'<p class="meta">Elige un archivo y pulsa «Inspeccionar con señal» para ver qué lleva dentro, además del audio.</p></section>';
  h+=`<h4>Etiquetas y bloques encontrados</h4><p class="meta">Por defecto no se conserva nada: se limpia todo lo ajeno. Marca «Conservar» solo lo que quieras mantener.</p>`;
  h+=rows.length?`<div class="hi-tbl"><div class="hi-r hi-th"><span>Elemento</span><span>Valor / resumen</span><span>Origen</span><span>Estado</span><span>Conservar</span></div>${rows.map(r=>{
    const fijo=r.a.accion==='conservar'&&!r.a.conservable,on=fijo||e.cons.has(r.k);
    return `<div class="hi-r"><span class="hi-mono" title="${E(r.el)}">${E(corto(r.el,34))}</span><span>${r.val}</span><span class="meta">${E(r.org)}</span><span class="meta" ${r.a.motivo?`title="${E(r.a.motivo)}"`:''}>${r.est}</span>
      <label class="hi-chk" ${r.a.conservable?'':`title="${E(r.a.motivo||'No se puede conservar en este formato')}"`}><input type="checkbox" data-k="${E(r.k)}" ${on?'checked':''} ${r.a.conservable&&!e.busy?'':'disabled'} aria-label="Conservar"><span>${fijo?'se mantiene':'Conservar'}</span></label></div>`}).join('')}</div>`
    :((i.avisos||[]).some(a=>a.nivel==='error')?'<p class="meta">No se pudieron leer etiquetas de este archivo: mira los avisos de arriba.</p>':'<p class="meta">Este archivo no lleva etiquetas ni bloques ajenos al audio.</p>');
  h+=`<h4>Señal: mediciones e indicios técnicos</h4>`;
  if(!sen)h+='<p class="meta">Aún no se ha medido la señal. Pulsa «Inspeccionar con señal».</p>';
  else if(!sen.disponible)h+=`<div class="callout">${(sen.avisos||[]).map(a=>E(a.mensaje)).join('<br>')||'No se pudo analizar la señal.'}</div>`;
  else{const n=sen.niveles||{},so=sen.sonoridad||{};
    const chips=[['Pico',n.pico_muestra_dbfs!=null?num(n.pico_muestra_dbfs)+' dBFS':null],['RMS',n.rms_dbfs!=null?num(n.rms_dbfs)+' dBFS':null],['Sonoridad',so.integrada_lufs!=null?num(so.integrada_lufs)+' LUFS':null],
      ['Rango de sonoridad',so.rango_lu!=null?num(so.rango_lu)+' LU':null],['Pico real',so.pico_real_dbtp!=null?num(so.pico_real_dbtp)+' dBTP':null],['Saturadas',n.muestras_en_fondo_de_escala!=null?String(n.muestras_en_fondo_de_escala):null],['Silencios',n.silencios?String(n.silencios.length):null]];
    h+=`<div class="hi-tec">${chips.filter(x=>x[1]!=null).map(([k,v])=>`<span class="hi-kv"><span class="meta">${k}</span> <b>${E(v)}</b></span>`).join('')}</div>`;
    h+=(sen.rasgos&&sen.rasgos.length)?`<div class="hi-tbl hi-sen"><div class="hi-r hi-th"><span>Rasgo</span><span>Medición</span><span>Umbral</span><span>Margen</span></div>${sen.rasgos.map(r=>{
      const d=r.detalle||{},nm=RASGOS[r.id]||[r.id,''],pk=r.unidad==='picos';
      const med=r.valor==null?'<span class="meta">sin dato</span>':`${num(r.valor,pk?0:1)} ${pk?pic(r.valor):'dB'}`;
      const sub=r.id==='corte_espectral'&&d.frecuencia_hz?`cerca de ${d.frecuencia_hz} Hz`:r.id==='pico_tonal_hf'&&d.frecuencia_hz?`a ${d.frecuencia_hz} Hz · persistencia ${num(d.persistencia_pct,0)} %`:'';
      const m=r.margen,mm=m==null?'':num(Math.abs(m),pk?0:1),mar=m==null?'<span class="meta">—</span>':`${m>=0?'+':''}${mm} ${pk?pic(Math.abs(m)):'dB'} ${m>=0?'sobre':'bajo'} el umbral`;
      let no='';   // margin ≥ 0 but the trait does not count: say why (so «+0.1 dB over the threshold» next to «no indicio» is not a riddle)
      if(!r.dispara&&m!=null&&m>=0){
        if(r.id==='pico_tonal_hf'&&d.nivel_db!=null&&d.nivel_db<d.nivel_minimo_db)no=`no cuenta: su nivel (${num(d.nivel_db)} dBFS) está por debajo del mínimo (${num(d.nivel_minimo_db,0)} dBFS)`;
        else if(r.id==='pico_tonal_hf'&&d.persistencia_pct!=null&&d.persistencia_pct<d.persistencia_minima_pct)no=`no cuenta: aparece en el ${num(d.persistencia_pct,0)} % del tiempo (mínimo ${num(d.persistencia_minima_pct,0)} %)`;
        else if(r.id==='picos_equiespaciados_hf')no='no cuenta: no están separados de forma regular'}
      return `<div class="hi-r ${r.dispara?'hi-on':''}"><span><b>${nm[0]}</b><br><span class="meta">${nm[1]}</span></span><span>${med}${sub?`<br><span class="meta">${sub}</span>`:''}</span><span class="hi-mono">≥ ${num(r.umbral,pk?0:1)} ${pk?pic(r.umbral):'dB'}</span><span>${mar}<br>${r.dispara?'<span class="b warn">Indicio activo</span>':'<span class="b">Sin indicio</span>'}${no?`<br><span class="meta">${no}</span>`:''}</span></div>`}).join('')}</div>`
      :'<p class="meta">No hay espectro que medir (audio demasiado corto o en silencio).</p>';
    h+=(sen.indicios||[]).map(x=>`<div class="hi-ind">${E(x.descripcion)}</div>`).join('');
    h+=(sen.avisos||[]).length?`<div class="meta" style="margin-top:6px">${sen.avisos.map(a=>E(a.mensaje)).join('<br>')}</div>`:''}
  h+=`<div class="callout hi-nota">Los datos de señal son mediciones e indicios técnicos, no una prueba legal ni un veredicto definitivo sobre el origen del audio.</div></section>`;
  return h}

/* ---- bloque 2: limpiar y etiquetar en copia segura ---- */
function panelPlan(e){
  const r=e.sim;if(!r)return '';
  if(!r.ok)return `<div class="hi-panel hi-mal"><b>${E(r.error||'No se pudo simular.')}</b>${(r.campos_invalidos||[]).map(x=>`<div>${E(x)}</div>`).join('')}</div>`;
  const p=r.plan,A=p.acciones||[],quita=unicos(e,A.filter(a=>a.accion==='quitar'||a.accion==='sustituir')),cons=unicos(e,A.filter(a=>a.accion==='conservar'));
  if(!p.puede_aplicarse)return `<div class="hi-panel hi-mal"><b>Este archivo no se puede etiquetar</b><div class="hi-sec">${(p.avisos||[]).map(a=>`<div class="hi-aviso"><span class="b hi-bad">error</span> <span>${E(a.mensaje)}</span></div>`).join('')}</div>
    <div class="meta" style="margin-top:6px">Puedes inspeccionarlo, pero no se escribe nada en él.</div></div>`;
  const est={ok:'ok',plegado:'plegado en el comentario',no_soportado:'no soportado en este formato'};
  return `<div class="hi-panel"><b>Simulación lista · no se ha escrito ningún archivo</b>
    <div class="hi-sec"><h4>Se quita</h4>${quita.length?`<div class="hi-pills">${quita.map(({a,n})=>`<span class="b" ${a.motivo?`title="${E(a.motivo)}"`:''}>${E(corto(n,40))}</span>`).join('')}</div>`:'<span class="meta">nada</span>'}</div>
    <div class="hi-sec"><h4>Se conserva</h4>${cons.length?`<div class="hi-pills">${cons.map(({n})=>`<span class="b ok">${E(corto(n,40))}</span>`).join('')}</div>`:'<span class="meta">nada</span>'}</div>
    <div class="hi-sec"><h4>Se escribe</h4>${(p.se_escribira||[]).length?`<div class="hi-tbl hi-esc">${p.se_escribira.map(w=>`<div class="hi-r"><span>${E(campoTxt(w.campo))}</span><span class="meta"><code class="hi-d">${E(corto(w.valor,60))}</code></span><span class="hi-mono">${E(w.destino||'—')}</span><span><span class="b ${w.estado==='ok'?'ok':'warn'}" ${w.motivo?`title="${E(w.motivo)}"`:''}>${est[w.estado]||w.estado}</span></span></div>`).join('')}</div>`:'<span class="meta">nada: la copia queda limpia, solo con el audio</span>'}</div>
    <div class="hi-sec"><h4>Avisos del formato</h4>${(p.avisos||[]).length?p.avisos.map(a=>`<div class="hi-aviso"><span class="b ${a.nivel==='error'?'hi-bad':a.nivel==='aviso'?'warn':''}">${a.nivel==='error'?'error':a.nivel==='aviso'?'aviso':'info'}</span> ${a.campo?`<b>${E(campoTxt(a.campo))}</b><span>: </span>`:''}<span>${E(a.mensaje)}</span></div>`).join(''):'<span class="meta">ninguno</span>'}
      <div class="meta" style="margin-top:6px"><span>Escritor:</span> <b>${E(p.soporte&&p.soporte.escritor||'—')}</b></div></div></div>`}
function panelRes(e){
  const r=e.res;if(!r)return '';
  const v=r.verificacion||{};
  if(!r.ok)return `<div class="hi-panel hi-mal"><b>No se entregó ninguna copia</b>${(v.errores||[]).length?'':`<div>${E(r.error||'')}</div>`}${(r.campos_invalidos||[]).map(x=>`<div>${E(x)}</div>`).join('')}${(v.errores||[]).map(x=>`<div>✗ ${E(x)}</div>`).join('')}
    <div class="meta" style="margin-top:6px">El archivo temporal se borró y el original no se tocó.</div></div>`;
  const ok=(c,t)=>`<div class="hi-v">${c===null?'<span class="b">–</span>':c?'<span class="b ok">✓</span>':'<span class="b hi-bad">✗</span>'} <span>${t}</span></div>`,c=r.copia||{},rg=r.registro||{},cb=r.cambios||{};
  return `<div class="hi-panel hi-bien"><b>Copia lista · verificación estricta superada</b>
    ${ok(!!v.sha256_audio_igual,'sha256_audio idéntico')}<div class="hi-mono hi-aud">${E(r.despues&&r.despues.sha256_audio||'')}</div>
    ${ok(v.md5_decodificado_igual===null||v.md5_decodificado_igual===undefined?null:v.md5_decodificado_igual,v.md5_decodificado_igual==null?'Audio decodificado (MD5): no comprobado (hace falta ffmpeg)':'Audio decodificado (MD5) idéntico')}
    ${ok(!!(v.lectura_de_vuelta&&v.lectura_de_vuelta.ok),'Lo escrito se lee de vuelta igual')}${ok(!(v.etiquetas_inesperadas||[]).length,'No queda ninguna etiqueta ajena')}${ok(!!(v.bloques_conservados_ok&&v.caratulas_ok),'Bloques y carátulas conservados idénticos')}
    <div class="hi-sec"><span class="meta">Copia guardada en:</span> <span class="hi-mono">${E(c.p||'')}</span> <span class="meta">(${kb(c.bytes)})</span>
      <div class="hi-acts" style="margin-top:6px"><button class="chip" data-hi="abrir" data-p="${E(c.p||'')}">Mostrar en el explorador</button><button class="chip" data-hi="ver-copia" data-p="${E(c.p||'')}">Inspeccionar la copia</button></div></div>
    <div class="hi-sec"><span class="meta">Qué cambió:</span> <span>${(cb.quitadas||[]).length} etiquetas quitadas · ${(cb.escritas||[]).length} escritas</span></div>
    <div class="hi-sec">${rg.ok?`<span class="meta">Registro anotado en:</span> <span class="hi-mono">diario_movimientos.jsonl</span>, <span class="hi-mono">hashes.json</span>, <span class="hi-mono">etiquetado/${E(rg.id||'')}.json</span>`:`<span class="b warn">${E(rg.error||'No se pudo anotar en el registro.')}</span>`}</div></div>`}
function bloque2(e){
  const f=e.f,pl=e.plan,cons=pl?unicos(e,pl.acciones.filter(a=>a.conservable&&e.cons.has(kAcc(a)))):[],ext=(e.p.match(/\.[^.]+$/)||[''])[0].toLowerCase();
  const puede=e.sim&&e.sim.ok&&e.sim.plan.puede_aplicarse&&e.simKey===claveCambios(e);
  return `<section class="hi-card"><div class="hi-h"><h3>2. Limpiar y etiquetar en copia segura</h3><span class="b ok"><span>Destino:</span> <code>_etiquetados/</code></span></div>
    <p class="meta">Política: se limpia todo lo ajeno (salvo lo que marques en «Conservar») y solo se escribe lo que declares aquí. La onda de audio no se toca.</p>
    <div class="hi-conserva">${cons.length?`<span class="meta">Se conservará:</span> ${cons.map(({n})=>`<span class="b ok">${E(corto(n,30))}</span>`).join(' ')}`:'<span class="meta">No conservas nada: se limpia todo lo ajeno.</span>'}</div>
    <div class="hi-form">${CAMPOS.map(([k,t,ph])=>`<div class="hi-f"><label for="hi-f-${k}">${t}</label><input id="hi-f-${k}" type="text" value="${E(f[k])}" ${ph?`placeholder="${E(ph)}"`:''}></div>`).join('')}
      <div class="hi-f hi-full"><label for="hi-f-lyrics">Letra completa (opcional)</label><textarea id="hi-f-lyrics" placeholder="${E(window.T?window.T('Escribe o pega aquí la letra…'):'Escribe o pega aquí la letra…')}">${E(f.lyrics)}</textarea></div></div>
    <h4>Créditos</h4><p class="meta">Cada crédito lleva un rol, un nombre, si es una persona o una herramienta, y una nota opcional.</p>
    <div class="hi-credlist">${f.cred.map((c,i)=>`<div class="hi-cred" data-i="${i}"><select class="hi-c-rol" aria-label="Rol">${ROLES.map(r=>`<option value="${r[0]}" ${r[0]===c.rol?'selected':''}>${r[1]}</option>`).join('')}</select>
      <input class="hi-c-nom" type="text" value="${E(c.nombre)}" placeholder="Nombre" aria-label="Nombre"><select class="hi-c-tipo" aria-label="Tipo"><option value="persona" ${c.tipo==='persona'?'selected':''}>Persona</option><option value="herramienta" ${c.tipo==='herramienta'?'selected':''}>Herramienta</option></select>
      <input class="hi-c-nota" type="text" value="${E(c.nota)}" placeholder="Nota (opcional)" aria-label="Nota"><button class="chip" data-hi="quitar-cred" data-i="${i}" aria-label="Quitar crédito" title="Quitar crédito">✕</button></div>`).join('')||'<div class="meta">Todavía no hay créditos.</div>'}</div>
    <div class="hi-pills" style="margin-top:6px">${[['letra','＋ Letra'],['musica','＋ Música / melodía'],['arreglos','＋ Arreglos'],['mezcla','＋ Mezcla'],['asistencia','＋ Asistencia u otros']].map(([r,t])=>`<button class="chip" data-hi="add-cred" data-r="${r}">${t}</button>`).join('')}</div>
    <div class="hi-f" style="margin-top:12px"><label for="hi-f-nombre">Nombre de la copia</label><div class="hi-nombre"><input id="hi-f-nombre" type="text" value="${E(f.nombre||nombre(e.p).replace(/\.[^.]+$/,'')+'_etiquetado')}"><span class="meta hi-mono">${E(ext)}</span></div></div>
    <div class="hi-acts" style="margin-top:14px"><button class="chip pri" data-hi="simular" ${e.busy||!e.p||!e.plan?'disabled':''}>1. Simular plan</button>
      <button class="chip pri hi-go" data-hi="aplicar" ${puede&&!e.busy?'':'disabled'}>2. Aplicar en _etiquetados/</button><span class="meta hi-pista">${e.busy==='aplicando'?'Escribiendo y verificando…':e.busy==='simulando'?'Simulando…':puede?'Todo listo: el plan coincide con lo que ves.':'Simular no escribe nada. Para aplicar, simula primero y no cambies nada después.'}</span></div>
    <div id="hi-plan">${panelPlan(e)}</div><div id="hi-res">${panelRes(e)}</div></section>`}

/* ---- pintar y eventos ---- */
function pintar(el,e){
  leerForm(el,e);
  if(e.lyricsAuto&&!e.f.lyrics){const L=GM.lyrics(e.s.id)||'';if(L)e.f.lyrics=L}   // the manager's lyrics may load after the page opens
  el.innerHTML=`<p class="hi-lead">Mira primero qué lleva tu archivo, limpia lo ajeno y pon lo tuyo en una copia. El audio no cambia: se comprueba con su huella (sha256_audio). Nada sale de tu ordenador.</p>${cabecera(e)}<div class="hi-cols">${bloque1(e)}${bloque2(e)}</div>`}
async function inspeccionar(el,e,conSenal){
  if(!e.p)return;leerForm(el,e);e.busy='insp';e.sim=null;e.res=null;pintar(el,e);
  const [i,p]=await Promise.all([GM.api(ID,'inspeccionar',{p:e.p,senal:conSenal}).catch(()=>({ok:false,errores:['No se pudo hablar con el gestor.']})),
    GM.api(ID,'etiquetar',{p:e.p,poner:{},creditos:[],conservar:[],simular:true}).catch(()=>null)]);
  e.insp=i;e.plan=p&&p.ok?p.plan:null;e.cons=new Set();e.busy='';if(el.isConnected)pintar(el,e)}
async function simular(el,e){
  leerForm(el,e);e.busy='simulando';pintar(el,e);
  e.sim=await GM.api(ID,'etiquetar',cuerpo(e,true)).catch(()=>({ok:false,error:'No se pudo hablar con el gestor.'}));
  e.simKey=claveCambios(e);e.res=null;e.busy='';if(el.isConnected)pintar(el,e)}
async function aplicar(el,e){
  leerForm(el,e);
  if(!await GM.ui.ask('¿Crear la copia etiquetada?','Se creará una copia en _etiquetados/ con lo que has declarado. El original no se toca y el audio no cambia: si la verificación falla, no se entrega nada.','Crear copia'))return;
  e.busy='aplicando';pintar(el,e);
  e.res=await GM.api(ID,'etiquetar',Object.assign(cuerpo(e,false),{simular:false})).catch(()=>({ok:false,error:'No se pudo hablar con el gestor.'}));
  e.busy='';if(el.isConnected)pintar(el,e);
  if(e.res&&e.res.ok)GM.ui.toast('Copia creada: '+e.res.copia.p)}
function seccion(el,s){
  const e=estado(s);
  pintar(el,e);
  el.onchange=ev=>{const t=ev.target;
    if(t.id==='hi-sel'){leerForm(el,e);e.p=t.value;e.insp=null;e.plan=null;e.sim=null;e.res=null;e.cons=new Set();pintar(el,e);return}
    if(t.dataset&&t.dataset.k){leerForm(el,e);t.checked?e.cons.add(t.dataset.k):e.cons.delete(t.dataset.k);e.sim=null;e.res=null;pintar(el,e);return}};
  el.oninput=ev=>{if(ev.target.id==='hi-f-lyrics')e.lyricsAuto=false;leerForm(el,e);guardarBorrador(e);
    const go=el.querySelector('.hi-go');if(go){const ok=e.sim&&e.sim.ok&&e.sim.plan.puede_aplicarse&&e.simKey===claveCambios(e);go.disabled=!ok||!!e.busy}};
  el.onclick=async ev=>{
    const b=ev.target.closest('[data-hi]');if(!b||b.disabled)return;const k=b.dataset.hi;leerForm(el,e);
    if(k==='insp-senal')return inspeccionar(el,e,true);
    if(k==='insp')return inspeccionar(el,e,false);
    if(k==='simular')return simular(el,e);
    if(k==='aplicar')return aplicar(el,e);
    if(k==='reset'){e.f=defecto(e.s);e.lyricsAuto=true;e.cons=new Set();e.sim=null;e.res=null;guardarBorrador(e);return pintar(el,e)}
    if(k==='add-cred'){e.f.cred.push({rol:b.dataset.r,nombre:'',tipo:'persona',nota:''});e.sim=null;guardarBorrador(e);pintar(el,e);const n=el.querySelectorAll('.hi-c-nom');n.length&&n[n.length-1].focus();return}
    if(k==='quitar-cred'){e.f.cred.splice(+b.dataset.i,1);e.sim=null;guardarBorrador(e);return pintar(el,e)}
    if(k==='copiar'){try{await navigator.clipboard.writeText(b.dataset.v);GM.ui.toast('Copiado')}catch(x){GM.ui.toast('No se pudo copiar')}return}
    if(k==='abrir'){fetch('/api/abrir',{method:'POST',body:JSON.stringify({p:b.dataset.p})}).catch(()=>{});return}
    if(k==='ver-copia'){e.extra=b.dataset.p;e.p=e.extra;e.insp=null;e.plan=null;e.sim=null;e.res=null;e.cons=new Set();return inspeccionar(el,e,false)}}}

GM.register({id:ID,nav:{label:'Huella',icon:'🔎'},
  songSection:{title:'Huella · inspección y etiquetado',order:70,render(el,s){seccion(el,s)}},
  async render(el){el.innerHTML='<h1>Huella</h1><p class="meta">Cargando…</p>';await cargar();pintar(el)}});
})();
