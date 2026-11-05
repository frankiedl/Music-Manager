/* Traductor en tiempo de ejecución del gestor (es → en · de · pt). Se carga ANTES de gm.js.
   No reescribe las pantallas: observa el DOM y traduce los textos de la interfaz que estén en el diccionario
   modulos/_core/idiomas/<xx>.json  {"exactas":{"texto":"traducción"},"patrones":[["{n} canciones","{n} songs"]]}.
   Lo que no está en el diccionario (títulos, letras, nombres de carpetas…) se queda tal cual.
   API: window.T('texto') · GM.idioma · GM.setIdioma('en')  ·  ?lang=xx en la URL para probar. */
(()=>{
const LANGS=['es','en','de','pt'],KEY='gm_idioma';
const NOMBRES={es:'Español',en:'English',de:'Deutsch',pt:'Português'};
let lang='es',EX=Object.create(null),PAT=[];
const cache=new Map(),orig=new WeakMap();   // orig: nodo o elemento → {txt|attr:valor original}
const ATTRS=['placeholder','title','aria-label','alt'];
const SKIP={SCRIPT:1,STYLE:1,TEXTAREA:1,NOSCRIPT:1,CODE:1,PRE:1};
const tieneLetras=/[A-Za-zÀ-ÿ]/;

function elegir(){
  let q=null;try{q=new URLSearchParams(location.search).get('lang')}catch{}
  if(q&&LANGS.includes(q.slice(0,2).toLowerCase())){q=q.slice(0,2).toLowerCase();try{localStorage.setItem(KEY,q)}catch{}return q}
  try{const s=localStorage.getItem(KEY);if(LANGS.includes(s))return s}catch{}
  const n=((navigator.language||navigator.userLanguage||'en')+'').slice(0,2).toLowerCase();
  return LANGS.includes(n)?n:'en'}

function cargar(l){
  EX=Object.create(null);PAT=[];cache.clear();
  if(l==='es')return;
  try{
    const x=new XMLHttpRequest();x.open('GET','/mod/_core/idiomas/'+l+'.json',false);x.send();   // síncrono: evita el parpadeo en español
    if(x.status!==200)return;
    const d=JSON.parse(x.responseText);
    Object.assign(EX,d.exactas||{});
    for(const [es,tr] of (d.patrones||[])){
      const partes=es.split(/\{(\w+)\}/),nombres=[];let re='';
      partes.forEach((p,i)=>{if(i%2){nombres.push(p);
        /* un marcador pegado a una letra («Letra{j}», «canción{b}») solo admite sufijos cortos: «s», « (3)», «, Ana» */
        const pegado=(i>0&&/[A-Za-zÀ-ÿ]$/.test(partes[i-1]))||(i<partes.length-1&&/^[A-Za-zÀ-ÿ]/.test(partes[i+1]));
        re+=pegado?'(\\s?\\([^)]*\\)|[^\\s]{0,3}|,\\s\\S+|[\\d\\s·.,%x\\-]*)':'([\\s\\S]+?)'}
      else re+=p.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')});
      try{PAT.push({re:new RegExp('^'+re+'$'),nombres,tr,lit:partes.filter((p,i)=>!(i%2)).join('').length})}catch{}}
    PAT.sort((a,b)=>b.lit-a.lit);   // primero los más específicos
  }catch(e){console.warn('i18n: no se pudo cargar el diccionario',l,e)}}

function buscar(core,prof){
  let r=EX[core];if(r!==undefined)return r;
  for(const p of PAT){const q=p.re.exec(core);if(q){const v={};p.nombres.forEach((n,i)=>{if(!(n in v))v[n]=q[i+1]});
    return p.tr.replace(/\{(\w+)\}/g,(_,n)=>{if(!(n in v))return '{'+n+'}';const x=v[n];return (prof||0)<2?(parte(x,(prof||0)+1)):x})}}}
/* traduce un trozo (valor capturado o segmento): exacta, o sin emojis/puntuación en los extremos */
function parte(x,prof){
  const m=/^(\s*)([\s\S]*?)(\s*)$/.exec(x),c=m[2].replace(/\s+/g,' ');if(!c||!tieneLetras.test(c))return x;
  let r=buscar(c,prof);
  if(r===undefined){const q=/^([^\wÀ-ÿ¿¡«{]*)([\s\S]*?)([\s….:,;·→]*)$/.exec(c);if(q[2]&&(q[1]||q[3])){const t=buscar(q[2],prof);if(t!==undefined)r=q[1]+t+q[3]}}
  return r===undefined?x:m[1]+r+m[3]}
const SEP=/(\s+·\s+|\s+—\s+|[.;:]\s+|,\s+|\s+\(|\)\s+)/;
function porTrozos(c){   // último recurso: traduce cada trozo de una frase compuesta que sí esté en el diccionario
  const t=c.split(SEP);if(t.length<3)return undefined;
  let hay=false;const o=t.map((x,i)=>{if(i%2||!x)return x;const y=parte(x,0);if(y!==x)hay=true;return y});
  return hay?o.join(''):undefined}
function trad(s){   // traduce una cadena conservando los espacios y los signos/emojis de los extremos
  if(lang==='es'||!s||!tieneLetras.test(s))return s;
  const m=/^(\s*)([\s\S]*?)(\s*)$/.exec(s),core=m[2].replace(/\s+/g,' ');
  let r=cache.get(core);
  if(r===undefined){
    r=buscar(core,0);
    if(r===undefined){
      const q=/^([^\wÀ-ÿ¿¡«{]*)([\s\S]*?)([\s….:,;·→]*)$/.exec(core);
      if(q[2]&&(q[1]||q[3])){const t=buscar(q[2],0);if(t!==undefined)r=q[1]+t+q[3]}}
    if(r===undefined)r=porTrozos(core);
    if(r===undefined)r=null;
    if(cache.size>30000)cache.clear();
    cache.set(core,r)}
  return r===null?s:m[1]+r+m[3]}

function ignorado(el){for(;el&&el.nodeType===1;el=el.parentNode){if(SKIP[el.tagName]||el.isContentEditable||el.classList.contains('notr')||el.getAttribute('translate')==='no')return true}return false}

function nodoTexto(n){
  if(ignorado(n.parentNode))return;
  const o=orig.get(n),v=n.nodeValue;
  if(o&&v===o.out)return;                 // ya traducido
  const t=trad(v);
  if(t!==v){orig.set(n,{txt:v,out:t});n.nodeValue=t}else if(o)orig.delete(n)}

function atributos(el){
  if(el.nodeType!==1||SKIP[el.tagName])return;
  for(const a of ATTRS){if(!el.hasAttribute(a))continue;attr(el,a)}
  if(el.tagName==='INPUT'&&/^(button|submit|reset)$/i.test(el.type))attr(el,'value')}
function attr(el,a){
  const v=el.getAttribute(a),k='@'+a,o=orig.get(el)||{};
  if(o[k]&&v===o[k].out)return;
  const t=trad(v);
  if(t!==v){o[k]={txt:v,out:t};orig.set(el,o);el.setAttribute(a,t)}else if(o[k]){delete o[k]}}

function recorrer(raiz){
  if(!raiz)return;
  if(raiz.nodeType===3){nodoTexto(raiz);return}
  if(raiz.nodeType!==1&&raiz.nodeType!==9)return;
  if(raiz.nodeType===1){if(SKIP[raiz.tagName])return;atributos(raiz)}
  const w=document.createTreeWalker(raiz,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT,{acceptNode:n=>n.nodeType===1&&SKIP[n.tagName]?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
  let n;while((n=w.nextNode())){if(n.nodeType===3)nodoTexto(n);else atributos(n)}}

let obs=null;
function observar(){
  if(obs)return;
  obs=new MutationObserver(recs=>{
    for(const r of recs){
      if(r.type==='childList')r.addedNodes.forEach(recorrer);
      else if(r.type==='characterData')nodoTexto(r.target);
      else if(r.type==='attributes'){const el=r.target;if(r.attributeName==='value'){if(el.tagName==='INPUT'&&/^(button|submit|reset)$/i.test(el.type))attr(el,'value')}else attr(el,r.attributeName)}}
    obs.takeRecords()});    // descarta lo que provocan nuestras propias escrituras
  obs.observe(document.documentElement,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:[...ATTRS,'value']})}

/* cambio de idioma al instante: restaura los originales y vuelve a traducir */
function restaurar(raiz){
  const w=document.createTreeWalker(raiz,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);let n;
  while((n=w.nextNode())){
    const o=orig.get(n);if(!o)continue;
    if(n.nodeType===3){if(n.nodeValue===o.out)n.nodeValue=o.txt}
    else for(const k in o){const a=k.slice(1);if(n.getAttribute(a)===o[k].out)n.setAttribute(a,o[k].txt)}
    orig.delete(n)}}

function aplicar(){
  document.documentElement.lang=lang;
  recorrer(document);
  if(obs)obs.takeRecords()}

function setIdioma(l){
  if(!LANGS.includes(l))return;
  if(obs)obs.disconnect();obs=null;
  restaurar(document);
  lang=l;try{localStorage.setItem(KEY,l)}catch{}
  cargar(l);if(window.GM)GM.idioma=l;
  aplicar();observar();
  try{window.dispatchEvent(new CustomEvent('gm-idioma',{detail:l}))}catch{}}

/* alert/confirm/prompt nativos */
for(const f of ['alert','confirm','prompt']){const o=window[f];window[f]=function(m,...r){return o.call(window,trad(String(m??'')),...r)}}

lang=elegir();cargar(lang);
{const f0=window.fetch;window.fetch=function(u,o){try{if(typeof u==='string'&&u.startsWith('/api/')){o=Object.assign({},o);const h=new Headers(o.headers||{});h.set('X-Lang',lang);o.headers=h}}catch{}return f0.call(this,u,o)}}

window.T=s=>trad(String(s??''));
window.GM_I18N={langs:LANGS,nombres:NOMBRES,get idioma(){return lang},setIdioma};
function listo(){
  if(window.GM){GM.idioma=lang;GM.idiomas=NOMBRES;GM.setIdioma=setIdioma}
  aplicar();observar()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',listo);else listo();
/* el documento ya existe parcialmente: empieza a observar desde ya para no dejar pasar nada */
if(lang!=='es'){document.documentElement.lang=lang;observar()}
})();
