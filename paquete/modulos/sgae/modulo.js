/* «sgae» module (PERSONAL, never in the public package). A separate browser window where YOU log in to the SGAE electronic office (SGAE e-mails you a
   one-time code; you type it there). The manager then reads your works from SGAE and can register new ones the same way its web form does.
   It never receives your password or the code, and it never reads your mailbox. Screen: tabs «Obras registradas», «En proceso», «Por registrar»;
   the recording of the SGAE web lives in «Configuración avanzada». */
(function(){
const ID='sgae',E=s=>GM.ui.esc(s==null?'':String(s));
const nr=x=>String(x||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9ñ]+/g,'');
const mmss=s=>s?Math.floor(s/60)+':'+String(s%60).padStart(2,'0'):'';
const fecha=f=>{f=String(f||'');return /^\d{8}$/.test(f)?f.slice(6)+'/'+f.slice(4,6)+'/'+f.slice(0,4):/^\d{4}-\d\d-\d\d/.test(f)?f.slice(8,10)+'/'+f.slice(5,7)+'/'+f.slice(0,4):''};
const regSgae=s=>((GM.state('derechos').reg||{})[s.id]||[]).find(e=>/sgae/i.test(e.soc));
const ERR={sin_sesion:'Todavía no tengo tu sesión: inicia sesión en la ventana de SGAE y pulsa Hecho.',sesion_caducada:'La sesión de SGAE ha caducado: vuelve a iniciar sesión en la ventana (te llegará un código nuevo al correo).',sin_plantilla:'Aún no conozco tus datos de autor. Registra una canción por la web de SGAE en esa ventana y el gestor los aprende.',duplicada:'Esa obra ya está en SGAE, validada o en proceso: no se vuelve a registrar.',ficheros:'No encuentro el audio o la letra de esa canción.',datos:'Faltan datos (título o duración).',tamano:'Algún fichero es demasiado grande.',rechazada:'SGAE ha rechazado el envío.',red:'No se pudo hablar con SGAE.'};
const S={tab:'reg',q:'',gen:'',alb:'',est:'todas',est_s:null,datos:null,prep:null,cargando:false,error:null,enviando:false,aviso:''};
let EL=null,timer=null;
async function api(r,b){try{return b===undefined?await GM.api(ID,r):await GM.api(ID,r,b)}catch(e){return {ok:false,error:String(e)}}}
try{S.tab=sessionStorage.getItem('sgae-tab')||'reg'}catch(e){}

/* ---------- data ---------- */
async function cargar(){
  S.cargando=true;S.error=null;cuerpo();
  const [c,p]=await Promise.all([api('comprobar'),api('preparadas')]);
  S.cargando=false;S.prep=p&&p.ok?p:null;
  if(c&&c.ok){S.datos=c;S.mem=false;S.ultima=c.ultima;avisarCambios(c.cambios);sincronizar(c)}else{if(!S.datos)S.error=c&&c.error||'red';else GM.ui.toast('No se pudo actualizar desde SGAE; se muestran los últimos datos guardados.')}
  cuerpo();cabecera()}
/* The manager's own list says «registered in SGAE» from an old spreadsheet. Here the songs are matched with what SGAE really has (the last read, kept in memory):
   validated → registered, in process → «pend». Titles are compared like the rest of this module (accents, case and symbols ignored; «(Acoustic)» stays different). */
function sincronizar(d){
  if(!d||!d.validadas||!GM.songs)return false;let cambio=false;
  const val=new Map(d.validadas.map(x=>[nr(x.titulo),x])),pen=new Map(d.pendientes.map(x=>[nr(x.titulo),x]));
  GM.songs.forEach(s=>{const k=nr(GM.title(s)),v=val.get(k),p=pen.get(k);let n=s.sgae||null;
    if(v){if(!n||n.pend||n.cod!==v.codigo&&!n.cod){n={cod:v.codigo,iswc:v.iswc,titulo:v.titulo};}}
    else if(p&&!n){n={cod:'',titulo:p.titulo,pend:true,rgo:p.rgo}}
    if(n!==(s.sgae||null)){s.sgae=n;cambio=true}});
  return cambio}
async function sincInicial(){const m=await api('memoria');if(m&&m.ok&&sincronizar(m)&&GM.refresh)GM.refresh()}
async function recordar(){const m=await api('memoria');if(m&&m.ok&&!S.datos){S.datos=m;S.mem=true;S.ultima=m.ultima}cuerpo();cabecera()}
function avisarCambios(c){if(!c)return;const n=[];if(c.validadas&&c.validadas.length)n.push(`${c.validadas.length} validada${c.validadas.length>1?'s':''}`);if(c.pendientes&&c.pendientes.length)n.push(`${c.pendientes.length} nueva${c.pendientes.length>1?'s':''} en proceso`);if(c.rechazadas&&c.rechazadas.length)n.push(`${c.rechazadas.length} rechazada${c.rechazadas.length>1?'s':''}`);
  GM.ui.toast(n.length?'SGAE ha cambiado: '+n.join(', '):'SGAE al día: sin cambios desde la última vez.')}
const cuando=t=>{const d=new Date(t);return isNaN(d)?'':d.toLocaleString('es-ES',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})};
function cabecera(){const ses=EL&&EL.querySelector('#sg-ses');if(!ses)return;
  ses.innerHTML=ULT.sesion?`<span>Sesión de SGAE activa${S.ultima?' · leído '+E(cuando(S.ultima)):''}</span><button class="chip" data-a="actualizar">Actualizar</button>`:(S.ultima?`<span>Datos guardados de SGAE · leído ${E(cuando(S.ultima))}. Sin sesión no se actualizan.</span>`:'')}
