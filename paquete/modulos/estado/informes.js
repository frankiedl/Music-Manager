/* «estado» module · views of the imported reports: totals, per month, per platform, per song and per album, trends,
   and the screen to resolve the rows that were not matched to any song. */
(function(){
const EST=window.EST,E=EST.E,C=window.EstadoCSV,fmtN=EST.fmtN,fmtE=EST.fmtE;
const COLORES=['var(--accent)','#5e8bff','var(--good)','#a259ff','var(--warn)','#17b3a3','#ff8a3d','#8e8e93'];

/* ---------- matching rows to songs ---------- */
let _cache=null;
EST.invalida=()=>{_cache=null};
function matcher(){
  const full=new Map(),rel=new Map(),pubDe=new Map();
  GM.songs.forEach(s=>{
    const t=GM.title(s),pub=(GM.dir(s)||'').startsWith('published');
    [[full,C.norm(t)],[rel,C.titulo(t)]].forEach(([m,k])=>{if(!k)return;if(!m.has(k)||(pub&&!pubDe.get(m.get(k))))m.set(k,s.id);pubDe.set(s.id,pub)});
  });
  return{full,rel};
}
EST.resolverFila=(r,mt,A)=>{
  if(r.i){const a=A.isrc[r.i.toUpperCase()];if(a)return a==='-'?{sid:null,ign:1}:{sid:a,how:'isrc'}}
  const k=C.norm(r.t),a=A.t[k];if(a)return a==='-'?{sid:null,ign:1}:{sid:a,how:'manual'};
  if(mt.full.has(k))return{sid:mt.full.get(k),how:'exacto'};
  const k2=C.titulo(r.t);if(k2&&mt.rel.has(k2))return{sid:mt.rel.get(k2),how:'parecido'};
  return{sid:null};
};
EST.filas=()=>{
  if(_cache&&_cache.songs===GM.songs.length)return _cache.filas;
  const mt=matcher(),A=EST.D.alias,memo=new Map(),F=[];
  EST.D.informes.forEach(inf=>(inf.filas||[]).forEach(r=>{
    const k=(r.i||'')+'|'+r.t;let x=memo.get(k);if(!x){x=EST.resolverFila(r,mt,A);memo.set(k,x)}
    F.push(Object.assign({},r,{inf:inf.id,sid:x.sid,how:x.how,ign:x.ign}));
  }));
  _cache={songs:GM.songs.length,filas:F};return F;
};
EST.resumenCanciones=()=>{
  if(!EST.D.informes.length)return null;
  const M=new Map();
  EST.filas().forEach(r=>{if(!r.sid)return;const x=M.get(r.sid)||{n:0,e:{}};x.n+=r.n||0;if(r.e){x.e[r.u||'']=(x.e[r.u||'']||0)+r.e}M.set(r.sid,x)});
  return M;
};

/* ---------- ayudantes ---------- */
const mesSig=(m,d)=>{let [y,k]=m.split('-').map(Number);k+=d;while(k>12){k-=12;y++}while(k<1){k+=12;y--}return y+'-'+String(k).padStart(2,'0')};
const rango=(a,b)=>{const o=[];for(let m=a;m<=b&&o.length<600;m=mesSig(m,1))o.push(m);return o};
const money=(o)=>{const k=Object.keys(o).filter(c=>o[c]);return k.length?k.map(c=>fmtE(o[c])+(c?' '+c:'')).join(' + '):'—'};
const sum=(arr,f)=>arr.reduce((a,r)=>a+(f(r)||0),0);
function agrupa(F,clave,disp){const M=new Map();F.forEach(r=>{const k=clave(r);if(k==null||k==='')return;const x=M.get(k)||{k,d:disp?disp(r):k,n:0,e:0,m:{}};x.n+=r.n||0;x.e+=r.e||0;x.m[r.m]=(x.m[r.m]||{n:0,e:0});x.m[r.m].n+=r.n||0;x.m[r.m].e+=r.e||0;M.set(k,x)});return[...M.values()]}
function tendencia(serie,meses,met){ // last 3 months versus the 3 before
  if(meses.length<4)return null;const u=meses[meses.length-1];
  const v=i=>(serie[mesSig(u,-i)]||{})[met]||0,a=v(0)+v(1)+v(2),b=v(3)+v(4)+v(5);
  if(!a&&!b)return null;if(!b)return{nuevo:1};return{p:(a-b)/b*100};
}
const tendTxt=t=>!t?'<span class="meta">—</span>':t.nuevo?'<span class="est-up">nuevo</span>':`<span class="${t.p>=0?'est-up':'est-down'}">${t.p>=0?'▲':'▼'} ${Math.abs(Math.round(t.p))}%</span>`;

/* ---------- vista «Informes» ---------- */
EST.vistas.informes=(el)=>{
  const st=EST.S();st.inf=st.inf||{};const f=st.inf;
  if(EST.sub==='importar'&&EST.pintarImportar)return EST.pintarImportar(el);
  if(EST.sub==='resolver')return pintarResolver(el);
  const infs=EST.D.informes;
  if(!infs.length){
    el.innerHTML=`<div class="panel" style="text-align:center;padding:34px 24px">
      <div style="font-size:40px">📈</div><h2 style="margin:6px 0">Aún no has importado ningún informe</h2>
      <p class="lead" style="margin:0 auto 16px">Descarga el informe (CSV) que ofrece tu plataforma o tu distribuidora, impórtalo aquí y verás tus reproducciones e ingresos por canción, por álbum y por mes. El archivo se lee en tu equipo y no sale de él.</p>
      <button class="chip pri" id="est-imp">＋ Importar un informe CSV</button>
      <p class="meta" style="margin-top:14px">¿No sabes de dónde sacarlo? Mira la pestaña «Conexiones»: allí explico qué ofrece cada plataforma.</p></div>`;
    el.querySelector('#est-imp').onclick=()=>{EST.sub='importar';EST.imp=null;EST.pintar()};return;
  }
  const todas=EST.filas();
  const plats=[...new Map(todas.map(r=>[C.norm(r.p),r.p])).entries()].filter(x=>x[0]);
  const mons=[...new Set(todas.filter(r=>r.e).map(r=>r.u||''))];
  const monDef=mons.sort((a,b)=>sum(todas.filter(r=>(r.u||'')===b),r=>r.e)-sum(todas.filter(r=>(r.u||'')===a),r=>r.e))[0];
  const hayN=todas.some(r=>r.n),hayE=todas.some(r=>r.e);
  if(!f.met||(f.met==='e'&&!hayE)||(f.met==='n'&&!hayN&&hayE))f.met=hayN?'n':'e';
  if(f.mon==null||!mons.includes(f.mon))f.mon=monDef||'';
  const meses=[...new Set(todas.map(r=>r.m))].sort();
  let F=todas.filter(r=>(!f.plat||C.norm(r.p)===f.plat)&&(!f.inf||r.inf===f.inf)&&(!f.desde||r.m>=f.desde)&&(!f.hasta||r.m<=f.hasta));
  const met=f.met,val=r=>met==='n'?(r.n||0):((r.u||'')===f.mon?(r.e||0):0);
  const fmtV=v=>met==='n'?fmtN(v):fmtE(v)+(f.mon?' '+f.mon:'');
  const mesesF=[...new Set(F.map(r=>r.m))].sort(),ru=mesesF.length?rango(mesesF[0],mesesF[mesesF.length-1]):[];
  const porMes=agrupa(F,r=>r.m),mapaMes=Object.fromEntries(porMes.map(x=>[x.k,x]));
  const serieTot={};porMes.forEach(x=>{serieTot[x.k]={n:x.n,e:0}});
  F.forEach(r=>{if((r.u||'')===f.mon)serieTot[r.m].e=(serieTot[r.m].e||0)+(r.e||0)});
  const totN=sum(F,r=>r.n),totE={};F.forEach(r=>{if(r.e)totE[r.u||'']=(totE[r.u||'']||0)+r.e});
  const tt=tendencia(serieTot,ru,met);
  const sinCasar=F.filter(r=>!r.sid&&!r.ign);
  const claveSin=new Set(sinCasar.map(r=>C.norm(r.t))).size;
  const aprox=new Set(F.filter(r=>r.how==='parecido').map(r=>C.norm(r.t))).size;
  const bs=(arr)=>arr.sort((a,b)=>(met==='n'?b.n-a.n:b.e-a.e));

  /* per song and per album */
  const porCan=bs(agrupa(F.filter(r=>r.sid),r=>r.sid,r=>r.sid).map(x=>{x.m2=x.m;if(met==='e'){x.e=sum(F.filter(r=>r.sid===x.k&&(r.u||'')===f.mon),r=>r.e)}return x}));
  const sidAlb=new Map();GM.groups().forEach(g=>g.songs.forEach(s=>{if(!sidAlb.has(s.id)||g.kind==='album')sidAlb.set(s.id,g)}));
  const porAlb=bs(agrupa(F.filter(r=>r.sid&&sidAlb.has(r.sid)),r=>sidAlb.get(r.sid).key,r=>sidAlb.get(r.sid).title).map(x=>{if(met==='e'){x.e=sum(F.filter(r=>r.sid&&sidAlb.has(r.sid)&&sidAlb.get(r.sid).key===x.k&&(r.u||'')===f.mon),r=>r.e)}return x}));
  const porPlat=bs(agrupa(F,r=>C.norm(r.p),r=>r.p).map(x=>{if(met==='e'){x.e=sum(F.filter(r=>C.norm(r.p)===x.k&&(r.u||'')===f.mon),r=>r.e)}return x}));
  const porPais=bs(agrupa(F.filter(r=>r.c),r=>C.norm(r.c),r=>r.c).map(x=>{if(met==='e'){x.e=sum(F.filter(r=>C.norm(r.c)===x.k&&(r.u||'')===f.mon),r=>r.e)}return x}));
  const v=x=>met==='n'?x.n:x.e;
  const barras=(L,max,n=8)=>{const mx=Math.max(1,...L.map(v));return L.slice(0,n).map((x,i)=>`<div class="est-row"><span class="lab" title="${E(x.d)}">${E(x.d)}</span><div class="est-bar"><b style="width:${v(x)/mx*100}%;background:${COLORES[i%COLORES.length]}"></b></div><span class="meta" style="text-align:right">${fmtV(v(x))}</span></div>`).join('')};
  const filaT=(x,sid)=>{const s=sid?GM.song(x.k):null;const serie=ru.map(m=>((x.m[m]||{})[met]||0));
    return`<tr class="${sid?'go':''}"><td ${sid?`data-go="${E(x.k)}"`:''}>${E(sid?(s?GM.title(s):x.k):x.d)}</td><td class="r">${fmtN(x.n)}</td><td class="r">${met==='e'||hayE?fmtE(met==='e'?x.e:sum(F.filter(r=>(sid?r.sid===x.k:(sidAlb.get(r.sid)||{}).key===x.k)&&(r.u||'')===f.mon),r=>r.e)):'—'}</td><td>${EST.spark(serie)}</td><td class="r">${tendTxt(tendencia(x.m,ru,met))}</td></tr>`};
  const tabla=(L,sid,tit)=>L.length?`<table class="est-tbl"><thead><tr><th>${tit}</th><th class="r">Reproducciones</th><th class="r">Ingresos${f.mon?' ('+E(f.mon)+')':''}</th><th>Evolución</th><th class="r">Últimos 3 meses</th></tr></thead><tbody>${L.slice(0,sid?200:60).map(x=>filaT(x,sid)).join('')}</tbody></table>`:'<div class="empty" style="padding:18px">Sin datos para este filtro.</div>';

  el.innerHTML=`
   <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
     <button class="chip pri" id="est-imp">＋ Importar otro informe</button>
     ${claveSin?`<button class="chip" id="est-res" style="background:color-mix(in srgb,var(--warn) 30%,var(--panel2))">⚠ ${claveSin} título${claveSin>1?'s':''} sin casar · resolver</button>`:''}
     ${aprox?`<button class="chip" id="est-res2">🔎 Revisar ${aprox} casado${aprox>1?'s':''} por parecido</button>`:''}
   </div>
   <details class="est-falta" style="margin-bottom:14px"><summary><span class="n" style="background:var(--muted)">${infs.length}</span>Informes importados<span class="d">Pulsa para ver o quitar alguno</span></summary>
     <div style="padding:0 16px 14px">${infs.map(i=>`<div class="est-srow" style="grid-template-columns:1fr auto auto"><span class="tt" style="cursor:default"><b>${E(i.nombre)}</b> <span class="meta">· ${E(i.plataforma||'plataforma sin indicar')} · ${i.periodo?E(i.periodo[0])+' → '+E(i.periodo[1]):''} · ${(i.filas||[]).length} filas${i.perfil?' · perfil «'+E(i.perfil)+'»':''}</span></span><span class="meta">${E((i.importado||'').slice(0,10))}</span><button class="chip" data-del="${E(i.id)}">Quitar</button></div>`).join('')}</div></details>
   <div class="est-filt">
     <label>Ver <select class="est-in" id="f-met">${hayN?`<option value="n" ${met==='n'?'selected':''}>Reproducciones</option>`:''}${hayE?`<option value="e" ${met==='e'?'selected':''}>Ingresos</option>`:''}</select></label>
     ${met==='e'&&mons.length>1?`<label>Moneda <select class="est-in" id="f-mon">${mons.map(c=>`<option ${c===f.mon?'selected':''} value="${E(c)}">${E(c||'(sin indicar)')}</option>`).join('')}</select></label>`:''}
     <label>Plataforma <select class="est-in" id="f-plat"><option value="">Todas</option>${plats.map(([k,n])=>`<option value="${E(k)}" ${f.plat===k?'selected':''}>${E(n)}</option>`).join('')}</select></label>
     ${infs.length>1?`<label>Informe <select class="est-in" id="f-inf"><option value="">Todos</option>${infs.map(i=>`<option value="${E(i.id)}" ${f.inf===i.id?'selected':''}>${E(i.nombre)}</option>`).join('')}</select></label>`:''}
     <label>Desde <select class="est-in" id="f-desde"><option value="">el principio</option>${meses.map(m=>`<option ${f.desde===m?'selected':''} value="${m}">${EST.mesTxt(m,1)}</option>`).join('')}</select></label>
     <label>Hasta <select class="est-in" id="f-hasta"><option value="">el final</option>${meses.map(m=>`<option ${f.hasta===m?'selected':''} value="${m}">${EST.mesTxt(m,1)}</option>`).join('')}</select></label>
   </div>
   ${F.length?`
   <div class="est-kpis">
     ${hayN?`<div class="est-kpi"><div class="n">${fmtN(totN)}</div><div class="t">reproducciones</div></div>`:''}
     ${hayE?`<div class="est-kpi"><div class="n" style="font-size:${Object.keys(totE).length>1?18:30}px">${money(totE)}</div><div class="t">ingresos</div></div>`:''}
     <div class="est-kpi"><div class="n">${porCan.length}</div><div class="t">canciones con datos</div></div>
     <div class="est-kpi"><div class="n">${mesesF.length}</div><div class="t">meses (${mesesF.length?EST.mesTxt(mesesF[0]):''} → ${mesesF.length?EST.mesTxt(mesesF[mesesF.length-1]):''})</div></div>
     <div class="est-kpi"><div class="n" style="font-size:22px">${tendTxt(tt)}</div><div class="t">últimos 3 meses frente a los 3 anteriores</div></div>
   </div>
   <div class="panel est-panel" style="margin-bottom:16px"><h3>${met==='n'?'Reproducciones':'Ingresos'} por mes</h3>
     ${EST.barrasMes(ru.map(m=>({m,v:(serieTot[m]||{})[met]||0})),{c:met==='n'?'var(--accent)':'var(--good)',fmt:met==='n'?fmtN:(x=>fmtE(x)),unidad:met==='n'?' repro.':' '+f.mon})}</div>
   <div class="est-grid2">
     <div class="panel est-panel"><h3>Por plataforma</h3>${barras(porPlat)||''}</div>
     ${porPais.length?`<div class="panel est-panel"><h3>Por país</h3>${barras(porPais)}</div>`:`<div class="panel est-panel"><h3>Por álbum</h3>${barras(porAlb)||'<div class="meta">Sin datos casados con álbumes.</div>'}</div>`}
   </div>
   <h2>Por canción</h2><div class="panel">${tabla(porCan,true,'Canción')}</div>
   <h2>Por álbum, single o proyecto</h2><div class="panel">${tabla(porAlb,false,'Álbum')}</div>
   ${sinCasar.length?`<div class="callout" style="margin-top:16px">Hay ${claveSin} título${claveSin>1?'s':''} (${fmtN(sum(sinCasar,r=>r.n))} reproducciones) que no se han podido unir a ninguna canción y por eso no aparecen en «Por canción». Pulsa «resolver» arriba para asignarlos.</div>`:''}`
   :'<div class="empty">No hay filas con ese filtro.</div>'}`;
  const on=(id,fn)=>{const x=el.querySelector(id);if(x)x.onchange=()=>{fn(x.value);GM.save();EST.pintar()}};
  on('#f-met',x=>f.met=x);on('#f-mon',x=>f.mon=x);on('#f-plat',x=>f.plat=x);on('#f-inf',x=>f.inf=x);on('#f-desde',x=>f.desde=x);on('#f-hasta',x=>f.hasta=x);
  el.querySelector('#est-imp').onclick=()=>{EST.sub='importar';EST.imp=null;EST.pintar()};
  const rs=el.querySelector('#est-res');if(rs)rs.onclick=()=>{EST.sub='resolver';EST.soloAprox=false;EST.pintar()};
  const rs2=el.querySelector('#est-res2');if(rs2)rs2.onclick=()=>{EST.sub='resolver';EST.soloAprox=true;EST.pintar()};
  el.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{
    const i=infs.find(x=>x.id===b.dataset.del);
    if(!await GM.ui.ask('¿Quitar este informe?','Se borra «'+E(i.nombre)+'» solo de este módulo. El archivo CSV original no se toca.','Quitar'))return;
    const r=await GM.api('estado','informe_borrar',{id:i.id});if(!r.ok)return GM.ui.toast('No se pudo quitar: '+r.error);
    EST.D.informes=EST.D.informes.filter(x=>x.id!==i.id);EST.invalida();GM.ui.toast('Informe quitado');EST.pintar()});
  EST.enlazar(el);
};

/* ---------- resolve the unmatched ones ---------- */
function pintarResolver(el){
  const F=EST.filas(),soloAprox=!!EST.soloAprox;
  const G=new Map();
  F.filter(r=>soloAprox?r.how==='parecido':(!r.sid&&!r.ign)).forEach(r=>{
    const k=C.norm(r.t);const x=G.get(k)||{k,t:r.t,n:0,e:0,isrcs:new Set(),sid:r.sid,veces:0};x.n+=r.n||0;x.e+=r.e||0;x.veces++;if(r.i)x.isrcs.add(r.i.toUpperCase());G.set(k,x)});
  const L=[...G.values()].sort((a,b)=>b.n-a.n),songs=GM.songs.slice().sort((a,b)=>GM.title(a).localeCompare(GM.title(b),'es'));
  const sug=t=>{let m=null,b=0;songs.forEach(s=>{const p=C.parecido(t,GM.title(s));if(p>b){b=p;m=s}});return b>=.6?m:null};
  el.innerHTML=`<p><button class="chip" id="est-vol">← Volver a los informes</button></p>
   <h2 style="margin-top:0">${soloAprox?'Casados por parecido: ¿están bien?':'Títulos que no he podido casar'}</h2>
   <p class="lead">${soloAprox?'Estos títulos se parecen a una canción tuya (por ejemplo, con «Remastered» o «Radio Edit» detrás). Confirma o corrige.':'Elige a qué canción tuya corresponde cada título del informe. Lo que dejes en «ignorar» no se contará (por ejemplo, canciones de otra persona o que no tienes en el gestor). Se recuerda para los próximos informes.'}</p>
   ${L.length?`<div class="panel">${L.map((x,i)=>{const s=soloAprox?GM.song(x.sid):sug(x.t);return`<div class="est-res" data-k="${E(x.k)}">
      <div><b>${E(x.t)}</b><div class="meta">${fmtN(x.n)} repro.${x.e?' · '+fmtE(x.e)+' ingresos':''}${x.isrcs.size?' · ISRC '+E([...x.isrcs][0]):''}</div></div>
      <select class="est-in" data-i="${i}"><option value="">— elegir canción —</option><option value="-">🚫 Ignorar (no es mía / no está en el gestor)</option>${songs.map(z=>`<option value="${E(z.id)}" ${s&&s.id===z.id?'selected':''}>${E(GM.title(z))}</option>`).join('')}</select>
      <span class="meta">${s&&!soloAprox?'sugerencia':''}</span></div>`}).join('')}
     <div style="margin-top:14px;display:flex;gap:8px"><button class="chip pri" id="est-gua">Guardar</button><span class="meta" id="est-gm" style="align-self:center"></span></div></div>`
   :'<div class="empty">✓ No queda nada por resolver.</div>'}`;
  el.querySelector('#est-vol').onclick=()=>{EST.sub=null;EST.pintar()};
  const g=el.querySelector('#est-gua');if(!g)return;
  g.onclick=async()=>{
    const A=EST.D.alias;let n=0;
    el.querySelectorAll('select[data-i]').forEach(sel=>{
      const x=L[+sel.dataset.i];if(!sel.value)return;
      A.t[x.k]=sel.value;x.isrcs.forEach(i=>A.isrc[i]=sel.value);n++});
    const r=await GM.api('estado','alias_guardar',{alias:A});
    if(!r.ok)return GM.ui.toast('No se pudo guardar: '+r.error);
    EST.invalida();GM.ui.toast(n+' título'+(n===1?'':'s')+' guardado'+(n===1?'':'s'));
    EST.sub=null;EST.pintar()};
}
})();
