/* Módulo «estado» · pestaña «Conexiones»: qué se puede conseguir de cada plataforma (resumen honesto de LEEME.md)
   y la única conexión opcional: datos públicos de catálogo de Spotify con las claves propias de la persona. */
(function(){
const EST=window.EST,E=EST.E;
const FUENTES=[
 {n:'Spotify',csv:'Spotify for Artists permite descargar algunas estadísticas en CSV (streams por canción, audiencia, tablas de canciones y listas). No he podido verificar sus columnas: usa el asistente.',api:'La API pública NO da reproducciones por canción de tu música. Sirve para datos públicos de catálogo (ver abajo).'},
 {n:'Apple Music',csv:'Apple Music for Artists permite descargar un CSV del catálogo (Música → Ver todo). Columnas sin verificar.',api:'La API de Apple es de catálogo, exige el programa de pago de Apple Developer y no da analítica de artista. No se ofrece conexión.'},
 {n:'YouTube',csv:'YouTube Studio → Analytics → modo avanzado → «Exportar vista actual» (máximo 500 filas). Columnas sin verificar.',api:'YouTube Analytics API existe y usa OAuth con tu propio proyecto de Google Cloud. Es viable pero complejo para quien no es técnico: queda como diseño (ver LEEME.md).'},
 {n:'SoundCloud',csv:'Según su ayuda, Insights no exporta datos (consulta en resumen de búsqueda; no verificado).',api:'Desde 2026 se pueden registrar apps nuevas, pero exige la suscripción de pago Artist Pro. Sin verificar qué estadísticas da.'},
 {n:'Distribuidoras (DistroKid, TuneCore, Ditto, CD Baby, Amuse, RouteNote…)',csv:'Todas ofrecen informes de ingresos descargables. Solo las columnas de Amuse están publicadas (en Excel). El resto: formato no verificado, usa el asistente.',api:'No se ha encontrado API pública verificada para artistas.'},
 {n:'SGAE',csv:'Las liquidaciones se descargan desde la Sede Electrónica. Formato y columnas no verificados.',api:'No hay API pública conocida.'},
];

EST.vistas.conexiones=(el)=>{
  const sp=EST.D.spotify||{},cat=sp.catalogo||{};
  const enc=Object.keys(cat).filter(k=>!k.startsWith('_'));
  el.innerHTML=`<div class="callout"><b>Recomendación: empieza por los CSV.</b> Es lo más simple, no necesita claves ni cuentas de desarrollador, y todo se queda en tu equipo. Las conexiones por API solo existen donde la plataforma las ofrece de forma legítima, y casi siempre no dan lo que más interesa (tus reproducciones). Nunca hago «scraping» (leer webs saltándome sus normas).</div>
   <div style="margin:12px 0"><button class="chip pri" id="co-imp">＋ Importar un informe CSV</button></div>
   ${FUENTES.map(f=>`<div class="panel est-conn"><h3>${E(f.n)} <span class="est-badge nv">formato no verificado · usa el asistente de columnas</span></h3>
      <div class="meta" style="font-size:13px"><b>Informe:</b> ${E(f.csv)}</div><div class="meta" style="font-size:13px;margin-top:4px"><b>Conexión:</b> ${E(f.api)}</div></div>`).join('')}
   <h2>Spotify: datos públicos del catálogo <span class="est-badge">opcional · desactivado por defecto</span></h2>
   <div class="panel est-conn">
     <p class="meta" style="font-size:13.5px;margin-top:0">Busca tus canciones en Spotify y guarda <b>solo datos públicos</b>: enlace, ISRC, álbum y fecha de salida. El ISRC ayuda a casar los informes con tus canciones. <b>No trae reproducciones</b> (Spotify no las da por API) ni entra en tu cuenta.</p>
     <div class="callout" style="margin:10px 0"><b>Qué sale de tu equipo si lo activas:</b> tus claves de desarrollador (solo hacia Spotify, para pedir un permiso temporal de lectura) y, por cada canción, su título y el nombre de artista que escribas abajo. Nada más. Las claves se guardan solo en la carpeta de datos de este módulo en tu equipo (no en el código ni en tu estado compartido).
       <br><b>Requisitos de Spotify (2026):</b> crear una app en su panel de desarrolladores; el modo de desarrollo exige que la cuenta propietaria tenga <b>Spotify Premium</b>. Si no te interesa, déjalo sin activar.</div>
     <div class="est-map">
       <label for="sp-id">ID de cliente</label><input class="est-in" id="sp-id" autocomplete="off" placeholder="${sp.configurado?'guardado ('+E(sp.id_visible)+') — déjalo vacío para conservarlo':'pégalo aquí'}">
       <label for="sp-sec">Clave secreta</label><input class="est-in" id="sp-sec" type="password" autocomplete="off" placeholder="${sp.configurado?'guardada — déjalo vacío para conservarla':'pégala aquí'}">
       <label for="sp-art">Nombre de tu artista en Spotify</label><input class="est-in" id="sp-art" value="${E(sp.artista||'')}">
       <label for="sp-mer">País (2 letras, opcional)</label><input class="est-in" id="sp-mer" maxlength="2" style="width:70px" value="${E(sp.mercado||'')}" placeholder="ES">
       <label for="sp-on">Activar la conexión</label><label><input type="checkbox" id="sp-on" ${sp.activo?'checked':''}> Sí, acepto lo que sale del equipo (arriba)</label>
     </div>
     <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px">
       <button class="chip pri" id="sp-gua">Guardar</button>
       <button class="chip" id="sp-pro" ${sp.configurado?'':'disabled'}>Probar las claves</button>
       <button class="chip" id="sp-con" ${sp.activo?'':'disabled'}>Traer datos de mis canciones</button>
       <button class="chip" id="sp-olv" ${sp.configurado||enc.length?'':'disabled'}>Olvidar claves y datos</button></div>
     <div class="meta" id="sp-msg" style="margin-top:8px"></div>
     ${enc.length?`<h3 style="margin:16px 0 6px">Encontradas en Spotify (${enc.length}) <span class="meta">· actualizado ${E(sp.actualizado)}</span></h3>
       ${enc.map(id=>{const s=GM.song(id),c=cat[id];return s?`<div class="est-srow" style="grid-template-columns:1fr auto auto"><span class="tt" data-go="${E(id)}">${E(GM.title(s))}</span><span class="meta">${c.isrc?'ISRC '+E(c.isrc):'sin ISRC'} · ${E(c.fecha||'')}</span>${c.url?`<a class="chip" href="${E(c.url)}" target="_blank" rel="noopener">Abrir en Spotify</a>`:'<span></span>'}</div>`:''}).join('')}
       <div style="margin-top:10px"><button class="chip" id="sp-isrc">Usar estos ISRC para casar mis informes</button></div>`:''}
   </div>
   <p class="meta">Más detalle, condiciones y fuentes (con fecha de consulta) en <code>modulos/estado/LEEME.md</code>.</p>`;
  el.querySelector('#co-imp').onclick=()=>{EST.S().tab='informes';EST.sub='importar';EST.imp=null;EST.pintar()};
  EST.enlazar(el);
  const msg=(t,mal)=>{const m=el.querySelector('#sp-msg');m.className='meta '+(mal?'est-bad':'est-ok');m.textContent=t};
  const val=id=>el.querySelector(id).value;
  const guardar=async()=>{
    const r=await GM.api('estado','spotify_guardar',{id:val('#sp-id'),secreto:val('#sp-sec'),artista:val('#sp-art'),mercado:val('#sp-mer'),activo:el.querySelector('#sp-on').checked});
    if(r.ok)EST.D.spotify=Object.assign(EST.D.spotify||{},r.spotify);return r};
  el.querySelector('#sp-gua').onclick=async()=>{const r=await guardar();if(!r.ok)return msg(r.error,1);GM.ui.toast('Guardado');EST.pintar()};
  el.querySelector('#sp-pro').onclick=async()=>{msg('Probando…');const g=await guardar();if(!g.ok)return msg(g.error,1);const r=await GM.api('estado','spotify_probar',{});msg(r.ok?r.mensaje:r.error,!r.ok)};
  el.querySelector('#sp-con').onclick=async()=>{
    const g=await guardar();if(!g.ok)return msg(g.error,1);
    if(!await GM.ui.ask('¿Consultar Spotify?','Se enviará a Spotify el título de cada canción tuya (hasta 120) junto con el nombre de artista «'+E(val('#sp-art'))+'». ¿Continuar?','Consultar'))return;
    msg('Consultando Spotify… puede tardar un minuto.');
    const r=await GM.api('estado','spotify_consultar',{canciones:GM.songs.filter(s=>!GM.isDraft(s)).map(s=>({id:s.id,titulo:GM.title(s)}))});
    if(!r.ok)return msg(r.error,1);
    EST.D.spotify=r.spotify;GM.ui.toast(r.encontradas+' encontradas, '+r.no_encontradas+' no');EST.pintar()};
  el.querySelector('#sp-olv').onclick=async()=>{
    if(!await GM.ui.ask('¿Olvidar Spotify?','Se borran tus claves y los datos traídos, solo de este módulo.','Olvidar'))return;
    const r=await GM.api('estado','spotify_olvidar',{});if(r.ok){EST.D.spotify=r.spotify;EST.pintar()}};
  const bi=el.querySelector('#sp-isrc');if(bi)bi.onclick=async()=>{
    const A=EST.D.alias;let n=0;enc.forEach(id=>{const i=(cat[id].isrc||'').toUpperCase();if(i&&!A.isrc[i]){A.isrc[i]=id;n++}});
    const r=await GM.api('estado','alias_guardar',{alias:A});EST.invalida();GM.ui.toast(r.ok?n+' ISRC guardados':'Error: '+r.error)};
};
})();