const dur=()=>{const m=new Map();((S.prep&&S.prep.items)||[]).forEach(x=>m.set(nr(x.sgae),x.segundos));return m};
const yaEnSgae=()=>new Set(S.datos?[...S.datos.validadas.map(x=>x.titulo),...S.datos.pendientes.map(x=>x.titulo)].map(nr):[]);

/* ---------- shell ---------- */
function pintar(el){
  EL=el;
  el.innerHTML=`<div class="sg"><div class="sg-head"><h1>SGAE</h1><div id="sg-ses" class="sg-ses"></div></div><div id="sg-guia"></div><div id="sg-cuerpo"></div>${avanzado()}</div>`;
  el.querySelector('#sg-adv').ontoggle=e=>{if(e.target.open)adv()};
  el.addEventListener('click',clic);el.addEventListener('input',entrada);
  estado(true);clearInterval(timer);timer=setInterval(()=>{if(!el.isConnected){clearInterval(timer);return}estado(false)},3000)}
let ULT={};
async function estado(primera){
  const s=await api('estado');if(!s||!s.ok||!EL)return;const antes=ULT.sesion;ULT=s;
  const ses=EL.querySelector('#sg-ses'),g=EL.querySelector('#sg-guia');if(!g)return;
  cabecera();
  if(!s.chrome)g.innerHTML=`<div class="sg-guia"><div><h2>No encuentro Chrome ni Edge</h2><p>El módulo necesita uno de los dos para abrir la ventana de SGAE.</p></div></div>`;
  else if(!s.abierto){if(!g.querySelector('[data-paso="1"]'))g.innerHTML=guia(1)}
  else if(!s.sesion){if(!g.querySelector('[data-paso="2"]'))g.innerHTML=guia(2)}
  else g.innerHTML='';
  if(s.sesion&&(!antes||primera)&&(!S.datos||S.mem)&&!S.cargando)cargar();
  if(!s.sesion&&primera){const p=await api('preparadas');S.prep=p&&p.ok?p:null;await recordar()}}
function guia(p,aviso){
  const pasos=`<ol class="sg-pasos"><li class="${p===1?'on':''}"><span class="n">1</span>Abrir la ventana</li><li class="${p===2?'on':''}"><span class="n">2</span>Iniciar sesión</li><li><span class="n">3</span>Ver tus obras</li></ol>`;
  return p===1?`<div class="sg-guia" data-paso="1"><div><h2>Abre la ventana de SGAE</h2><p>Se abre una ventana de Chrome aparte, con su propio perfil. La contraseña y el código del correo los escribes tú ahí; el gestor no los ve.</p>${pasos}<button class="chip pri" data-a="abrir">Abrir ventana de SGAE</button></div></div>`
   :`<div class="sg-guia" data-paso="2"><div><h2>Haz el login en la ventana de SGAE</h2><p>Escribe tu usuario y contraseña y después el código que SGAE te manda por correo. Cuando veas tu repertorio, vuelve aquí y pulsa Hecho.</p>${pasos}<button class="chip pri" data-a="hecho">Hecho</button><div class="aviso" id="sg-av">${E(aviso||'')}</div></div></div>`}

