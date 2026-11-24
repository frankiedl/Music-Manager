/* «huella» module: asks AudD (audio recognition) whether a master already sounds like a known song, BEFORE you publish it.
   - Menu section «Huella»: paste your own AudD token once (kept only in datos/modulos/huella/cuenta.json), choose songs, confirm, wait.
   - Per song it sends one 1-minute clip cut with ffmpeg from the middle of the song, and shows the matches (artist, title, link).
   - A match is a warning, not a verdict: it may be your own published version, a sample, or a false positive.
   Nothing is sent unless the user confirms in the dialog. Results are kept in resultados.json. */
(function(){
const ID='huella';
const E=s=>GM.ui.esc(s==null?'':String(s));
let EST=null,RES={},REG={},DEF={},SEL=new Set(),ABIERTO=null,EJEC=null;
const versiones=s=>(s.versions||[]).filter(v=>v&&v.p);
const esMaster=p=>/\/master\//i.test(p||'');
function fuente(s){const v=versiones(s),fin=GM.finalPath(s),M=v.filter(x=>esMaster(x.p));
  if(M.length){const f=M.find(x=>x.p===fin);return f?f.p:M[0].p}
  return fin||GM.bestVersion(s)||(v[0]&&v[0].p)||''}
const PH={autor:'Autor/a, quien firma la declaración',plataforma:'Dónde registraste la obra, por ejemplo SongProof',ref:'Referencia, número o enlace del registro',fecha:'Fecha del registro (AAAA-MM-DD)',letra_original:'Letras',musica_herr:'Herramienta de los arreglos de la música, por ejemplo SUNO',ia_max:'Máximo de IA en la obra, en %, por ejemplo 50',suno_ref:'Enlace o ID de la creación en SUNO',suno_plan:'Plan de SUNO al crearla',aportacion:'Qué aportas tú'};
function campo(attr,k,g){const ph=PH[k],d=DEF[k];
  if(k==='letra_original')return `<select data-${attr}="${k}" aria-label="Letras"><option value="">${attr==='rg'?'Letras: como en la declaración por defecto':'Letras: sin declarar'}</option><option value="si"${g[k]==='si'?' selected':''}>Las letras son textos originales del autor</option><option value="no"${g[k]==='no'?' selected':''}>Las letras no son originales</option></select>`;
  return `<input data-${attr}="${k}" placeholder="${E(attr==='rg'&&d?'Por defecto: '+d:ph)}" value="${E(g[k]||'')}" aria-label="${E(ph)}">`}
const nombre=p=>String(p||'').split('/').pop();

async function cargar(){
  try{EST=await GM.api(ID,'estado')}catch(e){EST={ok:false}}
  try{const r=await GM.api(ID,'resultados');RES=(r&&r.resultados)||{}}catch(e){RES={}}
  try{const r=await GM.api(ID,'registros');REG=(r&&r.registros)||{};DEF=(r&&r.defecto)||{}}catch(e){REG={};DEF={}}
}
function pastilla(r){
  if(!r)return '<span class="b">sin comprobar</span>';
  if(r.error)return `<span class="b warn" title="${E(r.error)}">no se pudo</span>`;
  if(!r.coincidencias.length)return '<span class="b ok">sin coincidencias</span>';
  return `<span class="b warn">coincide con ${r.coincidencias.length===1?'1 canción':r.coincidencias.length+' canciones'}</span>`}
function detalle(s,r){
  if(!r)return '';
  const q=encodeURIComponent(s.id),g=REG[s.id]||{},cfg=GM.cfg||{};
  const inf=(!r.error&&r.sha256)?`<div style="margin-top:10px;display:grid;gap:6px"><div class="meta">Declaración de autoría de esta obra. La escribes y la firmas tú, el documento no la verifica. Lo que dejes vacío se toma de la declaración por defecto.</div>${['autor','plataforma','ref','fecha','letra_original','musica_herr','ia_max','suno_ref','suno_plan','aportacion'].map(k=>campo('rg',k,g)).join('')}<div><button class="chip" data-rgsave="${E(s.id)}">Guardar estos datos</button> <a class="chip" href="/api/mod/${ID}/informe?id=${q}&lang=es" target="_blank" rel="noopener">Informe en español</a> <a class="chip" href="/api/mod/${ID}/informe?id=${q}&lang=en" target="_blank" rel="noopener">Report in English</a> <a class="chip pri" href="/api/mod/${ID}/dossier?id=${q}">Expediente completo (zip)</a></div></div>`:'';
  if(r.error)return `<div class="hf-det">${E(r.error)}</div>`;
  if(!r.coincidencias.length)return `<div class="hf-det">Comprobado el ${E(r.t)}. AudD no reconoce nada parecido. Eso no garantiza que nadie más tenga algo igual, solo que su catálogo no lo detecta.${inf}</div>`;
  return `<div class="hf-det">${r.coincidencias.map(c=>`<div><b>${E(c.artista)}, ${E(c.titulo)}</b>${c.album?' · álbum «'+E(c.album)+'»':''}${c.sello?' · '+E(c.sello):''}${c.fecha?' · '+E(c.fecha):''}${c.tc?' · suena como el minuto '+E(c.tc)+' de esa obra':''} ${c.link?`<a href="${E(c.link)}" target="_blank" rel="noopener">ver</a>`:''}</div>`).join('')}<div style="margin-top:6px">Puede ser una versión tuya ya publicada, un sample o un falso positivo. Escucha la coincidencia antes de decidir.${inf}</div></div>`}

function pintar(el){
  const L=GM.songs.map(s=>({s,p:fuente(s)})).filter(x=>x.p);
  const tok=EST&&EST.token;
  el.innerHTML=`<h1>Huella</h1><p class="lead">Comprueba si un máster ya suena a algo conocido antes de publicarlo. De cada canción se envía un fragmento de 1 minuto, de su parte central.</p>
  <div class="hu-flow"><div class="panel"><h2>Conecta tu cuenta de AudD</h2>
    ${tok?`<p class="meta">Token guardado en este ordenador. Nunca se muestra ni se sube a ningún sitio.</p><div class="hf-tok"><button class="chip" id="hf-borrar">Olvidar el token</button></div>`
        :`<p class="meta">Crea una cuenta en <b>dashboard.audd.io</b>, copia tu token y pégalo aquí. El servicio puede tener coste según tu plan. Mira sus tarifas en su web.</p><div class="hf-tok"><input type="password" id="hf-tok" placeholder="Token de AudD" autocomplete="off" aria-label="Token de AudD"><button class="chip pri" id="hf-guardar">Guardar</button></div>`}
    ${EST&&!EST.ffmpeg?'<p class="meta" style="color:var(--warn)">No encuentro ffmpeg: solo se pueden comprobar archivos de menos de 9 MB.</p>':''}
  </div>
  <div class="panel"><h2>Revisa la declaración</h2><p class="meta">Esta declaración irá, redactada con el título de cada obra, en el expediente de todas tus canciones, salvo lo que cambies en una concreta. La firmas tú bajo tu responsabilidad y el documento no la verifica. Se guarda solo en este ordenador.</p>
    <div style="display:grid;gap:6px">${['autor','plataforma','letra_original','musica_herr','ia_max','suno_plan','aportacion'].map(k=>campo('df',k,DEF)).join('')}<div><button class="chip pri" id="hf-defsave">Guardar declaración</button></div></div></div>
  <div class="panel"><h2>Elige canciones y comprueba</h2>
    ${L.length?'':'<p class="meta">Aún no hay canciones con audio.</p>'}
    <div id="hf-lista">${L.map(({s,p})=>`<div class="hf-row"><input type="checkbox" data-id="${E(s.id)}" ${SEL.has(String(s.id))?'checked':''} aria-label="Elegir ${E(GM.title(s))}"><div class="hf-t" data-ver="${E(s.id)}" style="cursor:pointer">${E(GM.title(s))}</div><div class="meta" title="${E(p)}">${E(nombre(p))}</div><div>${pastilla(RES[s.id])}</div></div>${ABIERTO===String(s.id)?detalle(s,RES[s.id]):''}`).join('')}</div>
    <div class="hf-tok" style="margin-top:12px"><button class="chip pri" id="hf-go" ${tok&&SEL.size&&!EJEC?'':'disabled'}>Comprobar ${SEL.size||''} ${SEL.size===1?'canción':'canciones'}</button><button class="chip" id="hf-todas">Elegir todas</button><span id="hf-prog" class="meta"></span></div>
    <div class="hf-bar" id="hf-bar" hidden><i></i></div>
  </div></div>`;
  el.querySelector('#hf-guardar')&&(el.querySelector('#hf-guardar').onclick=async()=>{
    const v=el.querySelector('#hf-tok').value;const r=await GM.api(ID,'token',{token:v}).catch(()=>({ok:false,error:'Error'}));
    if(!r.ok)return GM.ui.toast(r.error||'No se pudo guardar');await cargar();pintar(el);GM.ui.toast('Token guardado')});
  el.querySelector('#hf-borrar')&&(el.querySelector('#hf-borrar').onclick=async()=>{
    if(!await GM.ui.ask('¿Olvidar el token?','Se borra de este ordenador. Los resultados ya guardados se conservan.','Olvidar'))return;
    await GM.api(ID,'borrar_token',{});await cargar();pintar(el)});
  el.querySelectorAll('#hf-lista input[type=checkbox]').forEach(c=>c.onchange=()=>{const id=c.dataset.id;c.checked?SEL.add(id):SEL.delete(id);pintar(el)});
  el.querySelectorAll('[data-ver]').forEach(b=>b.onclick=()=>{ABIERTO=ABIERTO===b.dataset.ver?null:b.dataset.ver;pintar(el)});
  el.querySelector('#hf-todas').onclick=()=>{L.forEach(({s})=>SEL.add(String(s.id)));pintar(el)};
  el.querySelector('#hf-defsave').onclick=async()=>{const d={};el.querySelectorAll('[data-df]').forEach(i=>d[i.dataset.df]=i.value);const r=await GM.api(ID,'defecto',d).catch(()=>({ok:false}));if(r.ok){DEF=d;GM.ui.toast('Declaración guardada')}else GM.ui.toast('No se pudo guardar')};
  el.querySelectorAll('[data-rgsave]').forEach(b=>b.onclick=async()=>{const id=b.dataset.rgsave,d={id};el.querySelectorAll('[data-rg]').forEach(i=>d[i.dataset.rg]=i.value);
    const r=await GM.api(ID,'registro',d).catch(()=>({ok:false}));if(r.ok){REG[id]=d;GM.ui.toast('Datos guardados')}else GM.ui.toast('No se pudieron guardar')});
  el.querySelector('#hf-go').onclick=()=>lanzar(el,L);
}
async function lanzar(el,L){
  const items=L.filter(x=>SEL.has(String(x.s.id))).map(x=>({id:x.s.id,p:x.p,titulo:GM.title(x.s)}));if(!items.length)return;
  if(!await GM.ui.ask('¿Enviar fragmentos a AudD?',`Se enviarán a AudD (api.audd.io) un fragmento de 1 minuto de la parte central de ${items.length} ${items.length===1?'canción':'canciones'}, para saber si coinciden con alguna conocida. Los originales no se tocan. Esto puede consumir peticiones de tu plan de AudD.`,'Enviar'))return;
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

/* ---------- on each song: «Comprobar huella» (song page and song menu) ---------- */
async function cancion(s){
  await cargar();
  const o=GM.ui.modal('<div id="hf-modal" style="min-width:min(560px,86vw);display:grid;gap:10px"></div>'),box=o.querySelector('#hf-modal'),p=fuente(s),q=encodeURIComponent(s.id);
  const lista=r=>!r?'':r.error?`<p class="meta">${E(r.error)}</p>`:!r.coincidencias.length?`<p class="meta">Comprobado el ${E(r.t)}. AudD no reconoce nada parecido.</p>`
    :`<div>${r.coincidencias.map(c=>`<div><b>${E(c.artista)}, ${E(c.titulo)}</b>${c.album?' · álbum «'+E(c.album)+'»':''}${c.fecha?' · '+E(c.fecha):''}${c.tc?' · suena como el minuto '+E(c.tc)+' de esa obra':''} ${c.link?`<a href="${E(c.link)}" target="_blank" rel="noopener">ver</a>`:''}</div>`).join('')}<p class="meta">Puede ser una versión tuya ya publicada, un sample o un falso positivo.</p></div>`;
  const pinta=(extra)=>{const r=RES[s.id];
    box.innerHTML=`<h2>Huella de «${E(GM.title(s))}»</h2>`+
      (!p?'<p class="meta">Esta canción aún no tiene audio.</p>':
       !(EST&&EST.token)?'<p>Primero guarda tu token de AudD en el módulo Huella (menú, sección Módulos).</p><button class="chip pri" id="hf-ir">Ir a Huella</button>':
       `<p>${pastilla(r)}</p>${lista(r)}${extra||''}`+
       (r&&!r.error&&r.sha256?`<div><a class="chip" href="/api/mod/${ID}/informe?id=${q}&lang=es" target="_blank" rel="noopener">Informe en español</a> <a class="chip" href="/api/mod/${ID}/informe?id=${q}&lang=en" target="_blank" rel="noopener">Report in English</a> <a class="chip" href="/api/mod/${ID}/dossier?id=${q}">Expediente completo (zip)</a></div><p class="meta">Los datos de autoría y de SUNO del expediente se rellenan en el módulo Huella.</p>`:'')+
       `<p class="meta">Se enviarán a AudD (api.audd.io) un fragmento de 1 minuto de la parte central de ${E(nombre(p))}. Los originales no se tocan.</p><div><button class="chip pri" id="hf-m-go">${r?'Comprobar de nuevo':'Enviar y comprobar'}</button> <button class="chip" id="hf-m-x">Cerrar</button></div>`);
    const x=box.querySelector('#hf-m-x');if(x)x.onclick=()=>o.remove();
    const ir=box.querySelector('#hf-ir');if(ir)ir.onclick=()=>{o.remove();GM.ui.go('mod:'+ID)};
    const go=box.querySelector('#hf-m-go');if(go)go.onclick=async()=>{
      go.disabled=true;go.textContent='Comprobando…';
      const r=await GM.api(ID,'comprobar',{items:[{id:s.id,p,titulo:GM.title(s)}]}).catch(()=>({ok:false,error:'Error'}));
      if(!r.ok){GM.ui.toast(r.error||'No se pudo empezar');return pinta()}
      const t=setInterval(async()=>{const k=await GM.api(ID,'progreso?job='+r.job).catch(()=>null);
        if(!k||!k.ok){clearInterval(t);return pinta()}
        if(k.estado==='listo'){clearInterval(t);await cargar();if(o.isConnected)pinta()}},1000)}};
  pinta()}

GM.register({id:ID,nav:{label:'Huella',icon:'🔎'},songAction:{label:'Comprobar huella',icon:'🔎',run(s){cancion(s)}},
  async render(el){el.innerHTML='<h1>Huella</h1><p class="meta">Cargando…</p>';await cargar();pintar(el)}});
})();
