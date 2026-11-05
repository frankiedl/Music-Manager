/* Ajustes: carpeta de la música, nombre y titular, y (los plugins de efectos están desactivados por ahora). */
(()=>{
const api=(r,b)=>GM.api('ajustes',r,b);
const esc=s=>GM.ui.esc(s);

/* Explorador de carpetas dentro de la app. Devuelve la ruta elegida o null. Otros módulos pueden usarlo: GM.mods.ajustes.elegirCarpeta('Título') */
function elegirCarpeta(titulo,inicio){
  return new Promise(res=>{
    const o=GM.ui.modal(`<h3>${esc(titulo||'Elegir carpeta')}</h3><div class="meta" id="aj-ruta" style="word-break:break-all;margin:4px 0 8px"></div>
      <div id="aj-lista" style="max-height:46vh;overflow:auto;border-radius:10px;background:var(--panel2);padding:4px"></div>
      <div class="acts"><button class="chip" data-r="0">Cancelar</button><button class="chip pri" data-r="1" id="aj-ok">Elegir esta carpeta</button></div>`);
    let cur='';
    const ir=async ruta=>{
      const r=await api('carpetas?ruta='+encodeURIComponent(ruta||''));
      if(!r.ok){GM.ui.toast(r.error||'No se pudo abrir');return}
      cur=r.ruta;o.querySelector('#aj-ruta').textContent=cur||'Este equipo';o.querySelector('#aj-ok').disabled=!cur;
      o.querySelector('#aj-lista').innerHTML=(r.padre!==null?`<div class="aj-it" data-p="${esc(r.padre)}" style="padding:8px 10px;cursor:pointer">⬆ Subir</div>`:'')+
        (r.carpetas.map(c=>`<div class="aj-it" data-p="${esc(c.p)}" style="padding:8px 10px;cursor:pointer;border-radius:8px">📁 ${esc(c.n)}</div>`).join('')||'<div class="meta" style="padding:8px">No hay subcarpetas aquí.</div>')};
    o.addEventListener('click',e=>{
      const it=e.target.closest('.aj-it');if(it)return ir(it.dataset.p);
      const r=e.target.dataset&&e.target.dataset.r;if(r==='1'){o.remove();res(cur)}else if(r==='0'){o.remove();res(null)}});
    ir(inicio||'')})}

async function render(el){
  const st=await api('estado');
  if(!st.ok){el.innerHTML=`<h1>Ajustes</h1><div class="callout">No se pudieron leer los ajustes: ${esc(st.error||'')}</div>`;return}
  el.innerHTML=`<h1>Ajustes</h1><p class="lead">Dónde está tu música y cómo te llamas.</p>
   <div class="panel"><h2>Mi música</h2>
    <div style="word-break:break-all;margin:6px 0 10px">📁 <b>${esc(st.biblioteca)}</b></div>
    ${st.editable?`<button class="chip pri" id="aj-cambiar">Cambiar la carpeta de mi música…</button><div class="meta" style="margin-top:6px">Se vuelve a leer todo. Tu música no se mueve ni se copia: se usa donde está.</div>`
      :'<div class="meta">En esta instalación la carpeta de la música es fija.</div>'}
    ${GM.mods.importar?`<details id="aj-imp" style="margin-top:14px"><summary style="cursor:pointer;font-weight:600">📥 Importar música de otras carpetas (proyectos de tu DAW, bocetos, directos…)</summary><div id="aj-imp-body" style="margin-top:10px"></div></details>`:''}</div>
   <div class="panel"><h2>Cómo me llamo</h2>
    <label class="meta">Nombre artístico</label><input class="mxin" id="aj-art" value="${esc(st.artista)}" placeholder="Tu nombre artístico">
    <label class="meta">Titular del copyright (para los mixtapes y los másters)</label><input class="mxin" id="aj-tit" value="${esc(st.titular)}" placeholder="Nombre que aparecerá en © …">
    <button class="chip pri" id="aj-guardar">Guardar</button></div>
   <div class="panel"><h2>Idioma</h2><div class="meta" style="margin-bottom:6px">Idioma de la interfaz. Se recuerda en este navegador.</div>
    <select class="mxin" id="aj-idioma">${Object.entries(GM.idiomas||{es:'Español'}).map(([k,v])=>`<option value="${k}"${k===GM.idioma?' selected':''}>${v}</option>`).join('')}</select></div>
   <div class="panel"><h2>Sobre el gestor</h2><div class="meta">Tus datos (estrellas, notas, ajustes…) están en: ${esc(st.datos)}<br>Haz copia de seguridad de esa carpeta y de tu música.</div></div>`;
  const guardar=async(msg)=>{
    const r=await api('guardar',{artista:el.querySelector('#aj-art').value,titular:el.querySelector('#aj-tit').value});
    if(r.ok){Object.assign(GM.cfg,{artista:el.querySelector('#aj-art').value.trim(),titular:el.querySelector('#aj-tit').value.trim()});GM.ui.toast(msg||'Guardado ✓')}else GM.ui.toast(r.error||'No se pudo guardar')};
  el.querySelector('#aj-guardar').onclick=()=>guardar();
  const idi=el.querySelector('#aj-idioma');if(idi)idi.onchange=()=>GM.setIdioma&&GM.setIdioma(idi.value);
  const b=el.querySelector('#aj-cambiar');
  if(b)b.onclick=async()=>{
    const p=await elegirCarpeta('Elige la carpeta de tu música',st.biblioteca);if(!p)return;
    if(!await GM.ui.ask('Cambiar la carpeta de la música','Se usará «'+esc(p)+'» como tu biblioteca y se volverá a leer todo. No se mueve ni se borra nada.','Cambiar'))return;
    GM.ui.toast('Leyendo la carpeta…');const r=await api('biblioteca',{ruta:p});
    if(r.ok){GM.ui.toast('Biblioteca cambiada ✓');await GM.ui.reload()}else GM.ui.toast(r.error||'No se pudo cambiar')};
  const imp=el.querySelector('#aj-imp');
  if(imp)imp.addEventListener('toggle',()=>{const b=el.querySelector('#aj-imp-body');if(imp.open&&!b.children.length)GM.mods.importar.render(b,GM)});}

GM.register({id:'ajustes',render,init(G){G.mods.ajustes.elegirCarpeta=elegirCarpeta}});
})();