/* ---------- tabs + body ---------- */
function cuenta(){
  const d=S.datos,items=(S.prep&&S.prep.items)||[],ya=yaEnSgae();
  return {reg:d?d.validadas.length:null,pro:d?d.pendientes.length+d.rechazadas.length:null,por:d?items.filter(x=>!ya.has(nr(x.sgae))).length:null}}
function cuerpo(){
  const b=EL&&EL.querySelector('#sg-cuerpo');if(!b)return;const c=cuenta();
  const tab=(k,t)=>`<button class="sg-tab" role="tab" aria-selected="${S.tab===k}" data-tab="${k}">${t}<span class="c">${c[k]==null?'–':c[k]}</span></button>`;
  if(!S.datos&&!(ULT&&ULT.sesion)&&!S.cargando){b.innerHTML='';return}
  b.innerHTML=`<div class="sg-tabs" role="tablist">${tab('reg','Obras registradas')}${tab('pro','En proceso')}${tab('por','Por registrar')}</div><div id="sg-vista"></div>`;
  vista()}
function vista(){
  const v=EL.querySelector('#sg-vista');if(!v)return;
  if(S.tab==='por'){v.innerHTML=porRegistrar();return}
  if(!ULT.sesion){v.innerHTML=`<div class="sg-vacio"><b>Sin sesión de SGAE</b>Abre la ventana, inicia sesión y pulsa Hecho para ver tus obras.</div>`;return}
  if(S.cargando){v.innerHTML=esqueleto();return}
  if(S.error||!S.datos){v.innerHTML=`<div class="sg-vacio"><b>No se pudieron leer tus obras</b>${E(ERR[S.error]||'SGAE no respondió.')}<br><button class="chip pri" data-a="actualizar">Reintentar</button></div>`;return}
  v.innerHTML=S.tab==='reg'?registradas():enProceso()}
const esqueleto=()=>`<div class="sg-tabla">${Array.from({length:8},()=>`<div class="sg-fila sg-reg"><div class="sg-esq"></div><div class="sg-esq"></div><div class="sg-esq"></div><div class="sg-esq"></div><div class="sg-esq"></div><div class="sg-esq"></div></div>`).join('')}</div>`;
const barra=(extra,n,tot)=>`<div class="sg-bar"><input type="search" id="sg-q" placeholder="Buscar por título o código" value="${E(S.q)}" aria-label="Buscar">${extra}<span class="cuenta">${n} de ${tot}</span></div>`;
const coincide=(...c)=>{const q=nr(S.q);return !q||c.some(x=>nr(x).includes(q))};

function registradas(){
  const d=S.datos,gens=[...new Set(d.validadas.map(x=>x.genero||'').filter(Boolean))].sort();
  const L=d.validadas.filter(x=>(!S.gen||x.genero===S.gen)&&coincide(x.titulo,x.codigo,x.iswc)).sort((a,b)=>String(b.fecha).localeCompare(String(a.fecha)));
  const sel=`<select id="sg-gen" aria-label="Género"><option value="">Todos los géneros</option>${gens.map(g=>`<option${g===S.gen?' selected':''}>${E(g)}</option>`).join('')}</select>`;
  const apuntables=sinApuntar().length?`<div class="sg-aviso"><span>${sinApuntar().length} de tus altas no están anotadas en el gestor.</span><button class="chip pri" data-a="apuntar">Apuntarlas</button></div>`:'';
  const val=validables().length?`<div class="sg-aviso"><span>${validables().length} obras ya validadas por SGAE tienen aún su código provisional en el gestor.</span><button class="chip pri" data-a="definitivos">Apuntar los códigos definitivos</button></div>`:'';
  return val+apuntables+barra(sel,L.length,d.validadas.length)+`<div class="sg-tabla"><div class="sg-fila cab sg-reg"><div>Título</div><div>Código</div><div>ISWC</div><div>Género</div><div>Registro</div></div>
   ${L.slice(0,300).map(x=>`<div class="sg-fila sg-reg"><div class="tit">${E(x.titulo)}</div><div class="num">${E(x.codigo)}</div><div class="num">${E(x.iswc||'')}</div><div class="mut">${E(x.genero||'')}</div><div class="num">${fecha(x.fecha)}</div></div>`).join('')||vacio('No hay obras con ese filtro','Cambia la búsqueda o el género.')}</div>`}
