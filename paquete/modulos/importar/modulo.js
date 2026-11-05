/* Módulo «Importar»: asistente de 4 pasos para organizar música dispersa COPIÁNDOLA a la biblioteca (el origen no se toca). */
GM.register({
  id:'importar',
  render(el,GM){ IMP.montar(el,GM) },
});

const IMP=(()=>{
  const CATS=[['master','Máster','master/'],['version','Versión / mezcla','versiones/'],['directo','Directo','versiones/directos/'],['boceto','Boceto / idea','versiones/bocetos/'],
    ['toma','Toma','otros/tomas/'],['stem','Stem / pista','stems/'],['letra','Letra','letra.txt'],['doc','Documento','docs/'],['midi','MIDI','midi/'],
    ['arte','Imagen','arte/'],['video','Vídeo','video/'],['otro','Otro','otros/']];
  const CAT=Object.fromEntries(CATS.map(c=>[c[0],c]));
  const ICO={master:'🏅',version:'🎚',directo:'🎤',boceto:'✏️',toma:'🎙',stem:'🧩',letra:'📝',doc:'📄',midi:'🎹',arte:'🖼',video:'🎬',otro:'📦'};
  const S={paso:1,ruta:'',exp:null,expAbierto:false,job:null,scan:null,songs:[],filtro:'',presu:null,copia:null,hist:null,error:'',busy:false,sel:new Set()};
  let el=null,GMr=null,timer=null,tPresu=null;
  const E=s=>GMr.ui.esc(String(s==null?'':s));
  const fb=n=>{if(n==null)return '—';const u=['B','KB','MB','GB','TB'];let i=0;while(n>=1024&&i<4){n/=1024;i++}return (i<2?Math.round(n):n.toFixed(1))+' '+u[i]};
  const fd=s=>{if(s==null)return '';s=Math.round(s);return s>=3600?`${Math.floor(s/3600)}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`:`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`};
  const num=n=>Number(n||0).toLocaleString('es-ES');
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));

  function montar(e,GM){
    el=e;GMr=GM;
    if(!S.ruta){const st=GM.state('importar');if(st.ultimaRuta)S.ruta=st.ultimaRuta}
    if(!el._imp){el._imp=1}
    pintar(true);
    if(S.paso===1&&!S.hist)cargarHist();
  }

  /* ───────── piezas comunes ───────── */
  function pasos(){
    const N=['Elegir carpeta','Buscar','Revisar','Copiar'];
    return `<div class="imp-pasos">${N.map((n,i)=>{const k=i+1,cls=S.paso===k?'on':S.paso>k?'ok':'';
      const click=(k===1&&S.paso!==2&&!(S.paso===4&&(!S.copia||S.copia.estado==='corriendo')))?' click':'';
      return `<span class="imp-paso ${cls}${click}" ${click?`data-a="paso" data-n="${k}"`:''}><b>${S.paso>k?'✓':k}</b>${n}</span>`}).join('')}</div>`;
  }
  const vivo=()=>el&&el.firstElementChild&&el.firstElementChild.classList.contains('imp-root')&&document.body.contains(el);
  function pintar(forzar){
    if(!el||(!forzar&&!vivo()))return;   // si la persona ya está en otra sección, no pisamos su pantalla
    const cab=`<h1>Importar música</h1><p class="lead">Si tienes bocetos, versiones, tracks sueltos, grabaciones en directo y proyectos de tu programa de música repartidos por tus carpetas, aquí los ordenamos juntos. <b>Se copian a tu biblioteca; lo original no se toca.</b></p>${pasos()}`;
    let c='';
    if(S.paso===1)c=paso1();else if(S.paso===2)c=paso2();else if(S.paso===3)c=paso3();else c=paso4();
    el.innerHTML='<div class="imp-root">'+cab+c+'</div>';
    const r=el.firstElementChild;r.onclick=clic;r.onchange=cambia;r.oninput=entrada;
    if(S.paso===3)pintarEspacio();
  }

  /* ───────── paso 1: elegir carpeta ───────── */
  function paso1(){
    return `<div class="imp-seguro"><span class="ico">🛡</span><div><b>Sin riesgo para tu música.</b> Primero solo <b>miro</b> la carpeta que elijas (no abro ni cambio nada). Luego te enseño cómo la ordenaría y tú decides. Al final <b>copio</b> a tu biblioteca y compruebo que cada copia es idéntica. Tus archivos originales se quedan donde están, y si algo no te gusta puedes deshacer la importación.</div></div>
    <div class="panel"><h2 style="margin:0 0 4px">1 · ¿Dónde está tu música?</h2>
      <p class="meta" style="margin:0 0 12px">Escribe o pega la ruta de la carpeta, o búscala con el explorador. Puede estar en un disco externo o en Dropbox.</p>
      <div class="imp-fila"><input class="imp-ruta" id="imp-ruta" type="text" spellcheck="false" placeholder="Por ejemplo:  D:\\Mis proyectos de música   ·   /Users/yo/Música" value="${E(S.ruta)}">
        <button class="chip" data-a="explorar">📂 Buscar carpeta…</button></div>
      ${S.expAbierto?explorador():''}
      ${S.error?`<div class="callout" style="margin-top:14px">${E(S.error)}</div>`:''}
      <div class="imp-fila" style="margin-top:16px"><button class="chip pri imp-grande ${S.ruta.trim()?'':'imp-chip-off'}" data-a="escanear">Buscar canciones en esta carpeta →</button>
        <span class="meta">Con muchos archivos puede tardar unos minutos; verás el avance.</span></div></div>
    ${histHtml()}`;
  }
  function explorador(){
    const x=S.exp;
    if(!x)return `<div class="imp-exp"><span class="meta">Cargando…</span></div>`;
    if(!x.ok)return `<div class="imp-exp"><div class="callout" style="margin:0">${E(x.error)}</div><button class="chip" style="margin-top:10px" data-a="ir" data-r="">⌂ Volver al inicio</button></div>`;
    const migas=`<div class="imp-migas"><button data-a="ir" data-r="">🖥 Equipo</button>${(x.migas||[]).map(m=>`<span class="sep">›</span><button data-a="ir" data-r="${E(m.ruta)}">${E(m.n)}</button>`).join('')}</div>`;
    let lista='';
    if(!x.ruta){
      lista=`<div class="meta" style="margin:0 0 6px">Sitios habituales</div><div class="imp-lista">${(x.atajos||[]).map(a=>`<button class="u" data-a="ir" data-r="${E(a.ruta)}">⭐ <span class="n">${E(a.n)}</span></button>`).join('')}</div>
        <div class="meta" style="margin:12px 0 6px">Discos y unidades</div><div class="imp-lista">${(x.unidades||[]).map(a=>`<button class="u" data-a="ir" data-r="${E(a.ruta)}">💽 <span class="n">${E(a.n)}</span></button>`).join('')}</div>`;
    }else{
      lista=`<div class="imp-lista">${x.padre!=null?`<button class="u" data-a="ir" data-r="${E(x.padre)}">⬆ <span class="n">Subir un nivel</span></button>`:''}${(x.subcarpetas||[]).map(a=>`<button data-a="ir" data-r="${E(a.ruta)}" title="${E(a.n)}">📁 <span class="n">${E(a.n)}</span></button>`).join('')}</div>
        ${!(x.subcarpetas||[]).length?'<div class="meta" style="margin-top:8px">Esta carpeta no tiene subcarpetas.</div>':''}${x.truncado?'<div class="meta">Hay muchas carpetas; muestro las primeras 3000.</div>':''}`;
    }
    return `<div class="imp-exp">${migas}${lista}${x.ruta?`<div class="imp-elegir"><span class="meta" style="min-width:0;overflow:hidden;text-overflow:ellipsis">${E(x.ruta)}</span><button class="chip pri" data-a="elegir" data-r="${E(x.ruta)}">✔ Elegir esta carpeta</button></div>`:''}</div>`;
  }
  async function explorarIr(r){
    S.exp=null;pintar();
    S.exp=await GMr.api('importar','carpetas?ruta='+encodeURIComponent(r||'')).catch(()=>({ok:false,error:'No pude consultar las carpetas.'}));
    if(S.paso===1)pintar();
  }
  function histHtml(){
    const h=S.hist;if(!h||!h.length)return '';
    return `<div class="panel" style="margin-top:16px"><h2 style="margin:0 0 6px;font-size:17px">Importaciones anteriores</h2>${h.map(i=>`<div class="imp-hist"><div><b>${E(fechaTxt(i.ts))}</b> · desde «${E(i.origen)}»<div class="meta">${num(i.archivos)} archivos · ${fb(i.bytes)} · ${i.deshecha?`deshecha (${i.deshecho&&i.deshecho.borrados||0} archivos quitados${i.deshecho&&i.deshecho.conservados?`, ${i.deshecho.conservados} conservados`:''})`:E(i.estado)}</div></div>
      ${i.deshecha||!i.archivos?'':`<button class="chip" data-a="deshacer" data-id="${E(i.id)}">↩ Deshacer</button>`}</div>`).join('')}</div>`;
  }
  const fechaTxt=ts=>{try{return new Date(ts*1000).toLocaleString('es-ES',{dateStyle:'medium',timeStyle:'short'})}catch{return ''}};
  async function cargarHist(){const r=await GMr.api('importar','diario').catch(()=>null);S.hist=(r&&r.ok)?r.importaciones:[];if(S.paso===1&&el&&document.body.contains(el))pintar()}

  /* ───────── paso 2: escaneo ───────── */
  function paso2(){
    return `<div class="panel"><h2 style="margin:0 0 4px">2 · Buscando tus canciones…</h2>
      <p class="meta" style="margin:0 0 14px">Estoy leyendo <b>${E(S.ruta)}</b>. Solo miro nombres, tamaños y cabeceras; no cambio nada.</p>
      <div class="imp-barra indef"><i></i></div>
      <div class="imp-kpis"><div class="imp-kpi"><b id="imp-k1">0</b><span>carpetas vistas</span></div><div class="imp-kpi"><b id="imp-k2">0</b><span>archivos vistos</span></div><div class="imp-kpi"><b id="imp-k3">0 B</b><span>de contenido</span></div></div>
      <div class="imp-actual" id="imp-act"></div>
      <div class="imp-fila" style="margin-top:14px"><button class="chip" data-a="cancelar-scan">Cancelar</button></div></div>`;
  }
  async function escanear(){
    S.error='';
    const ruta=S.ruta.trim().replace(/^"|"$/g,'');
    S.busy=true;
    const r=await GMr.api('importar','escanear',{ruta}).catch(()=>({ok:false,error:'No pude hablar con el gestor.'}));
    S.busy=false;
    if(!r.ok){S.error=r.error;pintar();return}
    const st=GMr.state('importar');st.ultimaRuta=ruta;GMr.save();
    S.job=r.job;S.paso=2;pintar();sondeo('escaneo');
  }
  function sondeo(tipo){
    clearTimeout(timer);
    const tick=async()=>{
      const r=await GMr.api('importar','estado?job='+S.job).catch(()=>null);
      if(!r||!r.ok){S.error=(r&&r.error)||'Perdí la conexión con el gestor.';S.paso=1;pintar();return}
      if(tipo==='escaneo'){
        const g=id=>document.getElementById(id);
        if(g('imp-k1')){g('imp-k1').textContent=num(r.carpetas);g('imp-k2').textContent=num(r.archivos);g('imp-k3').textContent=fb(r.bytes);g('imp-act').textContent='📂 '+r.actual}
        if(r.estado==='corriendo'){timer=setTimeout(tick,500);return}
        if(r.estado==='listo')return alTerminarEscaneo();
        S.error=r.estado==='cancelado'?'Búsqueda cancelada.':('No pude leer la carpeta: '+(r.error||'error desconocido'));S.paso=1;pintar();
      }else{
        S.copia=r;pintarCopia();
        if(r.estado==='corriendo'){timer=setTimeout(tick,500);return}
        cargarHist();
      }
    };
    tick();
  }
  async function alTerminarEscaneo(){
    const r=await GMr.api('importar','propuesta?job='+S.job).catch(()=>null);
    if(!r||!r.ok){S.error=(r&&r.error)||'No pude recibir la propuesta.';S.paso=1;pintar();return}
    S.scan=r;
    S.songs=r.canciones.map(c=>({id:c.id,titulo:c.titulo,razon:c.razon,boceto:c.boceto,incl:!c.sueltos,abierta:false,todos:false,
      archivos:c.archivos.map(f=>({...f,incl:!f.excluir,sel:false})),
      sesiones:c.sesiones.map(s=>({...s,modo:s.tipo==='paquete'?'completa':'archivo',ligera:true}))}));
    S.sel=new Set();S.filtro='';S.presu=null;S.paso=3;pintar();pedirPresu();
  }

  /* ───────── paso 3: revisión ───────── */
  function catsChips(c){
    const n={};c.archivos.forEach(f=>{if(f.incl)n[f.cat]=(n[f.cat]||0)+1});
    return Object.keys(n).sort((a,b)=>CATS.findIndex(x=>x[0]===a)-CATS.findIndex(x=>x[0]===b)).map(k=>`<span class="imp-mini">${ICO[k]} ${n[k]} ${E(CAT[k][1].split(' ')[0].toLowerCase())}</span>`).join(' ');
  }
  function paso3(){
    const r=S.scan.resumen,nS=S.songs.filter(c=>c.incl).length;
    const f=S.filtro.trim().toLowerCase();
    const lista=S.songs.filter(c=>!f||c.titulo.toLowerCase().includes(f)||c.archivos.some(a=>a.nombre.toLowerCase().includes(f)));
    return `<div class="imp-top"><div class="panel"><div class="imp-esp" id="imp-esp"></div></div></div>
    <div class="panel" style="margin-bottom:12px"><h2 style="margin:0 0 4px">3 · Revisa la propuesta</h2>
      <p class="meta" style="margin:0 0 6px">Encontré <b>${num(r.archivos_propuestos)}</b> archivos de música y papeles${r.proyectos?`, <b>${r.proyectos}</b> proyecto${r.proyectos>1?'s':''} de programa de música`:''}; los he agrupado en <b>${S.songs.length}</b> canciones. Son <b>sugerencias</b>: debajo de cada cosa te digo por qué. Cambia lo que quieras: nombre, categoría, a qué canción va, o quítalo.</p>
      ${r.n_ignorados?`<div class="meta">No copiaré ${num(r.n_ignorados)} archivos de otro tipo (${r.ignorados.slice(0,6).map(i=>E(i.ext)+' ×'+i.n).join(', ')}…). ${r.basura?`Y ${num(r.basura)} archivos temporales o de caché.`:''}</div>`:''}
      ${r.enlaces_omitidos?`<div class="meta">${r.enlaces_omitidos} enlaces/accesos directos se han saltado (no los sigo).</div>`:''}
      ${S.scan.resumen&&(S.scan.resumen.archivos_vistos>r.archivos_propuestos+r.n_ignorados+r.basura)?`<div class="meta">Los archivos internos de los proyectos (samples, audio dentro de la sesión…) no se listan uno a uno: viajan con «la sesión completa» si la marcas.</div>`:''}
    </div>
    <div class="imp-herr"><input class="imp-buscar" id="imp-filtro" placeholder="🔎 Buscar canción o archivo" value="${E(S.filtro)}">
      <button class="chip" data-a="todo-abrir">Abrir todas</button><button class="chip" data-a="todo-cerrar">Cerrar todas</button>
      <button class="chip" data-a="fundir" ${S.sel.size>1?'':'disabled style="opacity:.5"'}>🔗 Fundir ${S.sel.size>1?S.sel.size:''} marcadas en una</button>
      <button class="chip" data-a="nueva">＋ Canción vacía</button>
      <span class="meta" style="margin-left:auto">${nS} de ${S.songs.length} canciones se importarán</span></div>
    ${lista.length?lista.map(songHtml).join(''):'<div class="empty">No hay canciones que coincidan.</div>'}
    <div class="imp-fila" style="margin:18px 0 40px"><button class="chip" data-a="paso" data-n="1">← Elegir otra carpeta</button>
      <button class="chip pri imp-grande" data-a="copiar" id="imp-copiar">Copiar a mi biblioteca →</button></div>`;
  }
  function destDe(c){return 'unreleased/'+(c.titulo.trim()||'Sin título')+'/'}
  function songHtml(c){
    const nf=c.archivos.filter(a=>a.incl).length,bytes=c.archivos.filter(a=>a.incl).reduce((s,a)=>s+a.tam,0);
    let cuerpo='';
    if(c.abierta){
      const otros=S.songs.filter(x=>x!==c);
      const marcados=c.archivos.filter(a=>a.sel).length;
      const lim=c.todos?1e9:300;
      cuerpo=`<div class="imp-sb">${c.razon.length?`<div class="imp-razon">💡 <b>Por qué esta canción:</b> ${c.razon.map(E).join(' · ')}</div>`:''}
        <div class="imp-dest">→ ${E(destDe(c))}…</div>
        ${c.sesiones.map(s=>sesHtml(c,s)).join('')}
        ${c.archivos.length?`<div class="imp-bulk"><label><input type="checkbox" data-a="selall" data-c="${c.id}"> Marcar todos</label>
          <select data-a="bulk" data-c="${c.id}"><option value="">${marcados?`Mover los ${marcados} marcados a…`:'Marca archivos para moverlos a otra canción…'}</option><option value="__nueva">➕ Una canción nueva</option>${otros.map(o=>`<option value="${o.id}">${E(o.titulo)}</option>`).join('')}</select>
          <select data-a="bulkcat" data-c="${c.id}"><option value="">Cambiar categoría de los marcados…</option>${CATS.map(k=>`<option value="${k[0]}">${k[1]}</option>`).join('')}</select>
          <button class="chip" data-a="bulkquitar" data-c="${c.id}">Quitar los marcados</button></div>`:''}
        ${c.archivos.slice(0,lim).map(a=>filaHtml(c,a,otros)).join('')}
        ${c.archivos.length>lim?`<button class="imp-mas" data-a="mas" data-c="${c.id}">Mostrar los ${c.archivos.length-lim} restantes…</button>`:''}</div>`;
    }
    return `<div class="imp-song ${c.incl?'':'off'}" data-c="${c.id}"><div class="imp-sh">
      <input type="checkbox" data-a="sel" data-c="${c.id}" title="Marcar para fundir con otras" ${S.sel.has(c.id)?'checked':''}>
      <input class="imp-tit" data-a="titulo" data-c="${c.id}" value="${E(c.titulo)}" title="Puedes cambiar el nombre de la canción">
      ${c.boceto?`<span class="imp-mini b" title="Se marcará como boceto en el gestor al terminar">✏️ boceto</span>`:''}
      ${c.sesiones.map(s=>`<span class="imp-mini" title="${E(s.nombre)}">🎛 ${E(s.daw)}</span>`).join(' ')}
      ${catsChips(c)}<span class="imp-mini">${nf} archivos · ${fb(bytes)}</span>
      <label class="meta" style="display:flex;gap:5px;align-items:center;cursor:pointer"><input type="checkbox" data-a="boc" data-c="${c.id}" ${c.boceto?'checked':''}> es un boceto</label>
      <label class="meta" style="display:flex;gap:5px;align-items:center;cursor:pointer"><input type="checkbox" data-a="incl" data-c="${c.id}" ${c.incl?'checked':''}> importar</label>
      <button class="imp-abrir" data-a="abrir" data-c="${c.id}" title="${c.abierta?'Cerrar':'Ver el detalle'}">${c.abierta?'▲':'▼'}</button></div>${cuerpo}</div>`;
  }
  function filaHtml(c,a,otros){
    return `<div class="imp-fila-f ${a.incl?'':'off'}" data-f="${a.id}"><input type="checkbox" data-a="fsel" data-c="${c.id}" data-f="${a.id}" ${a.sel?'checked':''} title="Marcar (para mover varios a la vez)">
      <div class="nom" title="${E(a.rel)}">${ICO[a.cat]||''} ${E(a.nombre)}</div>
      <select data-a="cat" data-c="${c.id}" data-f="${a.id}">${CATS.map(k=>`<option value="${k[0]}" ${k[0]===a.cat?'selected':''}>${ICO[k[0]]} ${k[1]}</option>`).join('')}</select>
      <select data-a="mover" data-c="${c.id}" data-f="${a.id}"><option value="">Mover a otra canción…</option><option value="__nueva">➕ Canción nueva</option>${otros.map(o=>`<option value="${o.id}">${E(o.titulo)}</option>`).join('')}</select>
      <div class="sub"><span class="dat">${fb(a.tam)}${a.dur!=null?' · '+(a.est?'≈':'')+fd(a.dur):''}</span> · <label style="cursor:pointer"><input type="checkbox" data-a="fincl" data-c="${c.id}" data-f="${a.id}" ${a.incl?'checked':''}> incluir</label>
        · <i>${E(a.motivo)}</i>${a.porque?` · <i>canción: ${E(a.porque)}</i>`:''}${a.dup?` · <span class="imp-aviso">parece copia exacta de «${E(a.dup)}» (mismo nombre y tamaño), la dejo sin marcar</span>`:''}</div></div>`;
  }
  function sesHtml(c,s){
    const pesa=s.tam>=1024**3;
    const arc=s.tipo==='paquete';
    return `<div class="imp-ses"><h4>🎛 Proyecto de ${E(s.daw)}: ${E(s.principales.join(', '))}</h4>
      <div class="meta">${E(s.porque)}. Contiene ${num(s.n)} archivos (${fb(s.tam)})${s.n_audio?`, ${num(s.n_audio)} audios internos`:''}.</div>
      ${arc?`<label><input type="radio" name="ses-${c.id}-${s.id}" data-a="ses" data-c="${c.id}" data-s="${s.id}" value="completa" ${s.modo==='completa'?'checked':''}> Copiar el proyecto (es una sola «carpeta-archivo»; sin ella la sesión no abre)</label>`
      :`<label><input type="radio" name="ses-${c.id}-${s.id}" data-a="ses" data-c="${c.id}" data-s="${s.id}" value="archivo" ${s.modo==='archivo'?'checked':''}> Solo el archivo del proyecto (ligero)</label>
        ${s.tipo==='carpeta'?`<label><input type="radio" name="ses-${c.id}-${s.id}" data-a="ses" data-c="${c.id}" data-s="${s.id}" value="completa" ${s.modo==='completa'?'checked':''}> Copiar también <b>la sesión completa del programa</b> (con sus audios, samples…) · ${fb(s.ligera?s.tam_ligero:s.tam)}</label>`:'<div class="meta">Está suelto, sin carpeta propia: solo puedo copiar este archivo.</div>'}`}
      <label><input type="radio" name="ses-${c.id}-${s.id}" data-a="ses" data-c="${c.id}" data-s="${s.id}" value="no" ${s.modo==='no'?'checked':''}> No copiar la sesión</label>
      ${s.modo==='completa'?`<label style="margin-left:22px"><input type="checkbox" data-a="ligera" data-c="${c.id}" data-s="${s.id}" ${s.ligera?'checked':''}> Omitir carpetas Freeze, Backup y cachés (ahorra ${fb(s.tam-s.tam_ligero)})</label>`:''}
      ${s.modo==='completa'&&pesa?`<div class="imp-aviso">⚠ Esta sesión pesa ${fb(s.ligera?s.tam_ligero:s.tam)}. Asegúrate de tener sitio (arriba verás el espacio).</div>`:''}</div>`;
  }

  /* plan que se envía al servidor */
  function plan(){
    return {job:S.job,canciones:S.songs.filter(c=>c.incl).map(c=>({titulo:c.titulo.trim()||'Sin título',boceto:c.boceto,
      archivos:c.archivos.filter(a=>a.incl).map(a=>({id:a.id,cat:a.cat,nombre:a.nombre})),
      sesiones:c.sesiones.filter(s=>s.modo!=='no').map(s=>({id:s.id,modo:s.modo,ligera:s.ligera}))})).filter(c=>c.archivos.length||c.sesiones.length)};
  }
  function pedirPresu(){
    clearTimeout(tPresu);
    tPresu=setTimeout(async()=>{
      const r=await GMr.api('importar','presupuesto',plan()).catch(()=>null);
      S.presu=r&&r.ok?r:null;pintarEspacio();
    },350);
  }
  function pintarEspacio(){
    const b=document.getElementById('imp-esp');if(!b)return;
    const p=S.presu;
    if(!p){b.innerHTML='<span class="t meta">Calculando el espacio necesario…</span>';return}
    const necesario=p.bytes,libre=p.libre,pct=libre?Math.min(100,necesario/libre*100):0;
    b.classList.toggle('mal',!p.cabe);
    b.innerHTML=`<span class="t"><b>Se copiarán ${num(p.archivos)} archivos en ${p.canciones} canciones</b> · hacen falta <b>${fb(necesario)}</b> · libre en tu biblioteca: <b>${fb(libre)}</b></span><div class="imp-barra"><i style="width:${pct}%"></i></div>
      <span class="t ${p.cabe?'':'mal'}">${p.cabe?'✔ Cabe':'⚠ No cabe: quita sesiones completas o libera espacio'}</span>`;
    const bt=document.getElementById('imp-copiar');
    if(bt){bt.disabled=!p.cabe||!p.archivos;bt.style.opacity=bt.disabled?.45:1}
  }

  /* ───────── paso 4: copiar ───────── */
  function paso4(){
    const c=S.copia;
    if(!c)return `<div class="panel"><h2 style="margin:0">4 · Preparando la copia…</h2></div>`;
    if(c.estado==='corriendo')return `<div class="panel"><h2 style="margin:0 0 4px">4 · Copiando y comprobando…</h2>
      <p class="meta" style="margin:0 0 14px">Cada archivo se copia, se vuelve a leer y se compara con el original antes de darlo por bueno. No cierres el gestor mientras tanto.</p>
      <div class="imp-barra"><i id="imp-pb" style="width:0%"></i></div>
      <div class="imp-kpis"><div class="imp-kpi"><b id="imp-c1">0</b><span id="imp-c1t">archivos</span></div><div class="imp-kpi"><b id="imp-c2">0 B</b><span id="imp-c2t">copiados</span></div><div class="imp-kpi"><b id="imp-c3">—</b><span>tiempo restante aprox.</span></div><div class="imp-kpi"><b id="imp-c4">0</b><span>omitidos / avisos</span></div></div>
      <div class="imp-actual" id="imp-cact"></div>
      <div class="imp-fila" style="margin-top:14px"><button class="chip" data-a="cancelar-copia">Cancelar (lo ya copiado se queda y se puede deshacer)</button></div></div>`;
    return resumenHtml(c);
  }
  function pintarCopia(){
    const c=S.copia;if(!c)return;
    if(c.estado!=='corriendo'){S.paso=4;pintar();return}
    const g=id=>document.getElementById(id);
    if(!g('imp-pb')){pintar();return}
    const pct=c.bytes_total?Math.min(100,c.bytes_hechos/c.bytes_total*100):(c.archivos_total?c.archivos_hechos/c.archivos_total*100:0);
    g('imp-pb').style.width=pct.toFixed(1)+'%';
    g('imp-c1').textContent=`${num(c.archivos_hechos)} / ${num(c.archivos_total)}`;
    g('imp-c2').textContent=`${fb(c.bytes_hechos)} / ${fb(c.bytes_total)}`;
    const v=c.bytes_hechos/Math.max(c.seg,1);g('imp-c3').textContent=c.bytes_hechos>0&&v>0?fd((c.bytes_total-c.bytes_hechos)/v):'—';
    g('imp-c4').textContent=`${c.omitidos} / ${c.n_avisos}`;
    g('imp-cact').textContent=c.actual?`${c.actual_fase==='verificando'?'🔍 Verificando':'📄 Copiando'}: ${c.actual}${c.actual_fase&&!['verificando','copiando'].includes(c.actual_fase)?' ('+c.actual_fase+')':''}`:c.fase;
  }
  function resumenHtml(c){
    const r=c.resumen||{},ok=c.estado==='listo',can=c.estado==='cancelado';
    const cs=r.canciones||[];
    return `<div class="panel imp-res"><h2>${ok?'✅ Importación terminada':can?'⏹ Importación cancelada':'⚠ La importación se detuvo'}</h2>
      ${c.error?`<div class="callout">${E(c.error)}</div>`:''}
      <div class="imp-kpis"><div class="imp-kpi"><b>${num(r.copiados)}</b><span>archivos copiados y verificados</span></div><div class="imp-kpi"><b>${fb(r.bytes)}</b><span>copiados</span></div>
        <div class="imp-kpi"><b>${cs.length}</b><span>canciones nuevas</span></div><div class="imp-kpi"><b>${num((r.omitidos||0))}</b><span>omitidos</span></div></div>
      <p class="meta">Verificación: ${num(r.verificacion_completa)} archivos comparados <b>byte a byte (huella SHA-256 completa)</b>${r.verificacion_muestreo?` y ${num(r.verificacion_muestreo)} archivos enormes (más de ${fb(r.limite_completo)}) comparados por <b>muestreo</b> (tamaño exacto + principio, final y 32 trozos repartidos)`:''}. Tus carpetas de origen no se han tocado.</p>
      ${(r.bloqueados||[]).length?`<div class="callout"><b>${r.bloqueados.length} archivos estaban bloqueados</b> (otro programa los estaba usando) y los dejé sin copiar. Ciérralos y vuelve a importar solo esos:<ul>${r.bloqueados.slice(0,15).map(n=>`<li>${E(n)}</li>`).join('')}</ul></div>`:''}
      ${(r.fallidos||[]).length?`<div class="callout"><b>${r.fallidos.length} archivos no se pudieron copiar:</b><ul>${r.fallidos.slice(0,15).map(f=>`<li>${E(f.n)} — ${E(f.error)}</li>`).join('')}</ul></div>`:''}
      ${cs.length?`<h3 style="margin:16px 0 4px;font-size:15px">Canciones creadas en tu biblioteca</h3><div class="imp-lista-c" id="imp-nuevas">${cs.map(x=>`<a data-a="ver-cancion" data-d="${E(x.carpeta)}"><span>${x.boceto?'✏️ ':'🎵 '}${E(x.carpeta.split('/').pop())}</span><span class="meta">${x.archivos} archivos</span></a>`).join('')}</div>`:''}
      ${c.avisos&&c.avisos.length?`<details class="imp-det"><summary>Avisos (${c.n_avisos})</summary><ul>${c.avisos.map(a=>`<li>${E(a)}</li>`).join('')}</ul></details>`:''}
      <div class="imp-fila" style="margin-top:16px">
        ${cs.length&&!S.actualizada?`<button class="chip pri imp-grande" data-a="actualizar">🔄 Actualizar la biblioteca</button>`:''}
        ${S.actualizada?`<button class="chip pri imp-grande" data-a="ver-nuevas">🎵 Ver las canciones nuevas</button>`:''}
        ${cs.length&&!S.deshecha?`<button class="chip" data-a="deshacer" data-id="${E(r.import_id)}">↩ Deshacer esta importación</button>`:''}
        <button class="chip" data-a="otra">Importar otra carpeta</button></div>
      ${S.actualizada?`<p class="meta" style="margin-top:10px">✔ Biblioteca actualizada${S.nBocetos?` · ${S.nBocetos} canción${S.nBocetos>1?'es':''} marcada${S.nBocetos>1?'s':''} como boceto`:''}. Pulsa en una canción de la lista para abrirla.</p>`:cs.length?`<p class="meta" style="margin-top:10px">Pulsa «Actualizar la biblioteca» para que el gestor lea las carpetas nuevas.</p>`:''}
      ${S.deshecha?`<div class="callout" style="margin-top:12px">↩ ${E(S.deshecha)}</div>`:''}</div>`;
  }

  async function copiar(){
    const p=plan();
    if(!p.canciones.length)return GMr.ui.toast('No hay nada que importar: marca alguna canción.');
    const ok=await GMr.ui.ask('¿Copiar a tu biblioteca?',`Voy a copiar <b>${num(S.presu&&S.presu.archivos||0)}</b> archivos (${fb(S.presu&&S.presu.bytes)}) en <b>${p.canciones.length}</b> canciones nuevas dentro de <b>unreleased</b>. No se sobrescribe nada y tus carpetas originales no se tocan.`,'Copiar');
    if(!ok)return;
    const r=await GMr.api('importar','copiar',p).catch(()=>({ok:false,error:'No pude hablar con el gestor.'}));
    if(!r.ok)return GMr.ui.toast(r.error||'No se pudo empezar');
    S.job=r.job;S.paso=4;S.copia=null;S.actualizada=false;S.deshecha='';S.nBocetos=0;pintar();sondeo('copia');
  }

  /* ───────── acciones ───────── */
  const song=id=>S.songs.find(c=>c.id===id);
  async function clic(ev){
    const t=ev.target.closest('[data-a]');if(!t)return;
    const a=t.dataset.a;
    if(['sel','titulo','boc','incl','fsel','fincl','cat','mover','ses','ligera','bulk','bulkcat','selall'].includes(a))return; // los maneja «cambia»
    ev.preventDefault?.();
    if(a==='paso'){S.paso=+t.dataset.n;S.error='';if(S.paso===1&&!S.hist)cargarHist();pintar()}
    else if(a==='explorar'){S.expAbierto=!S.expAbierto;pintar();if(S.expAbierto&&!S.exp)explorarIr(S.ruta.trim()&&!S.ruta.includes('..')?S.ruta.trim():'')}
    else if(a==='ir')explorarIr(t.dataset.r);
    else if(a==='elegir'){S.ruta=t.dataset.r;S.expAbierto=false;S.error='';pintar()}
    else if(a==='escanear'){if(S.ruta.trim()&&!S.busy)escanear()}
    else if(a==='cancelar-scan'){await GMr.api('importar','cancelar?job='+S.job,{});}
    else if(a==='cancelar-copia'){if(await GMr.ui.ask('¿Cancelar la copia?','Lo que ya se copió se queda en tu biblioteca (podrás deshacerlo). El archivo que se esté copiando ahora se descarta.','Sí, cancelar'))await GMr.api('importar','cancelar?job='+S.job,{})}
    else if(a==='abrir'){const c=song(t.dataset.c);c.abierta=!c.abierta;pintar()}
    else if(a==='todo-abrir'){S.songs.forEach(c=>c.abierta=S.songs.length<80);if(S.songs.length>=80)GMr.ui.toast('Son muchas canciones: ábrelas de una en una.');pintar()}
    else if(a==='todo-cerrar'){S.songs.forEach(c=>c.abierta=false);pintar()}
    else if(a==='mas'){song(t.dataset.c).todos=true;pintar()}
    else if(a==='nueva'){const id='n'+Date.now();S.songs.unshift({id,titulo:'Canción nueva',razon:['la creaste tú'],boceto:false,incl:true,abierta:true,archivos:[],sesiones:[],todos:false});pintar()}
    else if(a==='fundir')fundir();
    else if(a==='bulkquitar'){const c=song(t.dataset.c);c.archivos.forEach(f=>{if(f.sel){f.incl=false;f.sel=false}});pintar();pedirPresu()}
    else if(a==='copiar')copiar();
    else if(a==='actualizar')actualizar();
    else if(a==='ver-nuevas'){GMr.ui.go('songs')}
    else if(a==='ver-cancion'){const s=GMr.all.find(x=>x.dir===t.dataset.d);if(s)GMr.ui.go('song',s.id);else GMr.ui.toast('Primero pulsa «Actualizar la biblioteca».')}
    else if(a==='otra'){S.paso=1;S.scan=null;S.songs=[];S.copia=null;S.hist=null;S.error='';cargarHist();pintar()}
    else if(a==='deshacer')deshacer(t.dataset.id);
  }
  function cambia(ev){
    const t=ev.target;const a=t.dataset&&t.dataset.a;if(!a)return;
    const c=t.dataset.c?song(t.dataset.c):null;
    if(a==='titulo'){c.titulo=t.value.trim()||'Sin título';pintar();return}
    if(a==='sel'){t.checked?S.sel.add(c.id):S.sel.delete(c.id);pintar();return}
    if(a==='boc'){c.boceto=t.checked;pintar();return}
    if(a==='incl'){c.incl=t.checked;pintar();pedirPresu();return}
    if(a==='fsel'){c.archivos.find(f=>f.id===t.dataset.f).sel=t.checked;pintar();return}
    if(a==='selall'){c.archivos.forEach(f=>f.sel=t.checked);pintar();return}
    if(a==='fincl'){c.archivos.find(f=>f.id===t.dataset.f).incl=t.checked;pintar();pedirPresu();return}
    if(a==='cat'){c.archivos.find(f=>f.id===t.dataset.f).cat=t.value;pintar();return}
    if(a==='ses'){c.sesiones.find(s=>s.id===t.dataset.s).modo=t.value;pintar();pedirPresu();return}
    if(a==='ligera'){c.sesiones.find(s=>s.id===t.dataset.s).ligera=t.checked;pintar();pedirPresu();return}
    if(a==='mover'&&t.value){mover(c,[t.dataset.f],t.value);return}
    if(a==='bulk'&&t.value){const ids=c.archivos.filter(f=>f.sel).map(f=>f.id);if(!ids.length){GMr.ui.toast('Marca primero los archivos con su casilla.');pintar();return}mover(c,ids,t.value);return}
    if(a==='bulkcat'&&t.value){c.archivos.forEach(f=>{if(f.sel)f.cat=t.value});pintar();return}
  }
  function entrada(ev){
    const t=ev.target;
    if(t.id==='imp-ruta'){S.ruta=t.value;const b=el.querySelector('[data-a="escanear"]');if(b)b.classList.toggle('imp-chip-off',!S.ruta.trim())}
    else if(t.id==='imp-filtro'){S.filtro=t.value;clearTimeout(entrada.t);entrada.t=setTimeout(()=>{const pos=t.selectionStart;pintar();const n=document.getElementById('imp-filtro');if(n){n.focus();n.setSelectionRange(pos,pos)}},250)}
  }
  function mover(c,ids,destino){
    let d;
    if(destino==='__nueva'){
      const f0=c.archivos.find(f=>f.id===ids[0]);
      d={id:'n'+Date.now(),titulo:(f0?f0.nombre.replace(/\.[^.]+$/,''):'Canción nueva'),razon:['la separaste tú de «'+c.titulo+'»'],boceto:false,incl:true,abierta:true,archivos:[],sesiones:[],todos:false};
      S.songs.splice(S.songs.indexOf(c)+1,0,d);
    }else d=song(destino);
    ids.forEach(id=>{const i=c.archivos.findIndex(f=>f.id===id);if(i>=0){const [f]=c.archivos.splice(i,1);f.sel=false;f.porque='';d.archivos.push(f)}});
    pintar();pedirPresu();
  }
  async function fundir(){
    const ids=[...S.sel].filter(id=>song(id));if(ids.length<2)return;
    const cs=ids.map(song);
    const o=GMr.ui.modal(`<h3>Fundir ${cs.length} canciones en una</h3><p class="meta" style="font-size:14px">Todos los archivos y sesiones se juntarán. ¿Qué nombre llevará?</p>
      <input class="imp-ruta" id="imp-fn" style="width:100%;box-sizing:border-box" value="${E(cs[0].titulo)}">
      <div class="acts"><button class="chip" data-r="0">Cancelar</button><button class="chip pri" data-r="1">Fundir</button></div>`);
    const ok=await new Promise(res=>{o.onclick=e=>{const r=e.target.dataset&&e.target.dataset.r;if(r!==undefined){res(r==='1')}else if(e.target===o)res(false)}});
    const nombre=(o.querySelector('#imp-fn')||{}).value;o.remove();
    if(!ok)return;
    const d=cs[0];d.titulo=(nombre||d.titulo).trim()||'Sin título';
    cs.slice(1).forEach(c=>{d.archivos.push(...c.archivos);d.sesiones.push(...c.sesiones);d.razon.push('fundida con «'+c.titulo+'» (lo pediste tú)');if(c.boceto===false)d.boceto=false;S.songs.splice(S.songs.indexOf(c),1)});
    d.archivos.sort((a,b)=>CATS.findIndex(x=>x[0]===a.cat)-CATS.findIndex(x=>x[0]===b.cat)||a.nombre.localeCompare(b.nombre));
    S.sel=new Set();d.abierta=true;pintar();pedirPresu();
  }
  async function actualizar(){
    const cs=(S.copia&&S.copia.resumen&&S.copia.resumen.canciones)||[];
    GMr.ui.toast('Actualizando la biblioteca…');
    await GMr.ui.reload();
    const ids=[];
    cs.filter(c=>c.boceto).forEach(c=>{const s=GMr.all.find(x=>x.dir===c.carpeta);if(s)ids.push(s.id)});
    if(ids.length)GMr.ui.setDraft(ids,true);
    S.actualizada=true;S.nBocetos=ids.length;
    const n=cs.filter(c=>GMr.all.find(x=>x.dir===c.carpeta)).length;
    GMr.ui.go('mod:importar');   // el gestor vuelve a pintar la sección con el resumen
    if(n<cs.length)GMr.ui.toast(`El gestor ha reconocido ${n} de ${cs.length} canciones (las demás no tienen audio ni letra que catalogar).`);
  }
  async function deshacer(id){
    if(!await GMr.ui.ask('¿Deshacer esta importación?','Se quitarán de tu biblioteca <b>solo los archivos que esta importación copió</b>, y solo si siguen idénticos a como se copiaron (si has cambiado alguno, se queda). Las carpetas se quitan solo si quedan vacías. <b>Tus archivos originales no se tocan</b>.','Sí, deshacer'))return;
    const r=await GMr.api('importar','deshacer',{id}).catch(()=>({ok:false,error:'No pude hablar con el gestor.'}));
    if(!r.ok)return GMr.ui.toast(r.error||'No se pudo deshacer');
    GMr.ui.toast('Deshaciendo…');
    for(;;){
      await sleep(500);
      const e=await GMr.api('importar','estado?job='+r.job).catch(()=>null);
      if(!e||!e.ok)break;
      if(e.estado==='corriendo')continue;
      const msg=e.estado==='listo'?`Deshecho: ${e.borrados} archivos quitados${e.conservados.length?`, ${e.conservados.length} conservados porque habían cambiado`:''}${e.ausentes?`, ${e.ausentes} ya no estaban`:''}.`:('No se pudo deshacer: '+(e.error||e.estado));
      S.deshecha=msg;GMr.ui.toast(msg);break;
    }
    S.hist=null;await GMr.ui.reload().catch(()=>{});
    S.actualizada=true;
    if(S.paso===1)cargarHist();
    pintar();
  }

  return {montar};
})();
