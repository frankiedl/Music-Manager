/* «estado» module: music status panel + platform reports via CSV + optional connections.
   This file: registration, tabs, shared data, SVG charts and the «Resumen» / «Álbumes» (Summary / Albums) panel.
   Other files: csv.js (reader), importar.js (wizard), informes.js (performance views), conexiones.js (optional Spotify). */
(function(){
const EST=window.EST={vistas:{},D:{informes:[],perfiles:[],alias:{t:{},isrc:{}},spotify:{}},cargado:false};
const E=EST.E=s=>GM.ui.esc(s==null?'':s);
const S=EST.S=()=>GM.state('estado');
const fmtN=EST.fmtN=n=>Math.round(n).toLocaleString('es-ES');
EST.fmtE=n=>(Math.round(n*100)/100).toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2});
const MESN=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
EST.mesTxt=(m,largo)=>{const [y,k]=m.split('-');return MESN[+k-1]+(largo?' ':' ’')+(largo?y:y.slice(2))};

/* ---------- saved data (module server) ---------- */
EST.cargar=async()=>{
  const r=await GM.api('estado','datos').catch(e=>({ok:false,error:String(e)}));
  if(r&&r.ok){EST.D={informes:r.informes||[],perfiles:r.perfiles||[],alias:Object.assign({t:{},isrc:{}},r.alias||{}),spotify:r.spotify||{}};EST.cargado=true}
  else EST.errorCarga=(r&&r.error)||'No se pudieron leer los datos.';
  return r;
};