function enProceso(){
  const d=S.datos,D=dur();
  let L=[...d.pendientes.map(x=>({...x,k:'pen'})),...d.rechazadas.map(x=>({...x,k:'mal'}))];
  L=L.filter(x=>(S.est==='todas'||S.est===x.k)&&coincide(x.titulo,x.rgo)).sort((a,b)=>String(b.rgo).localeCompare(String(a.rgo)));
  const seg=`<div class="sg-seg" role="group" aria-label="Estado">${[['todas','Todas'],['pen','En revisión'],['mal','Rechazadas']].map(([k,t])=>`<button data-est="${k}" aria-pressed="${S.est===k}">${t}</button>`).join('')}</div>`;
  return barra(seg,L.length,d.pendientes.length+d.rechazadas.length)+`<div class="sg-tabla"><div class="sg-fila cab sg-pro"><div>Título</div><div>Código provisional</div><div>Estado</div><div>Envío</div><div>Duración</div></div>
   ${L.map(x=>`<div class="sg-fila sg-pro"><div class="tit">${E(x.titulo)}</div><div class="num">${E(x.rgo)}</div><div class="${x.k==='mal'?'sg-est-mal':'sg-est-pen'}" title="${x.k==='mal'?E(x.motivo||''):''}">${x.k==='mal'?'Rechazada'+(x.motivo?': '+E(x.motivo):''):'En revisión'}</div><div class="num">${fecha(x.fecha)}</div><div class="num">${mmss(D.get(nr(x.titulo)))}</div></div>`).join('')||vacio('Nada en proceso','Las altas que envíes aparecen aquí hasta que SGAE las valide.')}</div>`}
function porRegistrar(){
  if(!S.prep)return `<div class="sg-vacio"><b>No se pudo leer la carpeta de altas</b>Comprueba que existe «SGAE-REGISTRO MUSICAL» en tu biblioteca.</div>`;
  if(!S.datos)return vacio('Primero inicia sesión en SGAE','Para saber qué falta por registrar hay que comprobar qué hay ya en SGAE. Abre la ventana, inicia sesión y pulsa Hecho.');
  const ya=yaEnSgae(),items=S.prep.items.filter(x=>!ya.has(nr(x.sgae)));
  const albs=[...new Set(items.map(x=>x.album))].sort();
  const L=items.filter(x=>(!S.alb||x.album===S.alb)&&coincide(x.sgae,x.titulo)).sort((a,b)=>a.album.localeCompare(b.album)||a.sgae.localeCompare(b.sgae));
  const sel=`<select id="sg-alb" aria-label="Álbum"><option value="">Todos los álbumes</option>${albs.map(a=>`<option${a===S.alb?' selected':''}>${E(a)}</option>`).join('')}</select>`;
  const lista=!ULT.sesion?'Inicia sesión en SGAE para poder registrar.':!S.prep.plantilla?ERR.sin_plantilla:!S.datos?'Pulsa Actualizar para comprobar qué hay ya en SGAE.':'';
  const aviso=lista?`<div class="sg-aviso"><span>${E(lista)}</span></div>`:'';
  const puede=!lista;
  return (S.enviando?'':'')+`<div id="sg-env-lugar"></div>`+aviso+barra(sel,L.length,items.length)+`<div class="sg-tabla"><div class="sg-fila cab sg-por"><div></div><div>Título</div><div>Duración</div><div>Álbum</div><div>Ficheros</div></div>
   ${L.map(x=>`<div class="sg-fila sg-por"><div><button class="chip pri" data-reg="${S.prep.items.indexOf(x)}"${puede&&x.letra?'':' disabled'}>Registrar</button></div><div class="tit">${E(x.sgae)}</div><div class="num">${mmss(x.segundos)}</div><div class="mut">${E(x.album)}</div><div class="${x.letra?'mut':'sg-est-mal'}">${x.letra?'Audio y letra':'Falta la letra'}</div></div>`).join('')||vacio('Todo registrado','No queda ninguna alta preparada sin enviar. Las nuevas aparecen cuando guardes su audio y su letra en «SGAE enviado».')}</div>`}
