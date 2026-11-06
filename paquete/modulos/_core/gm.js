/* Module core of the manager (client side). Shared by the personal manager and the distributable package.
   Each module registers itself with GM.register({...}). Full example in modulos/_plantilla/modulo.js.

   GM.register({
     id:'miModulo',
     songAction:{label:'Mi acción',icon:'🎚',run(song,GM){}},          // button on the song page and in each song's menu (optional)
     mixtapeAction:{label:'Mi acción',icon:'🎚',run(mixtape,GM){}},    // button on each mixtape's page (optional)
     nav:{label:'Mi sección', icon:'🎛'},                       // adds a button to the side menu (optional)
     render(el,GM){ el.innerHTML='...' },                        // draws that section into #main
     albumTab:{id:'tab', label:'Mi pestaña', render(el,g,GM){}}, // extra tab on each album page (optional)
     songSection:{title:'Mi sección', render(el,song,GM){}},    // extra section on each song page (optional)
     badges(song,GM){return '<span class="b">…</span>'},       // small badges on the song cards (optional)
     tasks(GM){return [{k:'miFiltro',ic:'⚑',n:3,t:'…',d:'…'}]},  // cards in Pending; k = the id of one of your filters (optional)
     filters:[{k:'miFiltro',label:'…',fn:song=>true,pend:false}], // extra song filters; pend:true = also counts as «something pending» (optional)
     init(GM){}                                                  // called on registration (optional)
   })
   Labels are written in Spanish: the runtime translator (i18n.js) shows them in the user's language.
*/
window.GM=(()=>{
  const mods={},albTabs=[],navs=[],songActs=[],mixActs=[],homeSecs=[],songSecs=[],ev={};
  const M={
    mods,
    register(m){
      if(!m||!m.id)throw new Error('módulo sin id');
      mods[m.id]=m;if(m.nav)navs.push(m);
      if(m.songAction)songActs.push({mod:m.id,...m.songAction});
      if(m.mixtapeAction)mixActs.push({mod:m.id,...m.mixtapeAction});
      if(m.home)homeSecs.push({mod:m.id,...m.home});   // section inside Home: home:{title,render(el,GM)}
      if(m.songSection)songSecs.push({mod:m.id,...m.songSection});
      if(m.albumTab)albTabs.push({mod:m.id,id:m.albumTab.id||'tab',label:m.albumTab.label||m.id,render:m.albumTab.render});
      if(m.init){try{m.init(M)}catch(e){console.error('módulo',m.id,e)}}
    },
    /* Browser engine (optional): a module can bring a JavaScript version of a route, so it works without the local agent
       in browsers that allow working with local folders (Chrome, Edge).  GM.handle('miModulo','guardar',async body=>({ok:true}))
       Only used when GM.modoNavegador is true; if there is no JS version, the local agent is called. */
    modoNavegador:false,handlers:{},
    handle(mod,ruta,fn){M.handlers[mod+'/'+ruta]=fn},
    /* call the module's server:  GM.api('miModulo','estado')  ·  GM.api('miModulo','guardar',{...})  ·  GM.api('miModulo','subir?id=1',file) */
    api(mod,ruta,body){
      const loc=M.handlers[mod+'/'+ruta.split('?')[0]];
      if(M.modoNavegador&&loc)return Promise.resolve(loc(body,ruta));
      const raw=body instanceof Blob||body instanceof ArrayBuffer;
      return fetch('/api/mod/'+mod+'/'+ruta,{method:body===undefined?'GET':'POST',body:body===undefined?undefined:(raw?body:JSON.stringify(body))}).then(r=>r.json());
    },
    /* like api(), but returns a Blob (audio, images, files). Use this instead of a direct fetch: that way it also works in web mode with a token. */
    apiBlob(mod,ruta,body){
      const raw=body instanceof Blob||body instanceof ArrayBuffer;
      return fetch('/api/mod/'+mod+'/'+ruta,{method:body===undefined?'GET':'POST',body:body===undefined?undefined:(raw?body:JSON.stringify(body))}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.blob()});
    },
    /* the module's own state, saved with the rest of your work (estado.json) */
    state(id){ST.mod=ST.mod||{};return ST.mod[id]||(ST.mod[id]={})},
    save(){save()},
    on(e,f){(ev[e]=ev[e]||[]).push(f)},
    emit(e,d){(ev[e]||[]).forEach(f=>{try{f(d)}catch(x){console.error(x)}})},
    /* what the manager already knows */
    get songs(){return SONGS},          // visible songs (without the hidden ones)
    get all(){return ALL},
    groups:()=>groups(),                // albums, singles, pre-released and projects
    mixtapes:()=>MIXS(),                // the mixtapes (live objects: id, name, kbps, items:[{id,p}]…); after changing them call GM.mixSave()
    mixSave(){save();refresh()},
    mixCover:(m,size)=>mixCoverUrl(m,size||1200),   // a mixtape's cassette cover as a JPEG dataURL (to embed it into tracks or masters)
    mixCopy:m=>mixCopy(m),               // the mixtape's © text («© name year»)
    order:g=>groupOrder(g),             // the songs of an album/group in their order (the one you gave it)
    song:id=>ALL.find(s=>s.id===id),
    isDraft:s=>isDraft(s),
    bestVersion:s=>bestVersion(s),      // path of the best version (or null)
    finalPath:s=>finalPath(s),
    cover:s=>coverOf(s),
    title:s=>clean(s.title),
    dir:s=>D(s),                        // song folder, with «/»
    audioUrl:p=>'/audio?p='+encodeURIComponent(p),
    thumbUrl:c=>c&&c.t?'/thumb?f='+encodeURIComponent(c.t):'',   // thumbnail of a cover (the object returned by GM.cover)
    cfg:{artista:'',titular:''},        // artist name and copyright owner, if the manager knows them (filled in on load)
    lyrics:id=>(typeof LET!=='undefined'&&LET[id])?LET[id].t:'',
    ui:{
      toast:m=>toast(m),modal:(h,f)=>modal(h,f),ask:(t,x,o)=>ask(t,x,o),esc:s=>esc(s),
      go:(v,a)=>go(v,a),refresh:()=>refresh(),
      reload:()=>refreshAll(),            // re-reads the folders (like the Refresh button)
      setDraft:(ids,on)=>setDraft(ids.map(i=>ALL.find(z=>z.id===i)).filter(Boolean),on),   // marks/unmarks «boceto» (sketch) on several songs by id
    },
    navs:()=>navs,albumTabs:()=>albTabs,songActions:()=>songActs,mixtapeActions:()=>mixActs,homeSections:()=>homeSecs,songSections:()=>songSecs,
    badges(s){return Object.values(mods).map(m=>{try{return m.badges?m.badges(s,M)||'':''}catch(e){return ''}}).join('')},
    tasks(){return Object.values(mods).flatMap(m=>{try{return m.tasks?m.tasks(M)||[]:[]}catch(e){console.error(e);return []}})},
    filters(){return Object.values(mods).flatMap(m=>(m.filters||[]).map(f=>({mod:m.id,...f})))},
    /* release status chosen by the user (overrides the folder): 'pub' | 'pre' | 'un' | '' (= decided by the folder) */
    release:id=>(ST.release&&ST.release[id])||'',
    setRelease(id,v){ST.release=ST.release||{};if(v)ST.release[id]=v;else delete ST.release[id];save()},
    isPub:s=>isPub(s),isPre:s=>isPre(s),

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
