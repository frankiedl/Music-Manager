/* Módulo «estado» · asistente para importar un informe CSV/TSV: elegir archivo → «qué columna es qué» → comprobar → guardar.
   El archivo se lee en el navegador y solo se guarda el resultado ya limpio en la carpeta de datos del módulo (en tu equipo). */
(function(){
const EST=window.EST,E=EST.E,C=window.EstadoCSV;
const CAMPOS=[
  {k:'t',n:'Canción',req:1,syn:['track name','track title','song title','song','track','title','cancion','nombre de la cancion','titulo','titulo de la cancion','nombre','video title','titulo del video','contenido','content']},
  {k:'i',n:'ISRC (si viene)',syn:['isrc']},
  {k:'f',n:'Fecha o mes',syn:['royalty date','sales period','reporting month','sale month','period','periodo','month','mes','date','fecha','day','dia','start date','transaction date']},
  {k:'n',n:'Reproducciones',syn:['streams','stream count','plays','reproducciones','visualizaciones','views','quantity','cantidad','units','unidades']},
  {k:'e',n:'Ingresos',syn:['earnings','revenue','ingresos','royalty','royalties','net revenue','importe','amount','total earned','payable','ganancias','total']},
  {k:'p',n:'Plataforma / tienda',syn:['service','store','platform','plataforma','dsp','retailer','tienda','store name','servicio']},
  {k:'c',n:'País',syn:['country','pais','territory','territorio','country of sale','region']},
  {k:'u',n:'Moneda',syn:['currency','moneda','divisa']},
];
const fnv=s=>{let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(36)+s.length.toString(36)};
const PASOS=['1 · Archivo','2 · Qué columna es qué','3 · Comprobar','4 · Hecho'];
const SEPN={',':'Coma ( , )',';':'Punto y coma ( ; )','\t':'Tabulador','|':'Barra ( | )'};

function adivinar(cab){
  const usado=new Set(),mapa={};
  const nc=cab.map(c=>C.norm(c));
  CAMPOS.forEach(c=>{ // 1º coincidencia exacta, 2º que contenga la palabra
    for(const pass of [0,1]){ if(mapa[c.k]!=null)break;
      for(const s of c.syn){const i=nc.findIndex((h,ix)=>!usado.has(ix)&&(pass?h.includes(s):h===s));if(i>=0){mapa[c.k]=i;usado.add(i);break}}}
  });
  return mapa;
}
function aplicarPerfil(I,p){
  const nc=I.cab.map(c=>C.norm(c)),mapa={};let ok=0,tot=0;
  Object.entries(p.mapa||{}).forEach(([k,nom])=>{tot++;const i=nc.indexOf(C.norm(nom));if(i>=0){mapa[k]=i;ok++}});
  if(!tot||ok<tot)return false;
  I.mapa=mapa;I.dec=p.dec||I.dec;I.orden=p.orden||I.orden;if(p.mon)I.mon=p.mon;if(p.plataforma)I.plat=p.plataforma;I.perfil=p.nombre;I.idPerfil=p.id;return true;
}
function preparar(I){ // separa filas y cabecera con lo elegido
  I.R=C.filas(I.texto,I.sep);
  if(I.hdrAuto)I.hdr=C.cabecera(I.R);
  I.cab=(I.R[I.hdr]||[]).map(x=>String(x).trim());
}
function numCols(I){return Object.keys(I.mapa).filter(k=>k==='n'||k==='e').map(k=>I.mapa[k]).filter(i=>i!=null)}
function construir(I){
  const dec=I.dec,M=new Map(),est={leidas:0,sinTitulo:0,sinFecha:0,total:0};
  const fechasRaw=I.mapa.f!=null?I.R.slice(I.hdr+1,I.hdr+800).map(r=>r[I.mapa.f]||''):[];
  const orden=I.orden||C.ordenFechas(fechasRaw)||'dmy';
  for(let i=I.hdr+1;i<I.R.length;i++){
    const r=I.R[i],g=k=>I.mapa[k]!=null?String(r[I.mapa[k]]==null?'':r[I.mapa[k]]).trim():'';
    est.leidas++;
    const t=g('t');if(!t){est.sinTitulo++;continue}
    if(/^(total|totales|grand total|suma|sum)\b/i.test(t)){est.total++;continue}
    let m=I.mapa.f!=null?C.fecha(g('f'),orden):null;if(!m&&I.mes)m=I.mes;
    if(!m){est.sinFecha++;continue}
    const n=I.mapa.n!=null?C.numero(g('n'),dec):null,e=I.mapa.e!=null?C.numero(g('e'),dec):null;
    const o={t,i:g('i').toUpperCase().replace(/[^A-Z0-9]/g,''),m,p:g('p')||I.plat||'',c:g('c'),n:n||0,e:e||0,u:(g('u')||I.mon||'').toUpperCase()};
    const key=[o.t,o.i,o.m,o.p,o.c,o.u].join('\u0001'),x=M.get(key);
    if(x){x.n+=o.n;x.e+=o.e}else M.set(key,o);
  }
  const filas=[...M.values()].map(o=>{o.e=Math.round(o.e*1e6)/1e6;return o});
  const ms=filas.map(o=>o.m).sort();
  return{filas,est,orden,periodo:ms.length?[ms[0],ms[ms.length-1]]:null};
}

function leerArchivo(file){
  return file.arrayBuffer().then(buf=>{
    const d=C.leer(buf);
    const I={nombre:file.name,buf,texto:d.texto,enc:d.codificacion,sep:C.separador(d.texto),hdrAuto:true,mapa:{},mon:'EUR',plat:'',mes:'',orden:'',paso:2,hash:fnv(d.texto)};
    preparar(I);I.dec=C.decimal(I.R,I.hdr+1,null,I.sep);
    const ad=adivinar(I.cab);
    // ¿hay un perfil guardado que encaje?
    const ps=(EST.D.perfiles||[]).slice().sort((a,b)=>Object.keys(b.mapa||{}).length-Object.keys(a.mapa||{}).length);
    I.mapa=ad;let usado=false;for(const p of ps){if(aplicarPerfil(I,p)){usado=true;break}}
    I.perfilAuto=usado;
    return I;
  });
}

/* ---------- pantallas ---------- */
EST.pintarImportar=(el)=>{
  const I=EST.imp;
  if(!I)return pantallaArchivo(el);
  if(I.paso===2)return pantallaColumnas(el,I);
  if(I.paso===3)return pantallaComprobar(el,I);
  return pantallaFin(el,I);
};
const cabeza=(I,p)=>`<p><button class="chip" id="est-cancel">← Cancelar</button></p><div class="est-steps-wiz">${PASOS.map((n,i)=>`<span class="${i+1===p?'on':i+1<p?'ok':''}">${i+1<p?'✓ ':''}${n}</span>`).join('')}</div>`;
const salir=el=>{const b=el.querySelector('#est-cancel');if(b)b.onclick=()=>{EST.sub=null;EST.imp=null;EST.pintar()}};

function pantallaArchivo(el){
  el.innerHTML=`${cabeza(null,1)}<div class="est-drop" id="est-drop"><div style="font-size:34px">📄</div>
    <p style="margin:8px 0"><b>Suelta aquí el archivo CSV</b> (o TSV) de tu plataforma o distribuidora</p>
    <label class="chip pri" style="display:inline-block;cursor:pointer">Elegir archivo…<input type="file" id="est-file" accept=".csv,.tsv,.txt,text/csv" style="display:none"></label>
    <p class="meta" style="margin-top:12px">Se lee en tu equipo. No se sube a ningún sitio. Funciona con coma o punto y coma, con tildes, y con decimales con coma (12,5) o con punto (12.5).</p></div>
    <div class="callout" style="margin-top:16px"><b>Sobre los formatos.</b> Cada plataforma exporta sus columnas a su manera y casi ninguna publica el formato exacto, así que no doy por bueno ningún formato concreto: en el siguiente paso eliges tú «qué columna es qué» y se guarda como perfil para la próxima vez. Si tu plataforma solo ofrece Excel (.xlsx), ábrelo y usa «Guardar como… CSV».</div>`;
  salir(el);
  const go=async f=>{if(!f)return;try{EST.imp=await leerArchivo(f);EST.pintar()}catch(e){GM.ui.toast('No pude leer el archivo: '+e.message)}};
  el.querySelector('#est-file').onchange=e=>go(e.target.files[0]);
  const d=el.querySelector('#est-drop');
  ['dragenter','dragover'].forEach(ev=>d.addEventListener(ev,e=>{e.preventDefault();d.classList.add('over')}));
  ['dragleave','drop'].forEach(ev=>d.addEventListener(ev,e=>{e.preventDefault();d.classList.remove('over')}));
  d.addEventListener('drop',e=>go(e.dataTransfer.files[0]));
}

function pantallaColumnas(el,I){
  const cab=I.cab,filas=I.R.slice(I.hdr+1,I.hdr+9);
  const opt=k=>`<option value="">— ninguna —</option>`+cab.map((c,i)=>`<option value="${i}" ${I.mapa[k]===i?'selected':''}>${E(c||'(columna '+(i+1)+')')}</option>`).join('');
  const sinFecha=I.mapa.f==null;
  const ambig=I.mapa.f!=null&&!C.ordenFechas(I.R.slice(I.hdr+1,I.hdr+800).map(r=>r[I.mapa.f]||''))&&/^\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}/.test((filas[0]||[])[I.mapa.f]||'');
  el.innerHTML=`${cabeza(I,2)}
   <div class="panel" style="margin-bottom:14px"><b>${E(I.nombre)}</b>
     <div class="meta" style="margin-top:4px">Detecté: codificación <b>${E(I.enc)}</b> · separador <b>${E(SEPN[I.sep]||I.sep)}</b> · decimales con <b>${I.dec===','?'coma (12,5)':'punto (12.5)'}</b> · ${I.R.length-I.hdr-1} filas de datos${I.perfilAuto?` · <span class="est-ok">he reconocido tu perfil «${E(I.perfil)}»</span>`:''}</div>
     <div class="est-filt" style="margin:10px 0 0">
       <label>Separador <select class="est-in" id="w-sep">${Object.entries(SEPN).map(([k,n])=>`<option value="${k}" ${I.sep===k?'selected':''}>${n}</option>`).join('')}</select></label>
       <label>Decimales <select class="est-in" id="w-dec"><option value="," ${I.dec===','?'selected':''}>con coma (12,5)</option><option value="." ${I.dec==='.'?'selected':''}>con punto (12.5)</option></select></label>
       <label>Fila de títulos de columna <input class="est-in" id="w-hdr" type="number" min="1" max="60" style="width:70px" value="${I.hdr+1}"></label>
       <label>Texto <select class="est-in" id="w-enc"><option value="">${E(I.enc)} (detectado)</option><option value="utf-8">Forzar UTF-8</option><option value="windows-1252">Forzar Windows (ANSI)</option></select></label>
     </div></div>
   <div class="est-prev" style="margin-bottom:16px"><table><thead><tr>${cab.map(c=>`<th>${E(c)}</th>`).join('')}</tr></thead><tbody>${filas.map(r=>`<tr>${cab.map((_,i)=>`<td>${E(r[i]||'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
   <div class="panel"><h3 style="margin:0 0 4px">¿Qué columna es qué?</h3><div class="meta" style="margin-bottom:12px">Ya he probado a adivinarlo por el nombre de las columnas; corrige lo que no sea. Solo la canción y un número (reproducciones o ingresos) son imprescindibles.</div>
     <div class="est-map">${CAMPOS.map(c=>`<label for="m-${c.k}">${c.n}${c.req?' <span class="req">*</span>':''}</label><select class="est-in" id="m-${c.k}" data-k="${c.k}">${opt(c.k)}</select>`).join('')}
       ${sinFecha?`<label for="w-mes">Mes de todo el archivo <span class="meta">(no hay columna de fecha)</span></label><input class="est-in" id="w-mes" type="month" value="${E(I.mes||'')}">`:''}
       ${ambig?`<label>Las fechas tipo 03/04/2025 son…</label><select class="est-in" id="w-ord"><option value="dmy" ${I.orden!=='mdy'?'selected':''}>día/mes/año</option><option value="mdy" ${I.orden==='mdy'?'selected':''}>mes/día/año</option></select>`:''}
       ${I.mapa.p==null?`<label for="w-plat">Plataforma <span class="meta">(si el archivo no la dice)</span></label><input class="est-in" id="w-plat" list="est-pl" value="${E(I.plat)}" placeholder="Spotify, YouTube, Mi distribuidora…"><datalist id="est-pl">${['Spotify','Apple Music','YouTube','SoundCloud','Amazon Music','Deezer','TikTok','Tidal','Bandcamp','SGAE'].map(x=>`<option value="${x}">`).join('')}</datalist>`:''}
       ${I.mapa.u==null&&I.mapa.e!=null?`<label for="w-mon">Moneda de los ingresos</label><input class="est-in" id="w-mon" value="${E(I.mon)}" style="width:90px" maxlength="4">`:''}
     </div>
     <div id="w-err" class="est-bad" style="margin-top:10px"></div>
     <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
       <button class="chip pri" id="w-sig">Siguiente: comprobar →</button>
       <label class="meta">Guardar esta forma de leer como perfil: <input class="est-in" id="w-pf" placeholder="p. ej. Mi distribuidora" value="${E(I.perfil||'')}"></label></div>
     <div class="meta" style="margin-top:6px">Con un perfil guardado, la próxima vez que importes un archivo con las mismas columnas se hace solo.</div>
   </div>`;
  salir(el);
  const rerender=()=>{preparar(I);EST.pintar()};
  el.querySelector('#w-sep').onchange=e=>{I.sep=e.target.value;I.hdrAuto=true;preparar(I);I.dec=C.decimal(I.R,I.hdr+1,null,I.sep);I.mapa=adivinar(I.cab);EST.pintar()};
  el.querySelector('#w-dec').onchange=e=>{I.dec=e.target.value};
  el.querySelector('#w-hdr').onchange=e=>{I.hdr=Math.max(0,(+e.target.value||1)-1);I.hdrAuto=false;preparar(I);I.mapa=adivinar(I.cab);EST.pintar()};
  el.querySelector('#w-enc').onchange=e=>{if(!e.target.value)return;const t=new TextDecoder(e.target.value).decode(new Uint8Array(I.buf));I.texto=t.charCodeAt(0)===0xFEFF?t.slice(1):t;I.enc=e.target.value==='utf-8'?'UTF-8':'Windows (ANSI)';I.hash=fnv(I.texto);I.hdrAuto=true;preparar(I);I.mapa=adivinar(I.cab);EST.pintar()};
  el.querySelectorAll('select[data-k]').forEach(s=>s.onchange=()=>{const k=s.dataset.k;if(s.value==='')delete I.mapa[k];else I.mapa[k]=+s.value;if(k==='f'||k==='n'||k==='e'){I.perfilAuto=false;EST.pintar()}});
  const bind=(id,k)=>{const x=el.querySelector(id);if(x)x.onchange=x.oninput=()=>{I[k]=x.value}};
  bind('#w-mes','mes');bind('#w-ord','orden');bind('#w-plat','plat');bind('#w-mon','mon');
  el.querySelector('#w-pf').oninput=e=>{I.perfilNuevo=e.target.value.trim()};
  el.querySelector('#w-sig').onclick=()=>{
    const err=m=>el.querySelector('#w-err').textContent=m;
    if(I.mapa.t==null)return err('Indica qué columna es la canción.');
    if(I.mapa.n==null&&I.mapa.e==null)return err('Indica qué columna son las reproducciones o los ingresos.');
    if(I.mapa.f==null&&!I.mes)return err('No hay columna de fecha: elige el mes al que corresponde todo el archivo.');
    I.res=construir(I);
    if(!I.res.filas.length)return err('No he conseguido leer ninguna fila con esos ajustes. Revisa la fila de títulos, la fecha y el separador.');
    I.paso=3;EST.pintar()};
}

function pantallaComprobar(el,I){
  const r=I.res,mt=null,A=EST.D.alias;
  // casado de prueba (antes de guardar)
  const tmp={D:EST.D};const F=r.filas;
  const resolver=EST.resolverFila,matcherTmp=(()=>{ // misma lógica que las vistas
    const full=new Map(),rel=new Map();GM.songs.forEach(s=>{const t=GM.title(s);full.set(C.norm(t),s.id);rel.set(C.titulo(t),s.id)});return{full,rel}})();
  const cnt={exacto:0,isrc:0,manual:0,parecido:0,sin:0,ign:0},sin=new Map();
  F.forEach(o=>{const x=resolver(o,matcherTmp,A);if(x.ign)cnt.ign++;else if(x.sid)cnt[x.how]++;else{cnt.sin++;const k=C.norm(o.t),y=sin.get(k)||{t:o.t,n:0};y.n+=o.n;sin.set(k,y)}});
  const dup=EST.D.informes.find(i=>i.hash===I.hash);
  const totN=F.reduce((a,o)=>a+o.n,0),totE={};F.forEach(o=>{if(o.e)totE[o.u]=(totE[o.u]||0)+o.e});
  const plats=[...new Set(F.map(o=>o.p).filter(Boolean))];
  el.innerHTML=`${cabeza(I,3)}
   ${dup?`<div class="callout">Este mismo archivo ya lo importaste (<b>${E(dup.nombre)}</b>). Si sigues, se <b>sustituirá</b> el anterior para no contar dos veces.</div>`:''}
   <div class="est-kpis">
     <div class="est-kpi"><div class="n">${F.length}</div><div class="t">filas útiles (de ${r.est.leidas} leídas)</div></div>
     <div class="est-kpi"><div class="n">${EST.fmtN(totN)}</div><div class="t">reproducciones</div></div>
     ${Object.keys(totE).length?`<div class="est-kpi"><div class="n" style="font-size:20px">${Object.entries(totE).map(([u,v])=>EST.fmtE(v)+' '+E(u)).join(' + ')}</div><div class="t">ingresos</div></div>`:''}
     <div class="est-kpi"><div class="n" style="font-size:20px">${r.periodo?EST.mesTxt(r.periodo[0],1)+' → '+EST.mesTxt(r.periodo[1],1):'—'}</div><div class="t">periodo</div></div>
   </div>
   <div class="panel"><h3 style="margin:0 0 8px">Casado con tus canciones</h3>
     <div>✅ ${cnt.exacto+cnt.isrc+cnt.manual} filas casadas con claridad · 🔎 ${cnt.parecido} por parecido del título (sin «Remastered», «Radio Edit»…) · ⚠ <b>${cnt.sin}</b> sin casar${cnt.ign?` · 🚫 ${cnt.ign} ignoradas por ti`:''}</div>
     ${sin.size?`<div class="meta" style="margin-top:8px">Sin casar: ${[...sin.values()].sort((a,b)=>b.n-a.n).slice(0,8).map(x=>'«'+E(x.t)+'»').join(', ')}${sin.size>8?' y '+(sin.size-8)+' más':''}. Después de importar podrás asignarlos a mano.</div>`:''}
     <div class="meta" style="margin-top:8px">${plats.length?'Plataformas: '+plats.map(E).join(', ')+'. ':'<span class="est-bad">No se indicó plataforma.</span> '}${r.est.sinFecha?` ${r.est.sinFecha} filas sin fecha válida se han descartado.`:''}${r.est.total?` ${r.est.total} filas de «Total» se han saltado.`:''}${r.est.sinTitulo?` ${r.est.sinTitulo} filas sin título se han saltado.`:''}</div></div>
   <div style="margin-top:14px;display:flex;gap:8px"><button class="chip" id="w-atras">← Cambiar columnas</button><button class="chip pri" id="w-imp">Importar</button></div>`;
  salir(el);
  el.querySelector('#w-atras').onclick=()=>{I.paso=2;EST.pintar()};
  el.querySelector('#w-imp').onclick=async()=>{
    const b=el.querySelector('#w-imp');b.disabled=true;
    const inf={nombre:I.nombre,plataforma:I.plat||plats.join(', '),hash:I.hash,periodo:r.periodo,perfil:I.perfilNuevo||I.perfil||'',filas:r.filas,importado:new Date().toISOString().slice(0,19)};
    if(dup){await GM.api('estado','informe_borrar',{id:dup.id});EST.D.informes=EST.D.informes.filter(x=>x.id!==dup.id)}
    const g=await GM.api('estado','informe_guardar',{informe:inf});
    if(!g.ok){b.disabled=false;return GM.ui.toast('No se pudo guardar: '+g.error)}
    inf.id=g.id;EST.D.informes.push(inf);EST.invalida();
    // perfil
    const nom=I.perfilNuevo;
    if(nom){
      const p={id:I.idPerfil||('p'+Date.now().toString(36)),nombre:nom,plataforma:I.plat||'',mapa:{},dec:I.dec,orden:r.orden,mon:I.mon};
      Object.entries(I.mapa).forEach(([k,i])=>{if(I.cab[i])p.mapa[k]=I.cab[i]});
      const ps=EST.D.perfiles.filter(x=>x.nombre!==nom&&x.id!==p.id);ps.push(p);EST.D.perfiles=ps;
      await GM.api('estado','perfiles_guardar',{perfiles:ps});
    }
    I.sin=cnt.sin;I.paso=4;EST.pintar()};
}

function pantallaFin(el,I){
  el.innerHTML=`${cabeza(I,4)}<div class="panel" style="text-align:center;padding:30px">
    <div style="font-size:40px">✅</div><h2 style="margin:6px 0">Informe importado</h2>
    <p class="lead" style="margin:0 auto 16px">${I.res.filas.length} filas guardadas en tu equipo.${I.perfilNuevo?' Perfil «'+E(I.perfilNuevo)+'» guardado.':''}${I.sin?` Hay <b>${I.sin}</b> filas que no se han podido unir a ninguna canción.`:''}</p>
    <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
      ${I.sin?'<button class="chip pri" id="f-res">Resolver los no casados</button>':''}
      <button class="chip ${I.sin?'':'pri'}" id="f-ver">Ver los datos</button></div></div>`;
  salir(el);
  const done=(sub)=>{EST.sub=sub;EST.soloAprox=false;EST.imp=null;EST.pintar()};
  el.querySelector('#f-ver').onclick=()=>done(null);
  const r=el.querySelector('#f-res');if(r)r.onclick=()=>done('resolver');
}
})();