const vacio=(t,s)=>`<div class="sg-vacio"><b>${t}</b>${s}</div>`;

/* ---------- actions ---------- */
function sinApuntar(){return S.datos?S.datos.pendientes.map(p=>({p,s:GM.songs.filter(z=>!GM.isDraft(z)&&nr(GM.title(z))===nr(p.titulo))})).filter(x=>x.s.length===1&&!regSgae(x.s[0])):[]}
function validables(){if(!S.datos)return[];const val=new Map(S.datos.validadas.map(x=>[nr(x.titulo),x]));
  return GM.songs.map(s=>{const rg=regSgae(s);const v=rg&&/^RGO/.test(rg.cod)&&val.get(nr(GM.title(s)));return v?{s,rg,v}:null}).filter(Boolean)}
async function clic(ev){
  const t=ev.target.closest('[data-a],[data-tab],[data-est],[data-reg]');if(!t)return;
  if(t.dataset.tab){S.tab=t.dataset.tab;try{sessionStorage.setItem('sgae-tab',S.tab)}catch(e){}cuerpo();return}
  if(t.dataset.est){S.est=t.dataset.est;vista();return}
  if(t.dataset.reg!=null)return registrar(S.prep.items[+t.dataset.reg]);
  const a=t.dataset.a;
  if(a==='abrir'){t.disabled=true;t.textContent='Abriendo…';const r=await api('abrir',{});if(!r.ok)GM.ui.toast(r.error==='no_chrome'?'No encuentro Chrome ni Edge':'No se pudo abrir la ventana');ULT={};estado(true);return}
  if(a==='hecho'){t.disabled=true;t.textContent='Comprobando…';await api('refrescar',{});await new Promise(r=>setTimeout(r,6000));await estado(true);
    if(!ULT.sesion){const g=EL.querySelector('#sg-guia');g.innerHTML=guia(2,'Todavía no veo tu sesión. Entra en «Mi Repertorio» en la ventana de SGAE y pulsa Hecho otra vez.')}return}
  if(a==='actualizar'){await cargar();return}
  if(a==='apuntar'){let k=0;sinApuntar().forEach(x=>{if(window.DER&&DER.asignar&&DER.asignar(x.s[0],'SGAE',x.p.rgo,'Enviada a SGAE; pendiente de validar (código provisional)','env')==='nuevo')k++});GM.save();GM.ui.toast(k+' altas apuntadas');vista();return}
  if(a==='definitivos'){let k=0;validables().forEach(x=>{x.rg.notas='Validada por SGAE (antes '+x.rg.cod+')';x.rg.cod=x.v.codigo;x.rg.est='reg';const y=x.v.fecha||'';if(/^\d{8}$/.test(y))x.rg.fecha=y.slice(0,4)+'-'+y.slice(4,6)+'-'+y.slice(6);k++});GM.save();GM.ui.toast(k+' códigos apuntados');vista();return}
  if(a==='grabar'){const s=await api('estado');await api('grabar',{on:!s.grabando});adv();return}
  if(a==='vaciar'){await api('grabar',{limpiar:true,on:(await api('estado')).grabando});adv();return}
  if(a==='guardar'){const r=await api('guardar',{});GM.ui.toast(r.ok?`Guardadas ${r.n} peticiones en ${r.ruta}`:'No se pudo guardar');return}
  if(a==='cerrar'){await api('cerrar',{});S.datos=null;ULT={};estado(true);cuerpo();return}}
function entrada(ev){
  const t=ev.target;
  if(t.id==='sg-q'){S.q=t.value;const p=t.selectionStart;vista();const n=EL.querySelector('#sg-q');if(n){n.focus();n.setSelectionRange(p,p)}}
  else if(t.id==='sg-gen'){S.gen=t.value;vista()}
  else if(t.id==='sg-alb'){S.alb=t.value;vista()}}

