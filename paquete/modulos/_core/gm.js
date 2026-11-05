/* Núcleo de módulos del gestor (cliente). Lo comparten el gestor personal y el paquete distribuible.
   Cada módulo se registra con GM.register({...}). Ejemplo completo en modulos/_plantilla/modulo.js.

   GM.register({
     id:'miModulo',
     songAction:{label:'Mi acción',icon:'🎚',run(song,GM){}},
     mixtapeAction:{label:'Mi acción',icon:'🎚',run(mixtape,GM){}},   // botón en la página de cada mixtape (opcional)        // botón en la ficha y en el menú de cada canción (opcional)
     nav:{label:'Mi sección', icon:'🎛'},                       // añade un botón al menú lateral (opcional)
     render(el,GM){ el.innerHTML='...' },                        // pinta esa sección en #main
     albumTab:{id:'tab', label:'Mi pestaña', render(el,g,GM){}}, // pestaña extra en la página de cada álbum (opcional)
     init(GM){}                                                  // se llama al registrarse (opcional)
   })
*/
window.GM=(()=>{
  const mods={},albTabs=[],navs=[],songActs=[],mixActs=[],homeSecs=[],ev={};
  const M={
    mods,
    register(m){
      if(!m||!m.id)throw new Error('módulo sin id');
      mods[m.id]=m;if(m.nav)navs.push(m);
      if(m.songAction)songActs.push({mod:m.id,...m.songAction});
      if(m.mixtapeAction)mixActs.push({mod:m.id,...m.mixtapeAction});
      if(m.home)homeSecs.push({mod:m.id,...m.home});   // sección dentro de Inicio: home:{title,render(el,GM)}
      if(m.albumTab)albTabs.push({mod:m.id,id:m.albumTab.id||'tab',label:m.albumTab.label||m.id,render:m.albumTab.render});
      if(m.init){try{m.init(M)}catch(e){console.error('módulo',m.id,e)}}
    },
    /* Motor del navegador (opcional): un módulo puede traer su versión en JavaScript de una ruta, para que funcione sin agente local
       en navegadores que dejan trabajar con carpetas del equipo (Chrome, Edge).  GM.handle('miModulo','guardar',async body=>({ok:true}))
       Solo se usa cuando GM.modoNavegador es true; si no hay versión en JS, se llama al agente local. */
    modoNavegador:false,handlers:{},
    handle(mod,ruta,fn){M.handlers[mod+'/'+ruta]=fn},
    /* llamar al servidor del módulo:  GM.api('miModulo','estado')  ·  GM.api('miModulo','guardar',{...})  ·  GM.api('miModulo','subir?id=1',archivo) */
    api(mod,ruta,body){
      const loc=M.handlers[mod+'/'+ruta.split('?')[0]];
      if(M.modoNavegador&&loc)return Promise.resolve(loc(body,ruta));
      const raw=body instanceof Blob||body instanceof ArrayBuffer;
      return fetch('/api/mod/'+mod+'/'+ruta,{method:body===undefined?'GET':'POST',body:body===undefined?undefined:(raw?body:JSON.stringify(body))}).then(r=>r.json());
    },
    /* como api(), pero devuelve un Blob (audio, imágenes, archivos). Usa esto en vez de fetch directo: así funciona también en modo web con token. */
    apiBlob(mod,ruta,body){
      const raw=body instanceof Blob||body instanceof ArrayBuffer;
      return fetch('/api/mod/'+mod+'/'+ruta,{method:body===undefined?'GET':'POST',body:body===undefined?undefined:(raw?body:JSON.stringify(body))}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.blob()});
    },
    /* estado propio del módulo, guardado con el resto de tu trabajo (estado.json) */
    state(id){ST.mod=ST.mod||{};return ST.mod[id]||(ST.mod[id]={})},
    save(){save()},
    on(e,f){(ev[e]=ev[e]||[]).push(f)},
    emit(e,d){(ev[e]||[]).forEach(f=>{try{f(d)}catch(x){console.error(x)}})},
    /* lo que ya sabe el gestor */
    get songs(){return SONGS},          // canciones visibles (sin las ocultas)
    get all(){return ALL},
    groups:()=>groups(),                // álbumes, singles, pre-released y proyectos
    mixtapes:()=>MIXS(),                // los mixtapes (objetos vivos: id, name, kbps, items:[{id,p}]…); tras cambiarlos llama a GM.mixSave()
    mixSave(){save();refresh()},
    mixCover:(m,size)=>mixCoverUrl(m,size||1200),   // portada de casete de un mixtape como dataURL JPEG (para incrustarla en pistas o másters)
    mixCopy:m=>mixCopy(m),               // texto © del mixtape («© nombre año»)
    order:g=>groupOrder(g),             // las canciones de un álbum/grupo en su orden (el que tú le diste)
    song:id=>ALL.find(s=>s.id===id),
    isDraft:s=>isDraft(s),
    bestVersion:s=>bestVersion(s),      // ruta de la mejor versión (o null)
    finalPath:s=>finalPath(s),
    cover:s=>coverOf(s),
    title:s=>clean(s.title),
    dir:s=>D(s),                        // carpeta de la canción, con «/»
    audioUrl:p=>'/audio?p='+encodeURIComponent(p),
    thumbUrl:c=>c&&c.t?'/thumb?f='+encodeURIComponent(c.t):'',   // miniatura de una portada (el objeto que devuelve GM.cover)
    cfg:{artista:'',titular:''},        // nombre artístico y titular, si el gestor los conoce (se rellena al cargar)
    lyrics:id=>(typeof LET!=='undefined'&&LET[id])?LET[id].t:'',
    ui:{
      toast:m=>toast(m),modal:(h,f)=>modal(h,f),ask:(t,x,o)=>ask(t,x,o),esc:s=>esc(s),
      go:(v,a)=>go(v,a),refresh:()=>refresh(),
      reload:()=>refreshAll(),            // vuelve a leer las carpetas (como el botón Actualizar)
      setDraft:(ids,on)=>setDraft(ids.map(i=>ALL.find(z=>z.id===i)).filter(Boolean),on),   // marca/quita «boceto» a varias canciones por id
    },
    navs:()=>navs,albumTabs:()=>albTabs,songActions:()=>songActs,mixtapeActions:()=>mixActs,homeSections:()=>homeSecs,
    async load(){
      try{const c=await fetch('/api/config').then(r=>r.ok?r.json():{});Object.assign(M.cfg,c||{})}catch{}
      const L=await fetch('/api/modulos').then(r=>r.json()).catch(()=>[]);
      for(const m of L){
        (m.css||[]).forEach(f=>{const l=document.createElement('link');l.rel='stylesheet';l.href='/mod/'+m.id+'/'+f;document.head.appendChild(l)});
        for(const f of (m.js||[]))await new Promise(res=>{const s=document.createElement('script');s.src='/mod/'+m.id+'/'+f;s.onload=s.onerror=res;document.head.appendChild(s)});
      }
    },
    renderView(id){
      const m=mods[id],el=document.getElementById('main');
      if(m&&m.render)m.render(el,M);else el.innerHTML='<div class="empty">Este módulo no está disponible.</div>';
    },
  };
  return M;
})();
