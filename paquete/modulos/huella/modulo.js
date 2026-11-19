/* «huella» module: asks AudD (audio recognition) whether a master already sounds like a known song, BEFORE you publish it.
   - Menu section «Huella»: paste your own AudD token once (kept only in datos/modulos/huella/cuenta.json), choose songs, confirm, wait.
   - Per song it sends three 12-second clips cut with ffmpeg (never the whole song), and shows the matches (artist, title, link).
   - A match is a warning, not a verdict: it may be your own published version, a sample, or a false positive.
   Nothing is sent unless the user confirms in the dialog. Results are kept in resultados.json. */
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

GM.register({id:ID,nav:{label:'Huella',icon:'🔎'},
  async render(el){el.innerHTML='<h1>Huella</h1><p class="meta">Cargando…</p>';await cargar();pintar(el)}});
})();