async function registrar(x){
  if(S.enviando)return;
  const sim=await api('enviar',{mp3:x.mp3,letra:x.letra,simular:true});
  if(!sim.ok)return GM.ui.toast(ERR[sim.error]||('Error: '+sim.error));
  const m=sim.resumen;
  const ok=await GM.ui.ask('Registrar «'+m.titulo+'» en SGAE',`<div style="text-align:left"><div>Duración: <b>${mmss(m.segundos)}</b></div><div>Autor: <b>${E(m.autor||'')}</b>, ${E(m.reparto||'')}%</div><div>Intérprete: <b>${E((m.interprete||[]).join(', ')||'ninguno')}</b></div><div class="meta">${E(m.audio)}<br>${E(m.letra)}</div><p><b>Esto registra la obra en SGAE y no se puede deshacer.</b></p></div>`,'Registrar');
  if(!ok)return;
  S.enviando=true;EL.querySelectorAll('[data-reg]').forEach(b=>b.disabled=true);
  const lugar=EL.querySelector('#sg-env-lugar'),t0=Date.now();
  if(lugar)lugar.innerHTML=`<div class="sg-env" role="status"><span class="sg-sp"></span><b>Enviando «${E(m.titulo)}» a SGAE</b><span class="meta" id="sg-t">0 s. Sube el audio y la letra; puede tardar hasta un minuto. No cierres esta página.</span></div>`;
  const tm=setInterval(()=>{const q=EL.querySelector('#sg-t');if(q)q.textContent=Math.round((Date.now()-t0)/1000)+' s. Sube el audio y la letra; puede tardar hasta un minuto. No cierres esta página.'},1000);
  const r=await api('enviar',{mp3:x.mp3,letra:x.letra,titulo:m.titulo,segundos:m.segundos,confirmado:true});
  clearInterval(tm);S.enviando=false;
  if(!r.ok){GM.ui.toast(ERR[r.error]||('Error: '+r.error+(r.respuesta?', '+r.respuesta:'')));vista();return}
  GM.ui.toast('Registrada: '+r.caso);
  const s=GM.songs.filter(z=>nr(GM.title(z))===nr(x.titulo));
  if(s.length===1&&window.DER&&DER.asignar&&!regSgae(s[0])){DER.asignar(s[0],'SGAE',r.caso,'Enviada a SGAE desde el gestor; pendiente de validar (código provisional)','env');GM.save()}
  await cargar()}

/* ---------- advanced setup ---------- */
function avanzado(){return `<details class="sg-adv" id="sg-adv"><summary>Configuración avanzada</summary><div class="sg-adv-cuerpo" id="sg-adv-c"></div></details>`}
async function adv(){
  const c=EL.querySelector('#sg-adv-c');if(!c)return;const s=await api('estado');if(!s.ok){c.innerHTML='<p>No se pudo leer el estado.</p>';return}
  const cap=s.n?await api('captura'):{peticiones:[]};
  c.innerHTML=`<p>Datos de autor: ${s.plantilla?'aprendidos de tu última alta por la web de SGAE.':'pendientes; se aprenden la primera vez que registras una canción por la web en esa ventana.'}</p>
   <p>Grabar las peticiones que hace la web de SGAE sirve para estudiar cómo envía cada cosa. No se graban las de inicio de sesión ni los valores que parecen claves. Lo grabado se queda en tu ordenador.</p>
   <div class="sg-adv-btns"><button class="chip" data-a="grabar">${s.grabando?'Parar de grabar':'Empezar a grabar'}</button><button class="chip" data-a="vaciar">Vaciar</button><button class="chip" data-a="guardar">Guardar lo grabado</button><button class="chip" data-a="cerrar">Cerrar la ventana de SGAE</button></div>
   ${s.n?`<div>${s.n} peticiones grabadas${s.grabando?', grabando ahora':''}.</div>`:''}
   ${(cap.peticiones||[]).slice(-40).reverse().map(p=>`<details class="sg-peti"><summary><b>${E(p.metodo)}</b> ${E(p.url.replace(/^https?:\/\//,'').slice(0,100))} <span class="mut">${p.estado||''}</span></summary><div class="mut">Cabeceras: ${E((p.cabeceras||[]).join(', '))}</div>${p.cuerpo?`<pre>${E(p.cuerpo)}</pre>`:''}${p.formdata?`<pre>${E(JSON.stringify(p.formdata,null,1))}</pre>`:''}${p.respuesta?`<pre>${E(p.respuesta)}</pre>`:''}</details>`).join('')}`}

GM.register({id:ID,nav:{label:'SGAE',icon:'🏛'},render(el){pintar(el)}});
(function esp(n){if(GM.songs&&GM.songs.length)sincInicial();else if(n<20)setTimeout(()=>esp(n+1),500)})(0);
})();