/* ---------- status of each song in the process ---------- */
EST.PASOS=[{k:'letra',n:'Letra',ic:'📝'},{k:'version',n:'Versión',ic:'🎧'},{k:'stems',n:'Stems',ic:'🎚'},{k:'master',n:'Máster',ic:'💿'},{k:'portada',n:'Portada',ic:'🖼'},{k:'publicada',n:'Publicada',ic:'🚀'}];
const dirDe=s=>GM.dir(s)||'';
EST.pasos=s=>{
  const vs=s.versions||[],d=dirDe(s),pub=d.startsWith('published'),pre=d.startsWith('prereleased');
  const fin=GM.finalPath(s);
  return{
    letra:!!(s.letra||GM.lyrics(s.id)),
    version:vs.length>0,
    stems:vs.some(v=>/\/stems?\//i.test(v.p)||/(^|[^a-z])stems?([^a-z]|$)/i.test(v.p.split('/').pop())),
    master:vs.some(v=>v.dep||/\/master\//i.test(v.p))||(!!fin&&!pub&&!pre),
    portada:!!GM.cover(s),
    publicada:pub?1:pre?.5:0,
  };
};
EST.estadoDe=s=>{const d=dirDe(s);return GM.isDraft(s)?'boceto':d.startsWith('published')?'pub':d.startsWith('prereleased')?'pre':'sin'};
EST.avance=s=>{const p=EST.pasos(s);return EST.PASOS.reduce((a,x)=>a+(+p[x.k]||0),0)/EST.PASOS.length};
EST.ESTADOS={pub:{n:'Publicadas',c:'var(--good)'},pre:{n:'Pre-released',c:'var(--warn)'},sin:{n:'Sin publicar',c:'var(--accent)'},boceto:{n:'Bocetos',c:'var(--muted)'}};
const KIND={album:'Álbum',single:'Single',pre:'Pre-released',proyecto:'Proyecto'};
EST.KIND=KIND;
EST.thumb=g=>{const c=g&&g.cover;return c&&c.t?'/thumb?f='+encodeURIComponent(c.t):''};

/* ---------- own SVG charts (no libraries: the app works offline) ---------- */
EST.donut=(items,tam=150)=>{
  const tot=items.reduce((a,x)=>a+x.v,0),r=tam/2-14,C=2*Math.PI*r;let off=0;
  if(!tot)return`<svg class="est-svg" style="width:${tam}px" viewBox="0 0 ${tam} ${tam}"><circle cx="${tam/2}" cy="${tam/2}" r="${r}" fill="none" stroke="var(--panel2)" stroke-width="22"/></svg>`;
  const arcs=items.filter(x=>x.v>0).map(x=>{const l=x.v/tot*C,a=`<circle cx="${tam/2}" cy="${tam/2}" r="${r}" fill="none" stroke="${x.c}" stroke-width="22" stroke-dasharray="${l} ${C-l}" stroke-dashoffset="${-off}" transform="rotate(-90 ${tam/2} ${tam/2})"><title>${E(x.n)}: ${x.v}</title></circle>`;off+=l;return a}).join('');
  return`<svg class="est-svg" style="width:${tam}px" viewBox="0 0 ${tam} ${tam}" role="img" aria-label="Reparto por estado">${arcs}<text x="${tam/2}" y="${tam/2+2}" text-anchor="middle" style="font-size:26px;font-weight:700;fill:var(--txt)">${tot}</text><text x="${tam/2}" y="${tam/2+18}" text-anchor="middle">canciones</text></svg>`;
};
/* bars per month: datos=[{m:'2025-03',v:12}], bar color in `c` */
EST.barrasMes=(datos,{c='var(--accent)',h=170,fmt=fmtN,unidad=''}={})=>{
  const W=640,pl=34,pb=22,pt=8,n=datos.length||1,max=Math.max(1,...datos.map(d=>d.v)),bw=(W-pl)/n;
  const ejes=[0,.5,1].map(f=>{const y=pt+(h-pb-pt)*(1-f);return`<line class="ax" x1="${pl}" x2="${W}" y1="${y}" y2="${y}"/><text x="${pl-4}" y="${y+3}" text-anchor="end">${fmt(max*f)}</text>`}).join('');
  const bars=datos.map((d,i)=>{const bh=(h-pb-pt)*d.v/max,x=pl+i*bw+bw*.15,y=h-pb-bh;
    return`<rect x="${x}" y="${y}" width="${bw*.7}" height="${Math.max(bh,d.v?1.5:0)}" rx="3" fill="${c}"><title>${EST.mesTxt(d.m,1)}: ${fmt(d.v)}${unidad}</title></rect>`+(n<=14||i%Math.ceil(n/12)===0?`<text x="${x+bw*.35}" y="${h-6}" text-anchor="middle">${EST.mesTxt(d.m)}</text>`:'')}).join('');
  return`<svg class="est-svg" viewBox="0 0 ${W} ${h}" role="img">${ejes}${bars}</svg>`;
};
EST.spark=(vals,c='var(--accent)',w=90,h=24)=>{
  if(!vals.length)return'';const max=Math.max(1,...vals),n=vals.length;
  const pts=vals.map((v,i)=>`${n===1?w/2:i*(w-2)/(n-1)+1},${h-2-(h-4)*v/max}`).join(' ');
  return`<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="vertical-align:middle"><polyline fill="none" stroke="${c}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" points="${pts}"/></svg>`;
};
EST.barraH=(pct,cls='')=>`<div class="est-bar ${cls||(pct>=99.5?'g':'')}"><b style="width:${Math.max(0,Math.min(100,pct))}%"></b></div>`;

/* ---------- panel calculations ---------- */
function actividad(){ // number of audio files per month, by the date of each version
  const M={};let ultima='';
  GM.songs.forEach(s=>(s.versions||[]).forEach(v=>{
    let f=v.fecha||'';if(!/^\d{4}-\d{2}/.test(f)&&v.mt)f=new Date(v.mt*1000).toISOString().slice(0,10);
    if(!/^\d{4}-\d{2}/.test(f))return;M[f.slice(0,7)]=(M[f.slice(0,7)]||0)+1;if(f>ultima)ultima=f}));
  const hoy=new Date().toISOString().slice(0,7),mx=Object.keys(M).sort().pop()||hoy,fin=mx>hoy?mx:hoy;
  const out=[];let [y,m]=fin.split('-').map(Number);
  for(let i=0;i<18;i++){out.unshift({m:y+'-'+String(m).padStart(2,'0'),v:M[y+'-'+String(m).padStart(2,'0')]||0});m--;if(m<1){m=12;y--}}
  return{datos:out,total:Object.values(M).reduce((a,b)=>a+b,0),ultima};
}
EST.faltan=(SS)=>{ // listas accionables
  const P=new Map(SS.map(s=>[s.id,EST.pasos(s)])),noPub=s=>!P.get(s.id).publicada;
  return[
    {t:'Tienen música pero no su letra',d:'Escribe o pega la letra para no perderla.',L:SS.filter(s=>P.get(s.id).version&&!P.get(s.id).letra)},
    {t:'Solo letra: aún sin música',d:'Canciones que están en fase de escritura.',L:SS.filter(s=>P.get(s.id).letra&&!P.get(s.id).version&&noPub(s))},
    {t:'Con stems pero sin máster',d:'Se grabaron y se separaron, pero falta sacar el máster.',L:SS.filter(s=>P.get(s.id).stems&&!P.get(s.id).master)},
    {t:'Sin máster',d:'Tienen versión y aún no tienen máster elegido.',L:SS.filter(s=>P.get(s.id).version&&!P.get(s.id).master&&!P.get(s.id).stems&&noPub(s))},
    {t:'Casi listas para publicar',d:'Tienen letra, versión, máster y portada: solo falta publicarlas.',L:SS.filter(s=>{const p=P.get(s.id);return noPub(s)&&p.letra&&p.version&&p.master&&p.portada&&!p.publicada})},
    {t:'Sin portada',d:'Ninguna imagen de portada para estas canciones.',L:SS.filter(s=>P.get(s.id).version&&!P.get(s.id).portada)},
    {t:'Publicadas sin máster identificado',d:'No sé cuál de sus versiones es la que salió.',L:SS.filter(s=>P.get(s.id).publicada===1&&!P.get(s.id).master)},
    {t:'Sin ningún audio',d:'Entradas del catálogo sin archivo de música.',L:SS.filter(s=>!P.get(s.id).version&&!P.get(s.id).letra)},
  ].filter(x=>x.L.length);
};
const chipSong=(s,fn)=>`<button class="chip" data-go="${E(s.id)}" title="Abrir la canción">${E(GM.title(s))}</button>`;
EST.enlazar=el=>el.querySelectorAll('[data-go]').forEach(b=>b.onclick=e=>{e.preventDefault();GM.ui.go('song',b.dataset.go)});

/* ---------- vista «Resumen» ---------- */
EST.vistas.resumen=(el)=>{
  const todas=GM.songs,SS=todas.filter(s=>!GM.isDraft(s));
  if(!todas.length){el.innerHTML='<div class="empty">Todavía no hay canciones en el gestor. Cuando las haya, aquí verás en qué punto está cada una.</div>';return}
  const cnt={pub:0,pre:0,sin:0,boceto:0};todas.forEach(s=>cnt[EST.estadoDe(s)]++);
  const pasos=SS.map(s=>EST.pasos(s)),fa=EST.faltan(SS),act=actividad();
  const avg=SS.length?Math.round(SS.reduce((a,s)=>a+EST.avance(s),0)/SS.length*100):0;
  const por=Object.keys(EST.ESTADOS).map(k=>({k,n:EST.ESTADOS[k].n,c:EST.ESTADOS[k].c,v:cnt[k]}));
  const gs=GM.groups().filter(g=>g.songs.length);
  const cuenta=k=>gs.filter(g=>g.kind===k).length;
  el.innerHTML=`
   <div class="est-kpis">
     <div class="est-kpi"><div class="n">${todas.length}</div><div class="t">canciones en total</div></div>
     <div class="est-kpi"><div class="n" style="color:var(--good)">${cnt.pub}</div><div class="t">publicadas</div></div>
     <div class="est-kpi"><div class="n" style="color:var(--warn)">${cnt.pre}</div><div class="t">pre-released</div></div>
     <div class="est-kpi"><div class="n">${cnt.sin}</div><div class="t">sin publicar</div></div>
     <div class="est-kpi"><div class="n" style="color:var(--muted)">${cnt.boceto}</div><div class="t">bocetos</div></div>
     <div class="est-kpi"><div class="n">${cuenta('album')}</div><div class="t">álbumes · ${cuenta('single')} singles · ${cuenta('proyecto')} proyectos</div></div>
     <div class="est-kpi"><div class="n">${avg}%</div><div class="t">avance medio de las canciones (sin bocetos)</div></div>
   </div>
   <div class="est-grid2">
     <div class="panel est-panel"><h3>Reparto por estado</h3>
       <div class="est-donutwrap">${EST.donut(por)}<div class="est-legend">${por.map(x=>`<div><i style="background:${x.c}"></i>${x.n}: <b>${x.v}</b></div>`).join('')}</div></div></div>
     <div class="panel est-panel"><h3>¿Por dónde va el proceso?</h3>
       <div class="meta" style="margin-bottom:6px">Cuántas de tus ${SS.length} canciones (sin bocetos) han llegado a cada paso.</div>
       ${EST.PASOS.map(p=>{const n=pasos.filter(x=>(+x[p.k]||0)>=1).length,pc=SS.length?n/SS.length*100:0;
         return`<div class="est-row"><span class="lab">${p.ic} ${p.n}</span>${EST.barraH(pc,p.k==='publicada'?'g':'')}<span class="meta" style="text-align:right">${n} · ${Math.round(pc)}%</span></div>`}).join('')}
     </div>
   </div>
   <div class="panel est-panel" style="margin-bottom:18px"><h3>Actividad: archivos de audio por mes</h3>
     ${act.total?EST.barrasMes(act.datos,{unidad:' archivos'})+`<div class="meta">Según la fecha de cada archivo de versión. Último movimiento: ${E(act.ultima)}.</div>`:'<div class="empty" style="padding:20px">Aún no hay fechas de archivos para dibujar la actividad.</div>'}
   </div>
   <h2 style="margin-top:6px">Lo que falta</h2>
   ${fa.length?fa.map(x=>`<details class="est-falta"><summary><span class="n">${x.L.length}</span>${E(x.t)}<span class="d">${E(x.d)}</span></summary>
      <div class="cuerpo">${x.L.slice(0,40).map(s=>chipSong(s)).join('')}${x.L.length>40?`<span class="meta" style="align-self:center">… y ${x.L.length-40} más</span>`:''}</div></details>`).join(''):'<div class="empty">✓ No falta nada de lo que puedo comprobar.</div>'}`;
  EST.enlazar(el);
};

/* ---------- vista «Álbumes» ---------- */
EST.dots=p=>EST.PASOS.map(x=>{const v=+p[x.k]||0;return`<i class="est-dot ${v>=1?'on':v>0?'half':''}" title="${x.n}${v>=1?': sí':v>0?': a medias':': falta'}"></i>`}).join('');
EST.vistas.albumes=(el)=>{
  const orden={album:0,single:1,pre:2,proyecto:3};
  const gs=GM.groups().filter(g=>g.songs.length||g.nuevo).sort((a,b)=>(orden[a.kind]-orden[b.kind])||a.title.localeCompare(b.title,'es'));
  if(!gs.length){el.innerHTML='<div class="empty">Aún no hay álbumes, singles ni proyectos.</div>';return}
  const R=EST.resumenCanciones?EST.resumenCanciones():null;
  el.innerHTML=gs.map(g=>{
    const L=GM.order(g),SS=L.filter(s=>!GM.isDraft(s)),base=SS.length?SS:L;
    const P=base.map(s=>EST.pasos(s)),av=base.length?Math.round(base.reduce((a,s)=>a+EST.avance(s),0)/base.length*100):0;
    const th=EST.thumb(g);let st=null;
    if(R){st={n:0,e:{}};L.forEach(s=>{const x=R.get(s.id);if(x){st.n+=x.n;Object.entries(x.e).forEach(([k,v])=>st.e[k]=(st.e[k]||0)+v)}})}
    return`<div class="panel est-alb"><div class="cab">
      ${th?`<img src="${th}" alt="" onerror="this.outerHTML='<div class=sc></div>'">`:'<div class="sc"></div>'}
      <div class="tt"><b>${E(g.title)}</b><div class="meta"><span class="tag">${KIND[g.kind]||g.kind}</span> ${L.length} ${L.length===1?'canción':'canciones'}${L.length-SS.length?` (${L.length-SS.length} boceto${L.length-SS.length>1?'s':''})`:''}${st&&st.n?` · ▶ ${fmtN(st.n)} repro.`:''}</div></div>
      <div class="pc">${av}%</div></div>
      ${EST.barraH(av,av>=100?'g':'')}
      <div class="est-steps">${EST.PASOS.map(x=>{const n=P.filter(p=>(+p[x.k]||0)>=1).length,pc=base.length?n/base.length*100:0;return`<div class="est-step">${x.ic} ${x.n}<br><b style="color:var(--txt)">${n}/${base.length}</b>${EST.barraH(pc,x.k==='publicada'?'g':'')}</div>`}).join('')}</div>
      <details class="est-songs"><summary>Ver las canciones</summary>
       ${L.map(s=>`<div class="est-srow"><span class="tt" data-go="${E(s.id)}">${E(GM.title(s))}${GM.isDraft(s)?' <span class="tag">📝 boceto</span>':''}</span><span class="meta">${R&&R.get(s.id)?'▶ '+fmtN(R.get(s.id).n):''}</span><span class="est-dots">${EST.dots(EST.pasos(s))}</span></div>`).join('')}
       <div class="meta" style="margin-top:8px">Los puntos son, por orden: ${EST.PASOS.map(x=>x.n.toLowerCase()).join(' · ')}.</div>
      </details></div>`}).join('');
  EST.enlazar(el);
};

/* ---------- the module ---------- */
const TABS=[['resumen','📊 Resumen'],['albumes','💿 Álbumes y canciones'],['informes','📈 Informes de plataformas'],['conexiones','🔌 Conexiones']];
EST.pintar=async()=>{
  const el=EST.el;if(!el)return;const st=S();let t=st.tab&&EST.vistas[st.tab]?st.tab:'resumen';
  el.innerHTML=`<h1>Estado</h1><p class="lead">En qué punto está tu música y cómo le va en las plataformas. Todo se calcula en tu equipo.</p>
    <div class="est-tabs">${TABS.map(([k,n])=>`<button class="chip ${k===t?'on':''}" data-tab="${k}">${n}</button>`).join('')}</div><div id="est-cuerpo"></div>`;
  el.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{st.tab=b.dataset.tab;GM.save();EST.pintar()});
  const cu=el.querySelector('#est-cuerpo');
  if(!EST.cargado)await EST.cargar();
  try{EST.vistas[t](cu)}catch(e){console.error('estado',e);cu.innerHTML='<div class="callout">No pude dibujar esta vista: '+E(e.message)+'</div>'}
};

GM.register({
  id:'estado',
  home:{title:'Estado de tu música',render(el){EST.el=el;EST.pintar()}},   // goes inside Home
  render(el){EST.el=el;EST.pintar()},
});
})();
