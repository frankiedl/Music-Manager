/* «historias»: what the author thought when writing each song, or what it is about. It is written on the song page and travels with the song
   in albums and mixtapes (the manager sends it when a mixtape is built). State: GM.state('historias').t[songId] = text. */
(function(){
const ID='historias',E=s=>GM.ui.esc(s==null?'':String(s));
const S=()=>{const st=GM.state(ID);if(!st.t)st.t={};return st};
const de=s=>(S().t[s.id]||'').trim();
GM.historia=de;

function editor(el,s){
  const v=S().t[s.id]||'';
  el.innerHTML=`<div class="hi-ed"><p class="meta">Escribe con tus palabras qué pensabas al escribirla o de qué trata. Saldrá al lado de la canción en los álbumes y los mixtapes, y quien descargue la canción se la lleva con la letra.</p>
   <textarea id="hi-t" rows="5" placeholder="Por ejemplo: la escribí una noche de invierno pensando en…">${E(v)}</textarea>
   <div class="meta" id="hi-s">${v.trim()?'Guardada':'Aún sin historia'}</div></div>`;
  const t=el.querySelector('#hi-t'),m=el.querySelector('#hi-s');let tm=null;
  const guardar=()=>{const x=t.value.trim();if(x)S().t[s.id]=x;else delete S().t[s.id];GM.save();m.textContent=x?'Guardada':'Aún sin historia'};
  t.oninput=()=>{m.textContent='Escribiendo…';clearTimeout(tm);tm=setTimeout(guardar,700)};
  t.onblur=()=>{clearTimeout(tm);guardar()};
}

function lista(el,g){
  const L=(g.songs||[]).filter(s=>!(GM.isDraft&&GM.isDraft(s)));
  const con=L.filter(s=>de(s)).length;
  el.innerHTML=`<div class="hi-alb"><p class="meta">${con} de ${L.length} canciones con su historia. Se escribe en la página de cada canción.</p>
   ${L.map((s,i)=>`<article class="hi-card"><div class="hi-n">${String(i+1).padStart(2,'0')}</div><div class="hi-b"><h3>${E(GM.title(s))}</h3>${de(s)?`<p>${E(de(s))}</p>`:`<p class="mut">Aún sin historia.</p>`}</div></article>`).join('')}</div>`;
}

GM.register({id:ID,
  songSection:{title:'Su historia',order:20,render(el,s){editor(el,s)}},
  albumTab:{id:'historias',label:'Historias',render(el,g){lista(el,g)}}});
})();
