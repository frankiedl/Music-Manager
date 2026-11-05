/* Módulo «masterizado» — pestaña «Masterización» en cada álbum.
   Basado en el editor de masterizado independiente (Web Audio): mide la sonoridad (LUFS, BS.1770 / EBU R128),
   iguala el volumen, limita los picos, recorta, pone fundidos y silencios, escribe etiquetas ID3/RIFF + carátula
   y exporta WAV (ZIP o carpeta master/ de cada canción). Todo el audio se procesa en el navegador; ver NOTAS.md. */
(function(){
'use strict';
const ID='masterizado';
const ESTADOS=['Borrador','Mezcla','Masterización','Listo para distribuir'];
const OBJETIVOS=[[-14,'-14 LUFS · Streaming (Spotify, YouTube, Apple Music)'],[-16,'-16 LUFS · Más suave (podcast)'],[-12,'-12 LUFS · Más fuerte'],[-9,'-9 LUFS · Lo más fuerte posible'],[-23,'-23 LUFS · Radio y TV (EBU R128)']];
const TECHOS=[[-1,'-1,0 dB · recomendado para distribuir'],[-0.3,'-0,3 dB'],[-2,'-2,0 dB · prudente'],[0,'0 dB · sin techo']];
const IDIOMAS=[['','— Elige idioma —'],['spa','Español'],['eng','Inglés'],['por','Portugués'],['fra','Francés'],['deu','Alemán'],['ita','Italiano'],['cat','Catalán'],['glg','Gallego'],['eus','Euskera'],['nld','Neerlandés'],['swe','Sueco'],['nor','Noruego'],['dan','Danés'],['fin','Finés'],['pol','Polaco'],['ces','Checo'],['hun','Húngaro'],['ron','Rumano'],['ell','Griego'],['rus','Ruso'],['ukr','Ucraniano'],['tur','Turco'],['ara','Árabe'],['heb','Hebreo'],['hin','Hindi'],['jpn','Japonés'],['kor','Coreano'],['zho','Chino (mandarín)'],['vie','Vietnamita'],['ind','Indonesio'],['swa','Suajili'],['lat','Latín'],['zxx','Instrumental (sin letra)']];
const GENEROS=['Acústico','Alternativo','Ambient','Blues','Bossa nova','Clásica','Country','Dance','Disco','Drum and Bass','Electrónica','Experimental','Flamenco','Folk','Funk','Hip Hop','House','Indie','Jazz','Latino','Lo-fi','Metal','Pop','Pop rock','Punk','R&B','Rap','Reggae','Reggaeton','Rock','Rumba','Salsa','Singer-songwriter','Soul','Synthpop','Techno','Trap','Trance','Trip Hop','Banda sonora','Música del mundo'];
/* nombre de la etiqueta (en español o inglés) → fotograma ID3 */
const ID3_META={compositor:'TCOM',composer:'TCOM',copyright:'TCOP',editorial:'TPUB',publisher:'TPUB',sello:'TPUB',label:'TPUB',isrc:'TSRC',bpm:'TBPM',letrista:'TEXT',lyricist:'TEXT',director:'TPE3',conductor:'TPE3',remezclador:'TPE4',remixer:'TPE4',disco:'TPOS',disc:'TPOS','número de disco':'TPOS',ánimo:'TMOO',animo:'TMOO',mood:'TMOO',tonalidad:'TKEY',key:'TKEY',web:'WXXX_',website:'WXXX_'};
const INFO_META={comentario:'ICMT',comment:'ICMT',copyright:'ICOP',ingeniero:'IENG',engineer:'IENG','técnico':'IENG',technician:'IENG',productor:'IENG'};
const CLAVES_META=['Compositor','Letrista','Productor','Mezclador','Ingeniero','Editorial','Sello','Copyright','ISRC','BPM','Tonalidad','Ánimo','Director','Remezclador','Disco','Comentario','Web'];
const pista0=()=>({name:null,artist:'',trimStart:0,trimEnd:null,fadeIn:0,fadeOut:0,padStart:0,padEnd:0,previewNorm:false,meta:[]});
/* EFECTOS DESACTIVADOS (decisión del usuario): el código del panel FX1…FX5, del motor en directo y del módulo vst se conserva para retomarlo; poner true lo reactiva. Ver NOTAS.md. */
const FX_ACTIVO=false;
const ajustes0=()=>({estado:'Borrador',modo:'pista',lufs:-14,techo:-1,bits:24,dither:true,artista:'',anio:'',genero:'',idioma:'',portada:true,fuera:[],pistas:{},fx:{on:false,cadena:[],porPista:{}},mixMasters:{},origMix:{}});

/* ================= utilidades ================= */
/* ceder el hilo: con MessageChannel no se frena aunque la pestaña esté en segundo plano */
const _mc=new MessageChannel();let _esp=[];_mc.port1.onmessage=()=>{const w=_esp;_esp=[];w.forEach(f=>f())};
const ceder=()=>new Promise(r=>{_esp.push(r);_mc.port2.postMessage(0)});
const clamp=(v,a,b)=>v<a?a:(v>b?b:v);
const dbALin=db=>Math.pow(10,db/20);
const E=s=>GM.ui.esc(s==null?'':String(s));
const A=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
const num=(x,d=1)=>(x==null||!isFinite(x))?'—':x.toFixed(d).replace('.',',');
const tiempo=s=>{if(!isFinite(s)||s<0)s=0;const m=Math.floor(s/60),x=Math.floor(s%60);return m+':'+String(x).padStart(2,'0')};
const nombreSeguro=s=>String(s).replace(/[\\/:*?"<>|\x00-\x1f]/g,'_').replace(/^[ .]+|[ .]+$/g,'').trim()||'pista';
const SVG={
  play:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5v14l12-7z"/></svg>',
  pausa:'<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14"/><rect x="14" y="5" width="4" height="14"/></svg>',
  ant:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h2v14H6zM20 5v14l-11-7z"/></svg>',
  sig:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 5h2v14h-2zM4 5l11 7-11 7z"/></svg>',
  atras:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/></svg>',
  adel:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg>',
  chev:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>',
  x:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
};

/* ================= LECTURA DE AUDIO ================= */
/* WAV sin pérdidas: conserva frecuencia de muestreo y profundidad originales */
function leerWav(buf){
  const dv=new DataView(buf),u8=new Uint8Array(buf);
  const tag=i=>String.fromCharCode(u8[i],u8[i+1],u8[i+2],u8[i+3]);
  if(u8.length<44||tag(0)!=='RIFF'||tag(8)!=='WAVE')throw new Error('No es un WAV');
  let pos=12,fmt=null,dOff=0,dLen=0;
  while(pos+8<=dv.byteLength){
    const id=tag(pos),size=dv.getUint32(pos+4,true),body=pos+8;
    if(id==='fmt '){
      let af=dv.getUint16(body,true);
      const canales=dv.getUint16(body+2,true),sr=dv.getUint32(body+4,true),bits=dv.getUint16(body+14,true);
      if(af===0xFFFE&&size>=40)af=dv.getUint16(body+24,true);
      fmt={af,canales,sr,bits};
    }else if(id==='data'){dOff=body;dLen=Math.min(size,dv.byteLength-body)}
    pos=body+size+(size&1);
  }
  if(!fmt||!dOff)throw new Error('WAV incompleto');
  const {af,canales,sr,bits}=fmt,esFloat=af===3;
  if(!(af===1||af===3)||!canales||!sr)throw new Error('Formato WAV no compatible');
  const bps=bits/8,fs=bps*canales,n=Math.floor(dLen/fs);
  const ch=Array.from({length:canales},()=>new Float32Array(n));
  if(esFloat&&bits===32){for(let f=0;f<n;f++){const b=dOff+f*fs;for(let c=0;c<canales;c++)ch[c][f]=dv.getFloat32(b+c*4,true)}}
  else if(bits===16){for(let f=0;f<n;f++){const b=dOff+f*fs;for(let c=0;c<canales;c++)ch[c][f]=dv.getInt16(b+c*2,true)/32768}}
  else if(bits===24){for(let f=0;f<n;f++){const b=dOff+f*fs;for(let c=0;c<canales;c++){const o=b+c*3;let v=u8[o]|(u8[o+1]<<8)|(u8[o+2]<<16);if(v&0x800000)v|=~0xFFFFFF;ch[c][f]=v/8388608}}}
  else if(bits===32){for(let f=0;f<n;f++){const b=dOff+f*fs;for(let c=0;c<canales;c++)ch[c][f]=dv.getInt32(b+c*4,true)/2147483648}}
  else if(bits===8){for(let f=0;f<n;f++){const b=dOff+f*fs;for(let c=0;c<canales;c++)ch[c][f]=(u8[b+c]-128)/128}}
  else throw new Error('Profundidad no compatible: '+bits+' bits');
  return {sampleRate:sr,bits,float:esFloat,channels:canales,length:n,ch,decodificado:false};
}
/* Cualquier otro formato (MP3, FLAC, M4A, AIFF…): lo decodifica el navegador a 44,1 kHz en coma flotante.
   Es una fuente «float»: se exporta igualmente a los bits que elijas, pero a 44,1 kHz. */
let ACD=null;
async function decodificar(buf){
  const AC=window.AudioContext||window.webkitAudioContext;
  if(!ACD)ACD=new AC({sampleRate:44100});
  const ab=await ACD.decodeAudioData(buf);
  const ch=[];for(let c=0;c<ab.numberOfChannels;c++)ch.push(new Float32Array(ab.getChannelData(c)));
  return {sampleRate:ab.sampleRate,bits:null,float:true,channels:ab.numberOfChannels,length:ab.length,ch,decodificado:true};
}
async function leerAudio(buf){
  try{return leerWav(buf)}catch(e){/* no es un WAV normal: lo decodifica el navegador */}
  return decodificar(buf);
}

/* ================= SONORIDAD (ITU-R BS.1770-4 / EBU R128) ================= */
function coefK(fs){
  let f0=1681.974450955533,G=3.999843853973347,Q=0.7071752369554196,K=Math.tan(Math.PI*f0/fs);
  const Vh=Math.pow(10,G/20),Vb=Math.pow(Vh,0.4996667741545416);let a0=1+K/Q+K*K;
  const s1={b0:(Vh+Vb*K/Q+K*K)/a0,b1:2*(K*K-Vh)/a0,b2:(Vh-Vb*K/Q+K*K)/a0,a1:2*(K*K-1)/a0,a2:(1-K/Q+K*K)/a0};
  f0=38.13547087602442;Q=0.5003270373238773;K=Math.tan(Math.PI*f0/fs);a0=1+K/Q+K*K;
  const s2={b0:1,b1:-2,b2:1,a1:2*(K*K-1)/a0,a2:(1-K/Q+K*K)/a0};
  return [s1,s2];
}
function biquad(x,c){
  const y=new Float32Array(x.length);let x1=0,x2=0,y1=0,y2=0;
  for(let i=0;i<x.length;i++){const xn=x[i],yn=c.b0*xn+c.b1*x1+c.b2*x2-c.a1*y1-c.a2*y2;x2=x1;x1=xn;y2=y1;y1=yn;y[i]=yn}
  return y;
}
/* Devuelve la sonoridad integrada (LUFS). Cede el hilo entre canales para no congelar la pantalla. */
async function medirLUFS(canales,fs){
  const k=coefK(fs),nC=canales.length,bloque=Math.round(0.4*fs),paso=Math.round(bloque/4),len=canales[0].length;
  if(len<bloque)return -70;
  const nPasos=Math.floor(len/paso),en=[];
  for(let c=0;c<nC;c++){
    await ceder();
    const f=biquad(biquad(canales[c],k[0]),k[1]),e=new Float64Array(nPasos);
    for(let p=0;p<nPasos;p++){let s=0;for(let i=p*paso,fin=i+paso;i<fin;i++){const v=f[i];s+=v*v}e[p]=s}
    en.push(e);
  }
  const w=c=>(nC>=5&&(c===4||c===5))?1.41:1;
  const bl=[];
  for(let p=0;p+4<=nPasos;p++){
    let z=0;for(let c=0;c<nC;c++){const e=en[c];z+=w(c)*((e[p]+e[p+1]+e[p+2]+e[p+3])/(paso*4))}
    bl.push({l:-0.691+10*Math.log10(z+1e-12),z});
  }
  let g=bl.filter(b=>b.l>-70);if(!g.length)return -70;
  const umbral=-0.691+10*Math.log10(g.reduce((s,b)=>s+b.z,0)/g.length+1e-12)-10;
  g=g.filter(b=>b.l>umbral);if(!g.length)return -70;
  return -0.691+10*Math.log10(g.reduce((s,b)=>s+b.z,0)/g.length+1e-12);
}
function picoDb(canales){let p=0;for(const ch of canales)for(let i=0;i<ch.length;i++){const a=Math.abs(ch[i]);if(a>p)p=a}return p>0?20*Math.log10(p):-Infinity}

/* ================= GANANCIA + LIMITADOR (se trabaja «en sitio» sobre la copia editada) ================= */
function aplicarGanancia(canales,lin){if(lin===1)return;for(const ch of canales)for(let i=0;i<ch.length;i++)ch[i]*=lin}
function minimoVentana(arr,win){ // mínimo de arr[i..i+win) para cada i (cola doble con índices)
  const n=arr.length,out=new Float32Array(n),dq=new Int32Array(n);let h=0,t=0;
  for(let j=n-1;j>=0;j--){
    while(t>h&&arr[dq[t-1]]>=arr[j])t--;
    dq[t++]=j;
    while(dq[h]>=j+win)h++;
    out[j]=arr[dq[h]];
  }
  return out;
}
function limitar(canales,fs,techoLin){
  const nC=canales.length,n=canales[0].length,deseada=new Float32Array(n);
  for(let i=0;i<n;i++){let p=0;for(let c=0;c<nC;c++){const a=Math.abs(canales[c][i]);if(a>p)p=a}deseada[i]=p>techoLin?techoLin/p:1}
  const ventana=Math.max(1,Math.round(fs*0.0015)),objetivo=minimoVentana(deseada,ventana); // mira 1,5 ms hacia delante
  const rel=Math.exp(-1/(fs*0.060));let env=1; // ataque instantáneo, relajación 60 ms
  for(let i=0;i<n;i++){const d=objetivo[i];env=d<env?d:d+(env-d)*rel;objetivo[i]=env}
  for(const ch of canales)for(let i=0;i<n;i++)ch[i]*=objetivo[i];
}

/* ================= CODIFICADOR WAV (fmt + LIST INFO + id3 + data) ================= */
function aPCM(canales,bits,dither){
  const nC=canales.length,n=canales[0].length,bp=bits/8,total=n*nC;
  if(bits===32){const o=new Float32Array(total);for(let c=0;c<nC;c++){const ch=canales[c];for(let i=0,j=c;i<n;i++,j+=nC)o[j]=ch[i]}return new Uint8Array(o.buffer)}
  if(bits===16){const o=new Int16Array(total);for(let c=0;c<nC;c++){const ch=canales[c];for(let i=0,j=c;i<n;i++,j+=nC){let s=ch[i];if(dither)s+=(Math.random()+Math.random()-1)/32768;s=s>1?1:(s<-1?-1:s);o[j]=Math.round(s*32767)}}return new Uint8Array(o.buffer)}
  const o=new Uint8Array(total*3);
  for(let c=0;c<nC;c++){const ch=canales[c];for(let i=0,j=c*3;i<n;i++,j+=nC*3){let v=Math.round(clamp(ch[i],-1,1)*8388607);o[j]=v&255;o[j+1]=(v>>8)&255;o[j+2]=(v>>16)&255}}
  return o;
}
const bytes=s=>new TextEncoder().encode(s);
function juntar(arrs){let l=0;for(const a of arrs)l+=a.length;const o=new Uint8Array(l);let p=0;for(const a of arrs){o.set(a,p);p+=a.length}return o}
function chunkInfo(tags){
  const mapa={INAM:tags.title,IART:tags.artist,IPRD:tags.album,ICRD:tags.year,IGNR:tags.genre,ILNG:tags.lang,ITRK:tags.track,ISFT:'Gestor de música · Masterización',ICOP:tags.copyright};
  (tags.meta||[]).forEach(m=>{if(!m.key||!m.value)return;const c=INFO_META[m.key.trim().toLowerCase()];if(c&&!mapa[c])mapa[c]=m.value});
  const partes=[];
  for(const [k,v] of Object.entries(mapa)){
    if(!v)continue;const b=bytes(String(v)),arr=new Uint8Array(b.length+1);arr.set(b);
    const sz=arr.length,ch=new Uint8Array(8+sz+(sz&1));ch.set(bytes(k),0);new DataView(ch.buffer).setUint32(4,sz,true);ch.set(arr,8);partes.push(ch);
  }
  if(!partes.length)return new Uint8Array(0);
  const inner=juntar(partes),list=new Uint8Array(12+inner.length+(inner.length&1));
  list.set(bytes('LIST'),0);new DataView(list.buffer).setUint32(4,4+inner.length,true);list.set(bytes('INFO'),8);list.set(inner,12);
  return list;
}
const utf16=s=>{const a=[];for(let i=0;i<String(s).length;i++){const c=String(s).charCodeAt(i);a.push(c&255,c>>8)}return new Uint8Array(a)};
const BOM=new Uint8Array([0xFF,0xFE]),NUL2=new Uint8Array([0,0]);
function marco(id,body){const h=new Uint8Array(10);h.set(bytes(id),0);new DataView(h.buffer).setUint32(4,body.length,false);return juntar([h,body])}
const id3Texto=(id,t)=>marco(id,juntar([new Uint8Array([1]),BOM,utf16(t),NUL2]));
const id3TXXX=(d,v)=>marco('TXXX',juntar([new Uint8Array([1]),BOM,utf16(d),NUL2,BOM,utf16(v),NUL2]));
const id3COMM=t=>marco('COMM',juntar([new Uint8Array([1]),bytes('spa'),BOM,NUL2,BOM,utf16(t),NUL2]));
const id3WXXX=u=>marco('WXXX',juntar([new Uint8Array([0,0]),bytes(u)]));
const id3USLT=(lang,t)=>marco('USLT',juntar([new Uint8Array([1]),bytes((lang||'xxx').slice(0,3).padEnd(3,'x')),BOM,NUL2,BOM,utf16(String(t).replace(/\r?\n/g,'\r\n')),NUL2]));
const id3APIC=(mime,b)=>marco('APIC',juntar([new Uint8Array([0]),bytes(mime),new Uint8Array([0,3,0]),b]));
function chunkId3(tags,portada){
  const f=[];
  if(tags.title)f.push(id3Texto('TIT2',tags.title));
  if(tags.artist)f.push(id3Texto('TPE1',tags.artist));
  if(tags.album)f.push(id3Texto('TALB',tags.album));
  if(tags.albumArtist)f.push(id3Texto('TPE2',tags.albumArtist));
  if(tags.copyright)f.push(id3Texto('TCOP',tags.copyright));
  if(tags.year)f.push(id3Texto('TYER',String(tags.year)));
  if(tags.track)f.push(id3Texto('TRCK',String(tags.track)));
  if(tags.genre)f.push(id3Texto('TCON',tags.genre));
  if(tags.lang)f.push(id3Texto('TLAN',tags.lang));
  if(tags.composer&&!(tags.meta||[]).some(m=>m.value&&ID3_META[(m.key||'').trim().toLowerCase()]==='TCOM'))f.push(id3Texto('TCOM',tags.composer));
  if(tags.lyrics)f.push(id3USLT(tags.lang,tags.lyrics));
  (tags.meta||[]).forEach(m=>{
    if(!m.key||!m.value)return;const k=m.key.trim().toLowerCase();
    if(k==='comentario'||k==='comment'){f.push(id3COMM(m.value));return}
    const fid=ID3_META[k];
    if(fid==='WXXX_')f.push(id3WXXX(m.value));else if(fid)f.push(id3Texto(fid,m.value));else f.push(id3TXXX(m.key,m.value));
  });
  f.push(id3Texto('TSSE','Gestor de música · Masterización'));
  if(portada)f.push(id3APIC(portada.mime,portada.bytes));
  const fb=juntar(f),h=new Uint8Array(10);h.set(bytes('ID3'),0);h[3]=3;
  h.set([(fb.length>>21)&127,(fb.length>>14)&127,(fb.length>>7)&127,fb.length&127],6);
  const id3=juntar([h,fb]),pad=id3.length&1,ch=new Uint8Array(8+id3.length+pad);
  ch.set(bytes('id3 '),0);new DataView(ch.buffer).setUint32(4,id3.length,true);ch.set(id3,8);
  return ch;
}
function codificarWav(canales,sr,bits,tags,portada,dither){
  const nC=canales.length,esFloat=bits===32,pcm=aPCM(canales,bits,dither),bp=bits/8;
  const fmt=new Uint8Array(24);fmt.set(bytes('fmt '),0);const fd=new DataView(fmt.buffer);
  fd.setUint32(4,16,true);fd.setUint16(8,esFloat?3:1,true);fd.setUint16(10,nC,true);fd.setUint32(12,sr,true);fd.setUint32(16,sr*nC*bp,true);fd.setUint16(20,nC*bp,true);fd.setUint16(22,bits,true);
  const info=chunkInfo(tags),id3=chunkId3(tags,portada),dh=new Uint8Array(8);
  dh.set(bytes('data'),0);new DataView(dh.buffer).setUint32(4,pcm.length,true);
  const partes=[fmt,info,id3,dh,pcm,pcm.length&1?new Uint8Array(1):new Uint8Array(0)];
  let cuerpo=0;for(const p of partes)cuerpo+=p.length;
  const riff=new Uint8Array(12);riff.set(bytes('RIFF'),0);new DataView(riff.buffer).setUint32(4,4+cuerpo,true);riff.set(bytes('WAVE'),8);
  return juntar([riff,...partes]);
}

/* ================= ZIP sin compresión (los WAV no se comprimen bien; así no hace falta ninguna librería) ================= */
const CRC=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
function crc32(u8){let c=0xFFFFFFFF;for(let i=0;i<u8.length;i++)c=CRC[(c^u8[i])&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0}
class ZipSinCompresion{
  constructor(){this.partes=[];this.pos=0;this.ent=[];const d=new Date();this.hora=(d.getHours()<<11)|(d.getMinutes()<<5)|(d.getSeconds()>>1);this.fecha=((d.getFullYear()-1980)<<9)|((d.getMonth()+1)<<5)|d.getDate()}
  add(nombre,datos){
    const nb=bytes(nombre),crc=crc32(datos),h=new Uint8Array(30+nb.length),v=new DataView(h.buffer);
    v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x0800,true);v.setUint16(8,0,true);v.setUint16(10,this.hora,true);v.setUint16(12,this.fecha,true);
    v.setUint32(14,crc,true);v.setUint32(18,datos.length,true);v.setUint32(22,datos.length,true);v.setUint16(26,nb.length,true);v.setUint16(28,0,true);h.set(nb,30);
    this.ent.push({nb,crc,tam:datos.length,off:this.pos});this.partes.push(h,datos);this.pos+=h.length+datos.length;
    if(this.pos>4e9)throw new Error('El ZIP supera los 4 GB; guarda los másters en la biblioteca en su lugar.');
  }
  blob(){
    const cd=[];let cdTam=0;
    for(const e of this.ent){
      const h=new Uint8Array(46+e.nb.length),v=new DataView(h.buffer);
      v.setUint32(0,0x02014b50,true);v.setUint16(4,20,true);v.setUint16(6,20,true);v.setUint16(8,0x0800,true);v.setUint16(10,0,true);v.setUint16(12,this.hora,true);v.setUint16(14,this.fecha,true);
      v.setUint32(16,e.crc,true);v.setUint32(20,e.tam,true);v.setUint32(24,e.tam,true);v.setUint16(28,e.nb.length,true);v.setUint32(42,e.off,true);h.set(e.nb,46);
      cd.push(h);cdTam+=h.length;
    }
    const f=new Uint8Array(22),v=new DataView(f.buffer);
    v.setUint32(0,0x06054b50,true);v.setUint16(8,this.ent.length,true);v.setUint16(10,this.ent.length,true);v.setUint32(12,cdTam,true);v.setUint32(16,this.pos,true);
    return new Blob([...this.partes,...cd,f],{type:'application/zip'});
  }
}
function descargar(blob,nombre){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=nombre;document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove()},4000)}

/* ================= carátula ================= */
async function cargarCaratula(g){
  if(g.mix&&GM.mixCover){   // mixtape: la portada de casete del propio mixtape
    try{
      const blob=await (await fetch(await GM.mixCover(g.mix,1200))).blob();
      return {bytes:new Uint8Array(await blob.arrayBuffer()),mime:blob.type||'image/jpeg',url:URL.createObjectURL(blob)};
    }catch(e){console.warn('masterizado: portada del mixtape',e);return null}
  }
  if(!g.cover||!g.cover.p)return null;
  try{
    const r=await fetch(GM.audioUrl(g.cover.p));if(!r.ok)return null;
    let blob=await r.blob(),mime=(blob.type||'').toLowerCase();
    if(!mime||mime==='application/octet-stream')mime=/\.png$/i.test(g.cover.p)?'image/png':/\.webp$/i.test(g.cover.p)?'image/webp':'image/jpeg';
    // ID3 solo entiende bien JPEG y PNG; las demás (o las enormes) se pasan a JPEG de hasta 3000 px
    if((mime!=='image/jpeg'&&mime!=='image/png')||blob.size>3.5*1048576){
      const bm=await createImageBitmap(blob),esc=Math.min(1,3000/Math.max(bm.width,bm.height)),cv=document.createElement('canvas');
      cv.width=Math.round(bm.width*esc);cv.height=Math.round(bm.height*esc);cv.getContext('2d').drawImage(bm,0,0,cv.width,cv.height);
      blob=await new Promise(res=>cv.toBlob(res,'image/jpeg',0.92));mime='image/jpeg';
    }
    return {bytes:new Uint8Array(await blob.arrayBuffer()),mime,url:URL.createObjectURL(blob)};
  }catch(e){console.warn('masterizado: carátula',e);return null}
}

/* ================= la pestaña ================= */
let activa=null;           // la pestaña montada ahora mismo (para pararla al montar otra)
const FXCACHE=new Map();   // pista+cadena → trabajo ya procesado en el servidor
const informes={};         // último resultado por álbum (sobrevive a «Actualizar»)
let acReprod=null;
const ctxReprod=()=>acReprod||(acReprod=new (window.AudioContext||window.webkitAudioContext)());

function montar(el,g){
  if(activa)activa.destruir();
  const ab=new AbortController(),sig=ab.signal;
  const todo=GM.state(ID);
  const S=todo[g.key]=Object.assign(ajustes0(),todo[g.key]||{});
  S.fuera=S.fuera||[];S.pistas=S.pistas||{};S.fx=Object.assign({on:false,cadena:[],porPista:{}},S.fx||{});S.fx.porPista=S.fx.porPista||{};Object.keys(S.fx.porPista).forEach(k=>{const v=S.fx.porPista[k];if(!v||Array.isArray(v)||typeof v!=='object')delete S.fx.porPista[k]});S.fx.cadena=(S.fx.cadena||[]).slice(0,5);S.mixMasters=S.mixMasters||{};S.origMix=S.origMix||{};
  let guardaT=null;const guardar=()=>{clearTimeout(guardaT);guardaT=setTimeout(()=>GM.save(),500)};
  let portada=null,vivo=true,ocupado=false,manualN=1;
  const T=[];                         // pistas (del álbum + añadidas a mano)
  const abiertas=new Set();           // pistas con el editor desplegado
  const motor={src:null,buf:null,sonando:false,id:null,off:0,t0:0,o0:0,raf:null};
  const arrastre={modo:null,t:null};
  /* palabras según el contexto: álbum, mixtape o canción suelta (ver NOTAS.md, «Textos nuevos») */
  const X=g.mix?{Cap:'Mixtape',de:'del mixtape',el:'el mixtape',guardar:'Guardar másters del mixtape',dest:'la carpeta MIXTAPES/_masters de este mixtape',vacio:'Este mixtape no tiene canciones todavía. Añade canciones al mixtape o arrastra aquí archivos WAV.'}
    :g.unica?{Cap:'Canción',de:'de la canción',el:'la canción',guardar:'Guardar máster',dest:'la carpeta master de la canción',vacio:'Esta canción no tiene audio todavía. Arrastra aquí un archivo WAV.'}
    :{Cap:'Álbum',de:'del álbum',el:'el álbum',guardar:'Guardar másters del álbum',dest:'la carpeta master de cada canción',vacio:'Este álbum no tiene canciones todavía. Añade canciones al álbum o arrastra aquí archivos WAV.'};
  const soloUna=!!g.unica&&!g.mix;if(soloUna)S.modo='pista';

  el.innerHTML=`<div class="ms">
    <div class="panel ms-cab">
      <div class="ms-cab1"><div><h2 class="ms-h">Masterización ${X.de} «${E(g.title)}»</h2><div class="meta" id="ms-resumen"></div></div>
        <div class="ms-estado"${g.unica?' hidden':''}><span class="meta">Estado ${X.de}</span><div class="ms-chips" id="ms-estado"></div></div></div>
      <div class="ms-ayuda meta">Mide la sonoridad de cada canción, iguala el volumen entre ellas y deja los picos controlados. Tus originales <b>no se tocan</b>: el resultado son archivos nuevos (un ZIP o ${X.dest}).</div>
    </div>
    <div id="ms-avisos"></div>
    <div class="ms-grid">
      <div class="ms-izq">
        <div class="panel"><h3 class="ms-h3">${X.Cap}</h3>
          <div class="ms-cover" id="ms-cover"><span class="meta">Sin carátula</span></div>
          <label class="ms-chk"><input type="checkbox" id="ms-portada"> Incrustar la carátula en los WAV</label>
          <label class="ms-f">Artista ${X.de}</label><input type="text" id="ms-artista" placeholder="Nombre del artista">
          <div class="ms-fila2"><div><label class="ms-f">Año</label><input type="text" id="ms-anio" inputmode="numeric" placeholder="2026" maxlength="4"></div>
            <div><label class="ms-f">Idioma</label><select id="ms-idioma"></select></div></div>
          <label class="ms-f">Género</label><input type="text" id="ms-genero" list="ms-generos" placeholder="Pop, Rock…"><datalist id="ms-generos"></datalist>
          <label class="ms-f">Etiqueta para todas las canciones</label>
          <div class="ms-lote"><input type="text" id="ms-lk" list="ms-claves" placeholder="Ej. Compositor"><input type="text" id="ms-lv" placeholder="Valor"><button class="chip" id="ms-ladd">Añadir a todas</button></div>
          <datalist id="ms-claves"></datalist>
        </div>
        <div class="panel"><h3 class="ms-h3">Masterización</h3>
          <div ${soloUna?'hidden':''}><label class="ms-f">Cómo igualar el volumen</label>
          <div class="ms-seg" id="ms-modo"><button data-v="pista">Cada canción al mismo volumen</button><button data-v="album">Respetar las diferencias</button></div>
          <div class="ms-pista meta" id="ms-modoAyuda"></div></div>
          <label class="ms-f">Volumen objetivo (sonoridad)</label><select id="ms-lufs"></select>
          <label class="ms-f">Techo de picos</label><select id="ms-techo"></select>
          <div class="ms-pista meta">Cada canción se mide en LUFS y se sube o baja hasta el objetivo; un limitador evita que los picos pasen del techo. El limitador vigila el pico de las muestras y deja 0,3 dB extra de margen para el pico real entre muestras.</div>
        </div>
        <div class="panel"><h3 class="ms-h3">Exportación</h3>
          <label class="ms-f">Calidad (bits)</label>
          <div class="ms-seg" id="ms-bits"><button data-v="24">24 bits</button><button data-v="32">32 flotante</button><button data-v="16">16 bits</button></div>
          <label class="ms-chk"><input type="checkbox" id="ms-dither"> Añadir dither (solo en 16 bits)</label>
          <div class="ms-pista meta">Se mantiene la frecuencia de muestreo del archivo (sin remuestrear). El WAV lleva solo formato, etiquetas (ID3 + RIFF) y audio. Las canciones que no son WAV se decodifican a 44,1 kHz.</div>
        </div>
      </div>
      <div class="ms-der panel">
        <div class="ms-lhead"><div class="meta" id="ms-cnt"></div>
          <div class="ms-lacc"><button class="chip" id="ms-anadir">＋ Añadir WAV a mano…</button><input type="file" id="ms-file" accept=".wav,audio/wav,audio/x-wav" multiple hidden></div></div>
        <div id="ms-pistas" class="ms-pistas"></div>
        <div id="ms-vacio" class="empty" style="display:none"></div>
        <div class="ms-ab" id="ms-ab" style="display:none">
          <button class="ms-ib" id="ms-aprev" title="Canción anterior">${SVG.ant}</button><button class="ms-ib" id="ms-aback" title="Retroceder 5 s">${SVG.atras}</button>
          <button class="ms-ib ms-grande" id="ms-aplay" title="Reproducir / pausa">${SVG.play}</button>
          <button class="ms-ib" id="ms-afwd" title="Avanzar 5 s">${SVG.adel}</button><button class="ms-ib" id="ms-anext" title="Canción siguiente">${SVG.sig}</button>
          <span class="ms-tm" id="ms-acur">0:00</span>
          <div class="ms-linea" id="ms-alinea"><div class="ms-marcas" id="ms-amarcas"></div><div class="ms-relleno" id="ms-arell"></div><div class="ms-cab-r" id="ms-acab"></div></div>
          <span class="ms-tm" id="ms-atot">0:00</span>
          <span class="ms-med" id="ms-med" hidden title="Medidor de la escucha en directo"><i><b id="ms-mL"></b></i><i><b id="ms-mR"></b></i></span>
          <label class="ms-chk ms-chk-s" title="Oír todas las canciones ya igualadas al volumen objetivo"><input type="checkbox" id="ms-anorm"> Oír con el volumen igualado</label>
        </div>
        <div class="panel ms-fx" hidden><div class="ms-lhead"><div><h3 class="ms-h3" style="margin:0">Efectos · FX1…FX5, antes del limitador</h3><div class="meta" id="ms-fxres"></div></div>
          <div class="ms-fxsw" id="ms-fxsw"><button class="chip" data-v="1">Con efectos</button><button class="chip" data-v="0">Original</button></div>
          <button class="chip" id="ms-fxtog">▾ Configurar</button></div>
          <div class="meta" id="ms-fxmotor"></div>
          <div id="ms-fxbody" hidden>
            <div class="meta">Define hasta 5 efectos una sola vez (los mismos plugins y ajustes para todo ${g.mix?'el mixtape':g.unica?'lo de aquí':'el álbum'}). En cada pista, los botones <b>FX1…FX5</b> eligen cuáles lleva y <b>∅</b> los apaga todos en esa pista. Lo que oyes es lo que se exporta. Tus originales no se tocan.</div>
            <div id="ms-fxed"></div></div></div>
        <div class="ms-barra" id="ms-barra"><div id="ms-bar"></div></div>
        <div class="ms-acciones">
          <button class="chip" id="ms-analizar">📊 Medir volumen</button>
          <button class="chip pri" id="ms-zip">⬇ Descargar ZIP</button>
          <button class="chip pri" id="ms-bib">💾 ${X.guardar}</button>
          <span class="meta" id="ms-estadoOp"></span>
        </div>
        <div id="ms-mixbar"></div>
        <div class="ms-log" id="ms-log"></div>
      </div>
    </div></div>`;
  const $=s=>el.querySelector(s);

  /* ---------- registro y progreso ---------- */
  function log(msg,cls){const l=$('#ms-log');if(!l)return;l.classList.add('on');const d=document.createElement('div');if(cls)d.className='l-'+cls;d.textContent=msg;l.appendChild(d);l.scrollTop=l.scrollHeight}
  function progreso(p){const b=$('#ms-barra');if(!b)return;b.classList.toggle('on',p>=0&&p<1);$('#ms-bar').style.width=(clamp(p,0,1)*100)+'%'}
  function aviso(html,cls){const a=$('#ms-avisos');a.innerHTML=html?`<div class="callout ms-av ${cls||''}">${html}</div>`:''}

  /* ---------- ajustes de la columna izquierda ---------- */
  $('#ms-estado').innerHTML=ESTADOS.map(e=>`<button class="chip" data-v="${A(e)}">${E(e)}</button>`).join('');
  $('#ms-lufs').innerHTML=OBJETIVOS.map(([v,l])=>`<option value="${v}">${E(l)}</option>`).join('');
  $('#ms-techo').innerHTML=TECHOS.map(([v,l])=>`<option value="${v}">${E(l)}</option>`).join('');
  $('#ms-idioma').innerHTML=IDIOMAS.map(([v,l])=>`<option value="${v}">${E(l)}</option>`).join('');
  $('#ms-generos').innerHTML=GENEROS.map(x=>`<option value="${A(x)}">`).join('');
  $('#ms-claves').innerHTML=CLAVES_META.map(x=>`<option value="${A(x)}">`).join('');
  const seg=(id,val)=>$(id).querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v===String(val)));
  function pintarAjustes(){
    seg('#ms-estado',S.estado);seg('#ms-modo',S.modo);seg('#ms-bits',S.bits);
    if(![...$('#ms-lufs').options].some(o=>+o.value===+S.lufs))$('#ms-lufs').insertAdjacentHTML('beforeend',`<option value="${S.lufs}">${S.lufs} LUFS</option>`);
    $('#ms-lufs').value=S.lufs;$('#ms-techo').value=S.techo;$('#ms-dither').checked=!!S.dither;$('#ms-portada').checked=!!S.portada;
    $('#ms-artista').value=S.artista||'';$('#ms-anio').value=S.anio||'';$('#ms-genero').value=S.genero||'';$('#ms-idioma').value=S.idioma||'';
    $('#ms-modoAyuda').textContent=S.modo==='pista'?'Todas las canciones quedan con el mismo volumen (recomendado para singles y listas).':`Se sube todo ${X.el} lo mismo, de modo que la canción más fuerte llega al objetivo y las demás conservan su diferencia (recomendado para discos con canciones suaves y fuertes a propósito).`;
  }
  $('#ms-estado').onclick=e=>{const b=e.target.closest('button');if(!b)return;S.estado=b.dataset.v;seg('#ms-estado',S.estado);guardar();GM.emit('masterizado:estado',{album:g.key,estado:S.estado});GM.ui.toast('Estado '+X.de+': '+S.estado)};
  $('#ms-modo').onclick=e=>{const b=e.target.closest('button');if(!b)return;S.modo=b.dataset.v;guardar();pintarAjustes();recalcularGanancias()};
  $('#ms-bits').onclick=e=>{const b=e.target.closest('button');if(!b)return;S.bits=+b.dataset.v;guardar();seg('#ms-bits',S.bits)};
  $('#ms-lufs').onchange=e=>{S.lufs=+e.target.value;guardar();T.forEach(t=>{t.norm=null});recalcularGanancias();reiniciarSiNorm()};
  $('#ms-techo').onchange=e=>{S.techo=+e.target.value;guardar();T.forEach(t=>{t.norm=null});reiniciarSiNorm()};
  $('#ms-dither').onchange=e=>{S.dither=e.target.checked;guardar()};
  $('#ms-portada').onchange=e=>{S.portada=e.target.checked;guardar()};
  [['#ms-artista','artista'],['#ms-anio','anio'],['#ms-genero','genero'],['#ms-idioma','idioma']].forEach(([s,k])=>{const f=()=>{S[k]=$(s).value;guardar();if(k!=='idioma')pintarEtiquetasAuto()};$(s).addEventListener('input',f);$(s).addEventListener('change',f)});
  $('#ms-ladd').onclick=()=>{
    const k=$('#ms-lk').value.trim(),v=$('#ms-lv').value.trim();
    if(!k){GM.ui.toast('Escribe el nombre de la etiqueta (por ejemplo Compositor).');return}
    const act=T.filter(t=>!t.sinAudio);if(!act.length){GM.ui.toast('Todavía no hay canciones.');return}
    act.forEach(t=>{const ex=t.p.meta.find(m=>(m.key||'').toLowerCase()===k.toLowerCase());if(ex)ex.value=v;else t.p.meta.push({key:k,value:v})});
    $('#ms-lk').value='';$('#ms-lv').value='';guardar();pintarPistas();log(`Etiqueta «${k}» puesta en ${act.length} canción(es).`,'ok');
  };

  /* ---------- pistas ---------- */
  function pistaDe(id,p,extra){
    return Object.assign({id,p,ruta:null,file:null,info:null,ch:null,peaks:null,lufs:null,pico:null,gain:null,estadoCarga:'espera',error:'',edBuf:null,norm:null,normKey:'',manual:false,sinAudio:false},extra);
  }
  /* Fuente de cada canción: su versión final o la mejor (GM.finalPath || GM.bestVersion). Los másters que genera este mismo
     módulo («… (máster).wav» en master/) se saltan: si no, al volver a abrir la pestaña se masterizaría un máster ya masterizado. */
  const GENERADO=/\(m[aá]ster\)( \(\d+\))?\.wav$/i;
  function fuenteDe(s){
    const c=GM.finalPath(s)||GM.bestVersion(s)||null;
    if(!c||!GENERADO.test(c))return c;
    const v=(s.versions||[]).filter(x=>!GENERADO.test(x.p));
    const o=v.find(x=>!/\/master\//i.test(x.p))||v[0];
    return o?o.p:c;
  }
  /* mixtape: respeta la versión elegida en el mixtape (it.p), salvo que sea un máster de este módulo (entonces, el original guardado) */
  const MIXM=/^MIXTAPES\/_masters\//i;
  function fuenteMix(s){
    const it=g.mix.items.find(i=>i.id===s.id);let p=it&&it.p;
    if(p&&MIXM.test(p))p=S.origMix[s.id]||null;
    return p||fuenteDe(s);
  }
  function construirPistas(){
    const orden=g.mix?g.mix.items.map(it=>GM.song(it.id)).filter(Boolean):(g.canciones||GM.order(g));
    orden.forEach(s=>{
      if(S.fuera.includes(s.id))return;
      const p=S.pistas[s.id]=Object.assign(pista0(),S.pistas[s.id]||{});p.meta=p.meta||[];
      const ruta=g.mix?fuenteMix(s):fuenteDe(s);
      T.push(pistaDe(s.id,p,{song:s,ruta,sinAudio:!ruta,estadoCarga:ruta?'espera':'sinaudio',titulo:GM.title(s)}));
    });
  }
  const nombreDe=t=>t.p.name!=null&&t.p.name!==''?t.p.name:(t.titulo||'Sin título');
  const dur0=t=>t.info?t.info.length/t.info.sampleRate:0;
  const ini=t=>t.info?clamp(t.p.trimStart||0,0,dur0(t)):0;
  const fin=t=>t.info?clamp(t.p.trimEnd==null?dur0(t):t.p.trimEnd,ini(t),dur0(t)):0;
  function durEd(t){if(!t.info)return 0;const sr=t.info.sampleRate,core=Math.max(0,Math.floor(fin(t)*sr)-Math.floor(ini(t)*sr));return (Math.floor((t.p.padStart||0)*sr)+core+Math.floor((t.p.padEnd||0)*sr))/sr}
  const activas=()=>T.filter(t=>!t.sinAudio&&!t.error);
  const totalAlbum=()=>activas().reduce((a,t)=>a+durEd(t),0);

  /* carga bajo demanda: el audio entero solo está en memoria mientras se necesita (así caben 15 canciones de 60 MB) */
  /* efectos (módulo vst): la pista se procesa en el servidor ANTES de todo lo demás (medición, ganancia y limitador siguen en el navegador) */
  /* 5 huecos FX1…FX5 (S.fx.cadena, iguales para todo el conjunto); cada pista elige cuáles incluye (máscara) o los apaga todos */
  const fxM=t=>{const o=S.fx.porPista[t.id]||{};return {m:[0,1,2,3,4].map(i=>!(o.m&&o.m[i]===0)),off:!!o.off}};
  const fxCad=t=>{if(!FX_ACTIVO||!S.fx.on)return null;const {m,off}=fxM(t);if(off)return null;const c=S.fx.cadena.filter((x,i)=>m[i]&&x.on!==false);return c.length?c:null};
  function fxRevisar(t){   // si la cadena de la pista cambió desde que se cargó, lo medido y el audio cargado ya no valen
    if(t.fxKey===undefined||fxClave(t)===(t.fxKey||''))return;
    t.ch=null;t.edBuf=null;t.norm=null;t.lufs=null;t.pico=null;t.gain=null;t.fxKey=undefined;
  }
  const fxClave=t=>{const c=fxCad(t);return c?t.id+'|'+JSON.stringify(c.filter(x=>x.on!==false)):''};
  async function traerFx(t,c){
    if(!GM.mods.vst)throw new Error('el módulo de efectos no está disponible');
    const key=t.fxKey=fxClave(t),h=FXCACHE.get(key);
    if(h){try{const b=await (await GM.apiBlob('vst','audio?id='+h.id+'&que=proc')).arrayBuffer();t.fxBaj=h.baj;return b}catch(e){FXCACHE.delete(key)}}
    log('Aplicando efectos a «'+nombreDe(t)+'»…','info');
    const r=await GM.mods.vst.procesar({ruta:t.file?undefined:t.ruta,archivo:t.file||undefined,cadena:c,ini:0,dur:7200,bits:24});   // si pasa de 0 dB el servidor baja el volumen y lo anota (bajado_db): lo devolvemos al decodificar
    t.fxBaj=r.info.bajado_db||0;FXCACHE.set(key,{id:r.info.id,baj:t.fxBaj});URL.revokeObjectURL(r.url);return r.blob.arrayBuffer();
  }
  async function traerBuffer(t){
    const c=fxCad(t);t.fxKey='';t.fxBaj=0;
    if(c)try{return await traerFx(t,c)}catch(e){throw new Error('efectos: '+(e.message||e))}
    if(t.file)return t.file.arrayBuffer();
    const r=await fetch(GM.audioUrl(t.ruta));
    if(!r.ok)throw new Error('el gestor no pudo darme el archivo ('+r.status+')');
    return r.arrayBuffer();
  }
  async function asegurar(t){
    fxRevisar(t);
    if(t.ch)return t;
    if(t.sinAudio)throw new Error('esta canción no tiene audio');
    const d=await leerAudio(await traerBuffer(t));
    if(!vivo)throw new Error('cancelado');
    if(t.fxBaj>0){const k=dbALin(t.fxBaj);d.ch.forEach(c=>{for(let i=0;i<c.length;i++)c[i]*=k})}
    t.ch=d.ch;t.info=t.info||{};Object.assign(t.info,{sampleRate:d.sampleRate,bits:d.bits,float:d.float,channels:d.channels,length:d.length,decodificado:d.decodificado});
    if(!t.peaks)t.peaks=calcularPicos(t.ch,d.length,2400);
    return t;
  }
  function liberar(t){if(t.ch&&!mantener(t)){t.ch=null;t.edBuf=null;t.norm=null}}
  const mantener=t=>abiertas.has(t.id)||(motor.id===t.id);
  function calcularPicos(ch,n,res){
    const min=new Float32Array(res),max=new Float32Array(res),bs=n/res,nc=ch.length;
    for(let b=0;b<res;b++){const st=Math.floor(b*bs),en=Math.min(n,Math.floor((b+1)*bs));let mn=0,mx=0;
      for(let i=st;i<en;i++){let s=0;for(let c=0;c<nc;c++)s+=ch[c][i];s/=nc;if(s<mn)mn=s;if(s>mx)mx=s}
      min[b]=mn;max[b]=mx}
    return {res,min,max};
  }
  let colaCarga=Promise.resolve();
  function cargarInfo(t){ // una tras otra, sin bloquear la pantalla
    colaCarga=colaCarga.then(async()=>{
      if(!vivo||t.info&&t.peaks||t.sinAudio)return;
      t.estadoCarga='cargando';filaEstado(t);
      try{await asegurar(t);t.estadoCarga='lista';t.error=''}
      catch(e){t.estadoCarga='error';t.error=e.message||String(e)}
      liberar(t);await ceder();
      if(vivo){filaEstado(t);resumen();pintarMarcas()}
    });
    return colaCarga;
  }

  /* ---------- edición no destructiva: recorte + fundidos + silencios ---------- */
  function editar(t){
    const sr=t.info.sampleRate,n=t.info.length,s0=clamp(Math.floor(ini(t)*sr),0,n),s1=clamp(Math.floor(fin(t)*sr),0,n),core=Math.max(0,s1-s0);
    const pA=Math.max(0,Math.floor((t.p.padStart||0)*sr)),pB=Math.max(0,Math.floor((t.p.padEnd||0)*sr)),total=Math.max(1,pA+core+pB);
    const fi=Math.min(core,Math.floor((t.p.fadeIn||0)*sr)),fo=Math.min(core,Math.floor((t.p.fadeOut||0)*sr)),HP=Math.PI/2;
    return t.ch.map(ch=>{
      const o=new Float32Array(total);
      for(let i=0;i<core;i++){let v=ch[s0+i];if(fi>0&&i<fi)v*=Math.sin(HP*(i/fi));if(fo>0&&i>=core-fo)v*=Math.sin(HP*((core-i)/fo));o[pA+i]=v}
      return o;
    });
  }
  function aBuffer(canales,sr){const ac=ctxReprod(),b=ac.createBuffer(canales.length,canales[0].length,sr);canales.forEach((c,i)=>b.copyToChannel(c,i));return b}
  function bufferEditado(t){if(!t.edBuf)t.edBuf=aBuffer(editar(t),t.info.sampleRate);return t.edBuf}
  function invalidar(t){t.edBuf=null;t.norm=null;t.lufs=null;t.pico=null;t.gain=null;emPista(t)}
  async function medir(t){
    await asegurar(t);const ed=editar(t);
    t.lufs=await medirLUFS(ed,t.info.sampleRate);t.pico=picoDb(ed);
  }
  function ganancia(t){
    if(t.lufs==null)return null;
    if(S.modo==='album'){
      const ls=activas().map(x=>x.lufs).filter(l=>l!=null&&l>-70);if(!ls.length||t.lufs<=-70)return 0;
      if(activas().some(x=>x.lufs==null))return null;
      return S.lufs-Math.max(...ls);
    }
    return t.lufs<=-70?0:S.lufs-t.lufs;
  }
  function recalcularGanancias(){T.forEach(t=>{t.gain=ganancia(t);t.norm=null});T.forEach(t=>filaEstado(t));pintarCuadro()}
  /* el limitador mira el pico de las muestras; con techo negativo se deja 0,3 dB más de margen para el pico real entre muestras */
  const techoLin=()=>dbALin(S.techo-(S.techo<0?0.3:0));
  async function bufferIgualado(t){
    const clave=S.lufs+'|'+S.techo+'|'+S.modo+'|'+t.lufs+'|'+(t.gain==null?'':t.gain);
    if(t.norm&&t.normKey===clave)return t.norm;
    if(t.lufs==null){await medir(t);filaEstado(t)}
    t.gain=ganancia(t);
    if(t.gain==null)t.gain=(t.lufs<=-70)?0:S.lufs-t.lufs;
    const ed=editar(t);aplicarGanancia(ed,dbALin(t.gain));
    if(S.techo!==0)limitar(ed,t.info.sampleRate,techoLin());
    t.norm=aBuffer(ed,t.info.sampleRate);t.normKey=clave;return t.norm;
  }

  /* ---------- motor de escucha en directo (módulo vst · motor.py). El navegador no suena mientras funciona ---------- */
  const EM={vivo:false,est:null,at:0,sig:'',fallo:false,motivo:'',sinSd:false,poll:null,guard:0};
  const emCmd=o=>GM.mods.vst.motor.cmd(o).catch(()=>({ok:false}));
  const sinkTest=()=>{try{return localStorage.getItem('gm_sink')==='nulo'}catch(e){return false}};   // solo pruebas: salida nula, no suena nada
  async function emUsable(){
    if(EM.vivo)return true;
    if(!FX_ACTIVO||EM.fallo||S.fx.motor===false||!GM.mods.vst||!S.fx.cadena.length)return false;
    const r=await GM.mods.vst.motor.iniciar(sinkTest()?{sink:'nulo',tiempo_real:true}:{}).catch(e=>({ok:false,error:e.message}));
    if(!r.ok){EM.fallo=true;EM.motivo=r.error||'';EM.sinSd=!!r.sin_sounddevice;fxMotorUi();return false}
    EM.vivo=true;EM.sig='';EM.est=r.estado;EM.at=performance.now();EM.poll=setInterval(emSondeo,150);fxMotorUi();$('#ms-med').hidden=false;return true;
  }
  async function emSpec(t){
    const o=fxM(t),p=t.p,sp={id:t.id,mascara:o.m,apagado:o.off,gain_db:0,techo_db:null,ini:p.trimStart||0,padStart:p.padStart||0,padEnd:p.padEnd||0,fadeIn:p.fadeIn||0,fadeOut:p.fadeOut||0};
    if(p.trimEnd!=null)sp.fin=p.trimEnd;
    if(t.manual){
      if(!t.subida){const up=await GM.api('vst','subir?nombre='+encodeURIComponent(t.file.name||'audio.wav'),t.file);if(!up||!up.ok)throw new Error((up&&up.error)||'no se pudo subir el archivo');t.subida=up.id}
      sp.subida=t.subida;
    }else sp.ruta=t.ruta;
    if(p.previewNorm){sp.gain_db=t.gain==null?0:t.gain;sp.techo_db=S.techo!==0?S.techo:null}
    return sp;
  }
  async function emLista(){
    const L=activas();
    if(L.some(t=>t.p.previewNorm)&&L.some(t=>t.lufs==null))await medirTodas();
    const specs=[];for(const t of L)specs.push(await emSpec(t));
    const sig=JSON.stringify([specs,S.fx.cadena,S.fx.on]);
    if(sig===EM.sig)return;
    const r=await GM.mods.vst.motor.cmd({c:'lista',pistas:specs,slots:S.fx.cadena,efectos:S.fx.on});
    if(!r.ok)throw new Error(r.error||'el motor no aceptó la lista');
    EM.sig=sig;
  }
  async function emPlay(t,off){
    try{
      motor.id=t.id;motor.off=off||0;
      await emLista();
      const i=activas().findIndex(x=>x.id===t.id);
      const r=await GM.mods.vst.motor.cmd({c:'play',indice:i,seg:off||0});
      if(!r.ok)throw new Error(r.error||'no respondió');
      motor.sonando=true;EM.guard=performance.now()+600;EM.at=performance.now();EM.est=Object.assign({},EM.est||{},{pos:off||0,sonando:true});
      if(!abiertas.has(t.id)){abiertas.add(t.id);pintarPistas()}
      arrancarRaf();pintarReprod();
    }catch(e){motor.sonando=false;log('No se pudo reproducir «'+nombreDe(t)+'»: '+e.message,'warn');pintarReprod()}
  }
  async function emSondeo(){
    if(!EM.vivo||!vivo)return;
    const r=await GM.mods.vst.motor.estado().catch(()=>null);
    if(!r||!r.ok)return;
    if(!r.vivo){EM.vivo=false;EM.fallo=true;EM.motivo=r.fatal||'El motor de escucha se cerró.';clearInterval(EM.poll);motor.sonando=false;pararRaf();pintarReprod();$('#ms-med').hidden=true;fxMotorUi();log('✗ '+EM.motivo,'warn');return}
    const e=r.estado;if(!e)return;
    EM.est=e;EM.at=performance.now()-(r.edad||0)*1000;emMed(e);
    if(!motor.sonando)return;
    if(!e.sonando){if(performance.now()>EM.guard){motor.sonando=false;motor.off=0;pararRaf();pintarReprod();const a=actual();a&&dibujar(a)}return}
    if(e.id&&e.id!==motor.id){motor.id=e.id;motor.off=0;abiertas.add(e.id);pintarPistas();pintarReprod()}
  }
  function emMed(e){
    const f=v=>Math.max(0,Math.min(100,(v+60)/60*100)),L=el.querySelector('#ms-mL'),R=el.querySelector('#ms-mR');if(!L)return;
    L.style.width=f(e.sonando?e.pico[0]:-120)+'%';R.style.width=f(e.sonando?e.pico[1]:-120)+'%';
    L.parentElement.title='Pico: L '+e.pico[0]+' dB · R '+e.pico[1]+' dB';
  }
  const emPT={};
  function emPista(t){   // un cambio de edición o de máscara llega al motor al momento
    if(!EM.vivo||!vivo)return;
    clearTimeout(emPT[t.id]);
    emPT[t.id]=setTimeout(()=>{const o=fxM(t),p=t.p;emCmd({c:'pista',id:t.id,campos:{mascara:o.m,apagado:o.off,ini:p.trimStart||0,fin:p.trimEnd==null?undefined:p.trimEnd,padStart:p.padStart||0,padEnd:p.padEnd||0,fadeIn:p.fadeIn||0,fadeOut:p.fadeOut||0}});emGainPush()},120);
  }
  let emGT=null;
  function emGainPush(){   // ganancia y techo de cada pista (cambian al re-medir tras tocar efectos, objetivo o techo)
    if(!EM.vivo)return;clearTimeout(emGT);
    emGT=setTimeout(async()=>{
      if(!EM.vivo||!vivo)return;
      try{
        const L=activas(),pn=L.some(t=>t.p.previewNorm);
        if(pn&&L.some(t=>t.lufs==null))await medirTodas();
        for(const t of L)await emCmd({c:'pista',id:t.id,campos:{gain_db:t.p.previewNorm&&t.gain!=null?t.gain:0,techo_db:t.p.previewNorm&&S.techo!==0?S.techo:null}});
        EM.sig='';
      }catch(e){}
    },700);
  }

  /* ---------- reproducción ---------- */
  const pos=()=>EM.vivo?(motor.sonando?clamp((EM.est?EM.est.pos:0)+(performance.now()-EM.at)/1000,0,EM.est&&EM.est.dur?EM.est.dur:1e9):motor.off):motor.sonando&&motor.buf?clamp(motor.o0+(ctxReprod().currentTime-motor.t0),0,motor.buf.duration):motor.off;
  const actual=()=>T.find(t=>t.id===motor.id)||activas()[0];
  const sonando=t=>motor.sonando&&motor.id===t.id;
  function pararFuente(){if(motor.src){motor.src.onended=null;try{motor.src.stop()}catch(e){}try{motor.src.disconnect()}catch(e){}motor.src=null}}
  async function reproducir(t,off){
    if(await emUsable())return emPlay(t,off);
    try{
      const ac=ctxReprod();ac.resume();pararFuente();motor.sonando=false;motor.id=t.id;motor.off=off||0;
      await asegurar(t);
      const buf=t.p.previewNorm?await bufferIgualado(t):bufferEditado(t);
      if(motor.id!==t.id||!vivo)return;
      const src=ac.createBufferSource();src.buffer=buf;src.connect(ac.destination);src.onended=alTerminar;
      motor.src=src;motor.buf=buf;motor.sonando=true;motor.o0=clamp(off||0,0,Math.max(0,buf.duration-0.001));motor.t0=ac.currentTime;src.start(0,motor.o0);
      if(!abiertas.has(t.id)){abiertas.add(t.id);pintarPistas()}
      arrancarRaf();pintarReprod();
    }catch(e){motor.sonando=false;log('No se pudo reproducir «'+nombreDe(t)+'»: '+e.message,'warn');pintarReprod()}
  }
  function pausar(){if(!motor.sonando)return;motor.off=pos();if(EM.vivo)emCmd({c:'pausa'});pararFuente();motor.sonando=false;pararRaf();pintarReprod();const t=actual();t&&dibujar(t)}
  function parar(){if(EM.vivo&&motor.sonando)emCmd({c:'pausa'});pararFuente();motor.sonando=false;pararRaf()}
  function alTerminar(){
    if(!motor.sonando)return;
    const L=activas(),i=L.findIndex(t=>t.id===motor.id),sig=L[i+1];
    if(EM.vivo)return;
    if(sig)reproducir(sig,0);else{motor.sonando=false;motor.off=0;pararRaf();pintarReprod()}
  }
  function alternar(t){if(sonando(t)){pausar();return}reproducir(t,motor.id===t.id?motor.off:0)}
  function irA(t,off){off=clamp(off,0,durEd(t));if(sonando(t)||motor.sonando&&motor.id!==t.id)reproducir(t,off);else{motor.id=t.id;motor.off=off;dibujar(t);pintarReprod()}}
  function vecina(d){const L=activas(),t=actual(),s=L[L.indexOf(t)+d];if(!s)return;abiertas.add(s.id);if(motor.sonando)reproducir(s,0);else{motor.id=s.id;motor.off=0;pintarPistas()}}
  function saltar(d){
    const L=activas(),t=actual();if(!t)return;let e=pos()+d,i=L.indexOf(t);
    if(e<0&&L[i-1]){const p=L[i-1];irAlbum(acumulado(p)+durEd(p)+e);return}
    if(e>durEd(t)&&L[i+1]){irAlbum(acumulado(t)+e);return}
    irA(t,clamp(e,0,durEd(t)));
  }
  const acumulado=t=>{let a=0;for(const x of activas()){if(x.id===t.id)break;a+=durEd(x)}return a};
  function irAlbum(T0){
    const L=activas();T0=clamp(T0,0,totalAlbum());let a=0;
    for(let i=0;i<L.length;i++){const d=durEd(L[i]);if(T0<a+d||i===L.length-1){const t=L[i];abiertas.add(t.id);if(motor.sonando)reproducir(t,clamp(T0-a,0,d));else{motor.id=t.id;motor.off=clamp(T0-a,0,d);pintarPistas()}return}a+=d}
  }
  function reiniciarSiNorm(){emGainPush();const t=actual();if(motor.sonando&&t&&t.p.previewNorm)reproducir(t,clamp(pos(),0,durEd(t)));else{pintarCuadro();}}
  function arrancarRaf(){if(motor.raf)return;const f=()=>{if(!el.isConnected){destruir();return}tick();motor.raf=motor.sonando?requestAnimationFrame(f):null};motor.raf=requestAnimationFrame(f)}
  function pararRaf(){if(motor.raf){cancelAnimationFrame(motor.raf);motor.raf=null}}
  function tick(){const t=actual();if(t){dibujar(t);const s=el.querySelector('.ms-tiempo[data-id="'+CSS.escape(t.id)+'"]');if(s)s.textContent=tiempo(pos())+' / '+tiempo(durEd(t))}pintarBarra()}
  function pintarReprod(){
    el.querySelectorAll('.ms-fila').forEach(f=>{const t=T.find(x=>x.id===f.dataset.id);const b=f.querySelector('.ms-play');if(b&&t)b.innerHTML=sonando(t)?SVG.pausa:SVG.play});
    el.querySelectorAll('.ms-tp').forEach(b=>{const t=T.find(x=>x.id===b.dataset.id);if(t)b.innerHTML=sonando(t)?SVG.pausa:SVG.play});
    pintarBarra();
  }
  let scrub=null;
  function pintarBarra(){
    if(scrub!=null)return;const t=actual();if(!t)return;
    const tot=totalAlbum(),cur=acumulado(t)+(motor.id===t.id?pos():0),fr=tot>0?cur/tot:0;
    $('#ms-acur').textContent=tiempo(cur);$('#ms-atot').textContent=tiempo(tot);$('#ms-arell').style.width=(fr*100)+'%';$('#ms-acab').style.left=(fr*100)+'%';
    $('#ms-aplay').innerHTML=motor.sonando?SVG.pausa:SVG.play;
  }
  function pintarMarcas(){
    const tot=totalAlbum();if(tot<=0){$('#ms-amarcas').innerHTML='';return}
    let a=0,h='';activas().forEach((t,i)=>{const f=a/tot*100;if(i>0)h+=`<i style="left:${f}%"></i>`;h+=`<b style="left:${f}%">${i+1}</b>`;a+=durEd(t)});
    $('#ms-amarcas').innerHTML=h;pintarBarra();
  }

  /* ---------- pintar la lista ---------- */
  function subHtml(t){
    if(t.sinAudio)return '<span class="ms-mal">Esta canción no tiene audio: no entra en el máster.</span>';
    if(t.estadoCarga==='error')return `<span class="ms-mal">No se pudo leer: ${E(t.error)}</span>`;
    if(!t.info)return '<span class="meta">Leyendo audio…</span>';
    const i=t.info,f=i.decodificado?'decodificado a '+num(i.sampleRate/1000,1)+' kHz':num(i.sampleRate/1000,i.sampleRate%1000?1:0)+' kHz · '+i.bits+(i.float?' bits float':' bits');
    const gtxt=t.gain==null?'':`<span class="${t.gain>=0?'ms-sube':'ms-baja'}">${t.gain>=0?'+':''}${num(t.gain)} dB</span>`;
    return `<span title="${A(t.ruta||'')}">${f} · ${i.channels===1?'mono':i.channels===2?'estéreo':i.channels+' canales'}</span><span>${tiempo(durEd(t))}</span><span class="ms-lufs">${t.lufs==null?'— LUFS':(t.lufs<=-70?'silencio':num(t.lufs)+' LUFS')}</span>${t.pico!=null?`<span>pico ${isFinite(t.pico)?num(t.pico):'-∞'} dB</span>`:''}${gtxt}<span class="ms-orig" title="Archivo de origen">♪ ${E(t.manual?t.file.name:(t.ruta||'').split('/').pop())}</span>`;
  }
  function filaEstado(t){
    const f=el.querySelector('.ms-fila[data-id="'+CSS.escape(t.id)+'"]');if(!f)return;
    f.querySelector('.ms-sub').innerHTML=subHtml(t);
    const deshab=t.sinAudio||t.estadoCarga==='error';f.classList.toggle('ms-off',deshab);
    f.querySelectorAll('.ms-play,.ms-chev').forEach(b=>b.disabled=deshab);
  }
  function resumen(){
    const a=activas(),n=T.length,sin=T.filter(t=>t.sinAudio).length;
    $('#ms-resumen').textContent=`${a.length} de ${n} canciones con audio · ${tiempo(totalAlbum())}`;
    $('#ms-cnt').textContent=`${n} ${n!==1?'canciones':'canción'}${S.fuera.length?' · '+S.fuera.length+' fuera del máster':''}`;
    const h=T.filter(t=>t.sinAudio);
    aviso(h.length?`<b>${h.length===1?'Una canción no tiene':'Hay '+h.length+' canciones sin'} audio</b> y no entrará en el máster: ${h.map(t=>'«'+E(nombreDe(t))+'»').join(', ')}. Cuando tengan una versión de audio en su carpeta, pulsa «Actualizar» en el gestor.`:'');
    $('#ms-ab').style.display=a.length?'flex':'none';
    $('#ms-analizar').disabled=!a.length||ocupado;$('#ms-zip').disabled=!a.length||ocupado;$('#ms-bib').disabled=!a.some(t=>t.song)||ocupado;
  }
  function etiquetasAuto(t,idx){
    const L=activas(),n=L.length,i=L.indexOf(t);
    return [['Título',nombreDe(t)],['Artista',t.p.artist||S.artista],[X.Cap,g.title],['Artista '+X.de,S.artista],['Pista',(i+1)+'/'+n],['Año',S.anio],['Género',S.genero],['Idioma',(IDIOMAS.find(x=>x[0]===S.idioma)||[])[1]&&S.idioma?IDIOMAS.find(x=>x[0]===S.idioma)[1]:'']].filter(([k,v])=>v);
  }
  function pintarEtiquetasAuto(){el.querySelectorAll('.ms-fila').forEach(f=>{const t=T.find(x=>x.id===f.dataset.id),box=f.parentElement.querySelector('.ms-auto');if(t&&box)box.innerHTML=etiquetasAuto(t).map(([k,v])=>`<span class="ms-tag"><b>${E(k)}</b> ${E(v)}</span>`).join('')})}
  function pintarPistas(){
    const cont=$('#ms-pistas');cont.innerHTML='';
    $('#ms-vacio').style.display=T.length?'none':'block';
    if(!T.length)$('#ms-vacio').textContent=S.fuera.length?'Quitaste todas las canciones del máster. Pulsa «Recuperar las quitadas» para volver a verlas.':X.vacio;
    let num0=0;
    T.forEach(t=>{
      const abierta=abiertas.has(t.id),w=document.createElement('div');w.className='ms-wrap';
      const nu=(t.sinAudio||t.error)?'–':(++num0);
      w.innerHTML=`<div class="ms-fila${abierta?' sel':''}${t.sinAudio?' ms-off':''}" data-id="${A(t.id)}">
        <div class="ms-num">${nu}</div>
        <div class="ms-meta"><input class="ms-nombre" value="${A(nombreDe(t))}" placeholder="Título de la canción" title="Título que se escribirá en el WAV"><div class="ms-sub">${subHtml(t)}</div><div class="ms-fxb"></div></div>
        <div class="ms-bts"><button class="ms-ib ms-play" title="Escuchar"${t.sinAudio?' disabled':''}>${sonando(t)?SVG.pausa:SVG.play}</button><button class="ms-ib ms-chev${abierta?' open':''}" title="Editar: recorte, fundidos, etiquetas"${t.sinAudio?' disabled':''}>${SVG.chev}</button>${g.mix&&!t.manual?'<button class="ms-ib ms-up" title="Subir en el mixtape">↑</button><button class="ms-ib ms-dn" title="Bajar en el mixtape">↓</button>':''}<button class="ms-ib ms-del" title="${t.manual?'Quitar':'No incluir en el máster'}">${SVG.x}</button></div>
      </div>
      <div class="ms-ed"${abierta?'':' style="display:none"'}>${abierta?editorHtml(t):''}</div>`;
      const fila=w.querySelector('.ms-fila');
      w.querySelector('.ms-nombre').addEventListener('input',e=>{t.p.name=e.target.value;guardar();pintarEtiquetasAuto()});
      fila.querySelector('.ms-play').onclick=e=>{e.stopPropagation();alternar(t)};
      {const c=fila.querySelector('.ms-fxb');c.innerHTML=fxBtnsHtml(t);c.classList.toggle('apag',!S.fx.on);c.onclick=e=>{const bt=e.target.closest('button');if(!bt)return;e.stopPropagation();fxToggle(t,bt)}}
      fila.querySelector('.ms-chev').onclick=e=>{e.stopPropagation();alternarEditor(t)};
      fila.querySelector('.ms-del').onclick=e=>{e.stopPropagation();quitar(t)};
      const up=fila.querySelector('.ms-up'),dn=fila.querySelector('.ms-dn');
      if(up){up.onclick=e=>{e.stopPropagation();mover(t,-1)};dn.onclick=e=>{e.stopPropagation();mover(t,1)}}
      fila.addEventListener('click',e=>{if(e.target.closest('input,button'))return;if(!t.sinAudio)alternarEditor(t)});
      if(abierta&&!t.sinAudio)cablearEditor(w.querySelector('.ms-ed'),t);
      cont.appendChild(w);
    });
    if(S.fuera.length){const r=document.createElement('div');r.className='ms-rec';r.innerHTML=`<button class="chip" id="ms-recup">↩ Recuperar las quitadas (${S.fuera.length})</button>`;cont.appendChild(r);r.querySelector('button').onclick=()=>{if(!confirmarOcupado())return;S.fuera=[];guardar();recargarPistas()}}
    resumen();pintarMarcas();T.forEach(t=>{if(abiertas.has(t.id))dibujar(t)});pintarCuadro();
  }
  function pintarCuadro(){} // (hueco: aquí se refrescan las cifras que dependen de los ajustes)
  const confirmarOcupado=()=>{if(ocupado){GM.ui.toast('Espera a que termine lo que se está haciendo.');return false}return true};
  function recargarPistas(){parar();T.forEach(t=>{t.ch=null});T.length=0;abiertas.clear();construirPistas();pintarPistas();T.forEach(cargarInfo)}
  function mover(t,d){   // solo mixtapes: el orden se refleja en mixtape.items
    if(!confirmarOcupado())return;
    const L=T.filter(x=>!x.manual),i=L.indexOf(t),k=i+d;if(k<0||k>=L.length)return;
    const a=T.indexOf(t),b=T.indexOf(L[k]);[T[a],T[b]]=[T[b],T[a]];
    const ids=T.filter(x=>!x.manual).map(x=>x.id),its=g.mix.items;
    g.mix.items=ids.map(id=>its.find(x=>x.id===id)).concat(its.filter(x=>!ids.includes(x.id)));
    GM.mixSave();pintarPistas();resumen();
  }
  function quitar(t){
    if(!confirmarOcupado())return;
    if(motor.id===t.id){parar();motor.id=null;motor.off=0}
    abiertas.delete(t.id);
    if(t.manual){T.splice(T.indexOf(t),1)}
    else{S.fuera.push(t.id);T.splice(T.indexOf(t),1);guardar()}
    t.ch=null;pintarPistas();
  }
  function alternarEditor(t){
    if(abiertas.has(t.id)){abiertas.delete(t.id);liberar(t)}
    else{abiertas.add(t.id);if(motor.id==null&&!motor.sonando){motor.id=t.id;motor.off=0}}
    pintarPistas();
    if(abiertas.has(t.id))asegurar(t).then(()=>dibujar(t)).catch(()=>{});
  }

  /* ---------- editor desplegable de cada canción ---------- */
  function editorHtml(t){
    const p=t.p;
    return `<div class="ms-onda"><canvas class="ms-cv" data-id="${A(t.id)}"></canvas></div>
      <div class="ms-trans"><button class="ms-ib ms-grande ms-tp" data-id="${A(t.id)}" title="Reproducir / pausa">${sonando(t)?SVG.pausa:SVG.play}</button><span class="ms-tiempo" data-id="${A(t.id)}">0:00 / ${tiempo(durEd(t))}</span>
        <span class="meta">Arrastra las marcas de los extremos para recortar · haz clic en la onda para ir a ese punto</span>
        <label class="ms-chk ms-chk-s" style="margin-left:auto" title="Oír esta canción ya igualada al volumen objetivo"><input type="checkbox" class="ms-pn"${p.previewNorm?' checked':''}> Oír igualada</label></div>
      <div class="ms-ctl">
        <div><label>Recorte</label><div class="ms-btns"><button class="chip ms-ti">Empezar aquí</button><button class="chip ms-to">Terminar aquí</button><button class="chip ms-tr">Quitar recorte</button></div></div>
        <div><label>Fundido de entrada · <span class="ms-fiv">${num(p.fadeIn,2)} s</span></label><input type="range" class="ms-fi" min="0" max="10" step="0.05" value="${p.fadeIn}"></div>
        <div><label>Fundido de salida · <span class="ms-fov">${num(p.fadeOut,2)} s</span></label><input type="range" class="ms-fo" min="0" max="10" step="0.05" value="${p.fadeOut}"></div>
        <div><label>Silencio al principio (s)</label><input type="number" class="ms-pa" min="0" max="30" step="0.1" value="${p.padStart}"></div>
        <div><label>Silencio al final (s)</label><input type="number" class="ms-pb" min="0" max="30" step="0.1" value="${p.padEnd}"></div>
        <div><label>Artista de esta canción (si es distinto)</label><input type="text" class="ms-art" value="${A(p.artist)}" placeholder="${A(S.artista||'Artista '+X.de)}"></div>
      </div>
      <div class="ms-etq"><div class="ms-etqh"><b>Etiquetas</b><button class="chip ms-mas">＋ Añadir etiqueta</button></div>
        <div class="ms-auto">${etiquetasAuto(t).map(([k,v])=>`<span class="ms-tag"><b>${E(k)}</b> ${E(v)}</span>`).join('')}</div>
        <div>${p.meta.map((m,i)=>`<div class="ms-mrow" data-i="${i}"><input class="ms-mk" list="ms-claves" value="${A(m.key)}" placeholder="Etiqueta"><input class="ms-mv" value="${A(m.value)}" placeholder="Valor"><button class="ms-ib ms-md" title="Quitar etiqueta">${SVG.x}</button></div>`).join('')}</div></div>`;
  }
  function cambio(t){invalidar(t);if(sonando(t))reproducir(t,clamp(pos(),0,durEd(t)));dibujar(t);const f=el.querySelector('.ms-fila[data-id="'+CSS.escape(t.id)+'"]');if(f)filaEstado(t);pintarMarcas();recalcularGanancias();guardar()}
  function cablearEditor(ed,t){
    const cv=ed.querySelector('canvas'),p=t.p;
    cv.addEventListener('mousedown',e=>{if(!t.info)return;const r=cv.getBoundingClientRect(),x=e.clientX-r.left,xs=ini(t)/dur0(t)*r.width,xe=fin(t)/dur0(t)*r.width;
      if(Math.abs(x-xs)<9){arrastre.modo='ini';arrastre.t=t}else if(Math.abs(x-xe)<9){arrastre.modo='fin';arrastre.t=t}
      else{arrastre.modo='ir';arrastre.t=t;irA(t,origAEd(t,clamp(x/r.width,0,1)*dur0(t)))}});
    ed.querySelector('.ms-tp').onclick=()=>alternar(t);
    const posOrig=()=>sonando(t)||motor.id===t.id?edAOrig(t,sonando(t)?pos():motor.off):null;
    ed.querySelector('.ms-ti').onclick=()=>{const q=posOrig();p.trimStart=clamp(q==null?ini(t):q,0,fin(t)-0.05);cambio(t)};
    ed.querySelector('.ms-to').onclick=()=>{const q=posOrig();p.trimEnd=clamp(q==null?fin(t):q,ini(t)+0.05,dur0(t));cambio(t)};
    ed.querySelector('.ms-tr').onclick=()=>{p.trimStart=0;p.trimEnd=null;cambio(t)};
    ed.querySelector('.ms-fi').oninput=e=>{p.fadeIn=+e.target.value;ed.querySelector('.ms-fiv').textContent=num(p.fadeIn,2)+' s';cambio(t)};
    ed.querySelector('.ms-fo').oninput=e=>{p.fadeOut=+e.target.value;ed.querySelector('.ms-fov').textContent=num(p.fadeOut,2)+' s';cambio(t)};
    ed.querySelector('.ms-pa').oninput=e=>{p.padStart=Math.max(0,+e.target.value||0);cambio(t)};
    ed.querySelector('.ms-pb').oninput=e=>{p.padEnd=Math.max(0,+e.target.value||0);cambio(t)};
    ed.querySelector('.ms-art').oninput=e=>{p.artist=e.target.value;guardar()};
    ed.querySelector('.ms-pn').onchange=async e=>{p.previewNorm=e.target.checked;t.norm=null;guardar();if(motor.sonando&&motor.id===t.id)reproducir(t,clamp(pos(),0,durEd(t)));else if(p.previewNorm)try{await medir(t);recalcularGanancias()}catch(x){}dibujar(t)};
    ed.querySelector('.ms-mas').onclick=()=>{p.meta.push({key:'',value:''});guardar();pintarPistas()};
    ed.querySelectorAll('.ms-mrow').forEach(r=>{const i=+r.dataset.i;
      r.querySelector('.ms-mk').oninput=e=>{p.meta[i].key=e.target.value;guardar()};
      r.querySelector('.ms-mv').oninput=e=>{p.meta[i].value=e.target.value;guardar()};
      r.querySelector('.ms-md').onclick=()=>{p.meta.splice(i,1);guardar();pintarPistas()}});
  }
  const edAOrig=(t,e)=>{const a=t.p.padStart||0,core=fin(t)-ini(t);if(e<=a)return ini(t);if(e>=a+core)return fin(t);return ini(t)+(e-a)};
  const origAEd=(t,o)=>(t.p.padStart||0)+(clamp(o,ini(t),fin(t))-ini(t));
  window.addEventListener('mousemove',e=>{
    const t=arrastre.t;if(!arrastre.modo||!t||!t.info)return;const cv=el.querySelector('canvas.ms-cv[data-id="'+CSS.escape(t.id)+'"]');if(!cv)return;
    const r=cv.getBoundingClientRect(),tm=clamp((e.clientX-r.left)/r.width,0,1)*dur0(t);
    if(arrastre.modo==='ini'){t.p.trimStart=clamp(tm,0,fin(t)-0.05);invalidar(t);dibujar(t)}
    else if(arrastre.modo==='fin'){t.p.trimEnd=clamp(tm,ini(t)+0.05,dur0(t));invalidar(t);dibujar(t)}
    else irA(t,origAEd(t,tm));
  },{signal:sig});
  window.addEventListener('mouseup',()=>{const t=arrastre.t,m=arrastre.modo;arrastre.modo=null;arrastre.t=null;if(t&&(m==='ini'||m==='fin'))cambio(t)},{signal:sig});
  window.addEventListener('resize',()=>T.forEach(t=>{if(abiertas.has(t.id))dibujar(t)}),{signal:sig});

  /* forma de onda (los colores salen de las variables del gestor, así sirve en claro y oscuro) */
  const css=n=>getComputedStyle(el).getPropertyValue(n).trim()||'#888';
  function dibujar(t){
    if(!t||!t.peaks||!t.info)return;const cv=el.querySelector('canvas.ms-cv[data-id="'+CSS.escape(t.id)+'"]');if(!cv)return;
    const dpr=window.devicePixelRatio||1,W0=cv.clientWidth||cv.parentElement.clientWidth||700,H0=140;
    if(cv.width!==Math.floor(W0*dpr)||cv.height!==Math.floor(H0*dpr)){cv.width=Math.floor(W0*dpr);cv.height=Math.floor(H0*dpr)}
    const c=cv.getContext('2d'),W=cv.width,H=cv.height,mid=H/2,dur=dur0(t),pk=t.peaks;c.clearRect(0,0,W,H);
    let amp=0.95;if(t.p.previewNorm&&t.lufs!=null&&t.lufs>-70&&t.gain!=null)amp*=clamp(dbALin(t.gain),0,3.5);
    const x0=ini(t)/dur*W,x1=fin(t)/dur*W,colOn=css(t.p.previewNorm?'--good':'--accent'),colOff=css('--muted');
    for(let x=0;x<W;x++){const b=Math.min(pk.res-1,Math.floor(x/W*pk.res)),yT=clamp(mid-pk.max[b]*mid*amp,0,H),yB=clamp(mid-pk.min[b]*mid*amp,0,H);
      c.strokeStyle=(x>=x0&&x<=x1)?colOn:colOff;c.globalAlpha=(x>=x0&&x<=x1)?0.95:0.35;c.beginPath();c.moveTo(x+0.5,yT);c.lineTo(x+0.5,Math.max(yB,yT+1));c.stroke()}
    c.globalAlpha=1;
    const core=Math.max(0.0001,fin(t)-ini(t)),top=mid-mid*0.9,fiPx=(t.p.fadeIn/core)*(x1-x0),foPx=(t.p.fadeOut/core)*(x1-x0),warn=css('--warn');
    c.strokeStyle=warn;c.lineWidth=dpr*1.5;c.beginPath();c.moveTo(x0,t.p.fadeIn>0?mid:top);c.lineTo(x0+fiPx,top);c.lineTo(x1-foPx,top);c.lineTo(x1,t.p.fadeOut>0?mid:top);c.stroke();
    c.fillStyle=warn;[x0,x1].forEach(x=>{c.fillRect(x-dpr*1.5,0,dpr*3,H);c.fillRect(x-dpr*5,0,dpr*10,dpr*16);c.fillRect(x-dpr*5,H-dpr*16,dpr*10,dpr*16)});
    const pp=motor.id===t.id?edAOrig(t,sonando(t)?pos():motor.off):ini(t),px=clamp(pp/dur*W,0,W);
    c.strokeStyle=css('--txt');c.lineWidth=dpr*1.5;c.beginPath();c.moveTo(px,0);c.lineTo(px,H);c.stroke();c.fillStyle=css('--txt');c.beginPath();c.arc(px,dpr*6,dpr*4,0,Math.PI*2);c.fill();
  }

  /* barra del álbum */
  const tl=$('#ms-alinea'),fr=e=>{const r=tl.getBoundingClientRect();return clamp((e.clientX-r.left)/r.width,0,1)};
  tl.addEventListener('mousedown',e=>{scrub=fr(e);$('#ms-arell').style.width=(scrub*100)+'%';$('#ms-acab').style.left=(scrub*100)+'%'});
  window.addEventListener('mousemove',e=>{if(scrub==null)return;scrub=fr(e);$('#ms-arell').style.width=(scrub*100)+'%';$('#ms-acab').style.left=(scrub*100)+'%';$('#ms-acur').textContent=tiempo(scrub*totalAlbum())},{signal:sig});
  window.addEventListener('mouseup',()=>{if(scrub==null)return;const f=scrub;scrub=null;irAlbum(f*totalAlbum())},{signal:sig});
  $('#ms-aplay').onclick=()=>{const t=actual();if(t)alternar(t)};
  $('#ms-aprev').onclick=()=>vecina(-1);$('#ms-anext').onclick=()=>vecina(1);$('#ms-aback').onclick=()=>saltar(-5);$('#ms-afwd').onclick=()=>saltar(5);
  $('#ms-anorm').onchange=async e=>{
    const on=e.target.checked;
    if(on&&activas().some(t=>t.lufs==null))await medirTodas();
    activas().forEach(t=>{t.p.previewNorm=on;t.norm=null});guardar();
    const a=actual();if(motor.sonando&&a)reproducir(a,clamp(pos(),0,durEd(a)));pintarPistas();
  };

  /* ---------- medir ---------- */
  async function medirTodas(){
    const L=activas();
    for(let i=0;i<L.length;i++){
      const t=L[i];progreso(i/L.length);$('#ms-estadoOp').textContent=`Midiendo ${i+1} de ${L.length}…`;
      try{if(t.lufs==null)await medir(t)}catch(e){t.error=e.message;t.estadoCarga='error';log(`✗ «${nombreDe(t)}»: ${e.message}`,'warn')}
      liberar(t);filaEstado(t);await ceder();
    }
    recalcularGanancias();progreso(-1);$('#ms-estadoOp').textContent='';
  }
  async function analizar(){
    if(!confirmarOcupado())return;ocupado=true;resumen();
    log('Midiendo la sonoridad de cada canción (LUFS)…','info');
    try{
      T.forEach(t=>{if(!t.sinAudio){t.lufs=null}});await medirTodas();
      activas().forEach(t=>log(`  ${nombreDe(t)}: ${num(t.lufs)} LUFS · pico ${isFinite(t.pico)?num(t.pico):'-∞'} dB → ${t.gain==null?'—':(t.gain>=0?'+':'')+num(t.gain)+' dB'}`));
      log('Medición terminada.','ok');
    }finally{ocupado=false;resumen()}
  }

  /* ---------- efectos: 5 huecos FX1…FX5 + «Con efectos / Original» ---------- */
  let fxH=null,fxMontado=false,fxT=null,fxST=null;
  function fxResumen(){
    const n=S.fx.cadena.length,pro=Object.keys(S.fx.porPista).length;
    $('#ms-fxres').textContent=!n?'Sin efectos definidos (el audio pasa tal cual). Pulsa «Configurar» para añadir hasta 5.':
      (S.fx.on?`Con efectos: ${S.fx.cadena.filter(x=>x.on!==false).length} de ${n} hueco(s) activos${pro?` · ${pro} pista(s) con ajuste propio`:''}`:'Original: los efectos están saltados (no se oyen ni se exportan).');
    el.querySelectorAll('#ms-fxsw button').forEach(b=>b.classList.toggle('pri',(b.dataset.v==='1')===S.fx.on));
    $('#ms-fxsw').hidden=!n;
  }
  function fxBtnsHtml(t){
    if(!FX_ACTIVO||!GM.mods.vst||!S.fx.cadena.length||t.sinAudio)return '';
    const {m,off}=fxM(t);
    return S.fx.cadena.map((x,i)=>`<button class="ms-fxb1${m[i]&&!off?' on':''}${x.on===false?' dim':''}" data-i="${i}" title="${A((x.nombre||x.clase||'Efecto')+(x.on===false?' (apagado en la cadena)':''))}">FX${i+1}</button>`).join('')+`<button class="ms-fxb1 ms-fxoff${off?' on':''}" title="Todos los efectos apagados en esta pista">∅</button>`;
  }
  function fxBtns(t){const c=el.querySelector('.ms-fila[data-id="'+CSS.escape(t.id)+'"] .ms-fxb');if(!c)return;c.innerHTML=fxBtnsHtml(t);c.classList.toggle('apag',!S.fx.on)}
  const fxBtnsTodos=()=>T.forEach(fxBtns);
  function fxToggle(t,bt){
    const o=S.fx.porPista[t.id]=S.fx.porPista[t.id]||{m:[1,1,1,1,1],off:0};
    if(bt.dataset.i!=null){const i=+bt.dataset.i;o.m[i]=o.m[i]===0?1:0}else o.off=o.off?0:1;
    if(o.off===0&&o.m.every(v=>v!==0))delete S.fx.porPista[t.id];
    fxCambio(t);
  }
  function fxCambio(t){
    guardar();fxRevisar(t);fxBtns(t);fxResumen();
    if(EM.vivo)emPista(t);else fxDif();
  }
  function fxDif(){   // sin motor en directo: la comparación es por render (se vuelve a procesar la canción actual)
    clearTimeout(fxT);fxT=setTimeout(()=>{const a=actual();if(a&&!a.sinAudio&&a.fxKey!==undefined)fxReprocesar([a],motor.sonando?pos():null)},700);
  }
  async function fxReprocesar(L,reanudar){
    if(ocupado||!vivo)return;const sono=motor.sonando&&reanudar!=null;parar();ocupado=true;resumen();
    L.forEach(t=>{t.ch=null;t.edBuf=null;t.norm=null;t.lufs=null;t.pico=null;t.gain=null;t.error='';t.estadoCarga='espera'});
    try{
      let i=0;for(const t of L){$('#ms-estadoOp').textContent=`Aplicando efectos ${++i} de ${L.length}: ${nombreDe(t)}`;await cargarInfo(t)}
      log('Efectos '+(S.fx.on?'aplicados':'quitados')+' en '+L.length+' pista(s).','ok');
    }catch(e){log('✗ '+e.message,'warn')}
    finally{if(vivo){ocupado=false;$('#ms-estadoOp').textContent='';resumen();fxResumen();recalcularGanancias();if(sono){const t=L[0];reproducir(t,clamp(reanudar,0,durEd(t)))}}}
  }
  function fxConmutar(on){
    if(S.fx.on===on)return;S.fx.on=on;guardar();T.forEach(fxRevisar);fxBtnsTodos();fxResumen();
    if(EM.vivo){emCmd({c:'efectos',on});emGainPush()}else fxDif();
  }
  async function fxMotorUi(){
    const b=el.querySelector('#ms-fxmotor');if(!b||!FX_ACTIVO)return;
    if(!GM.mods.vst){b.textContent='';return}
    let e=null;try{e=await GM.mods.vst.estado()}catch(x){}
    if(!b.isConnected)return;
    if(!e||!e.pedalboard){b.innerHTML='<span class="meta">Para usar efectos hay que instalar el soporte de plugins (en la sección «Efectos» del gestor). La masterización funciona igual sin ellos.</span>';return}
    if(EM.vivo&&EM.est)b.innerHTML=`🔊 <b>Escucha en directo</b> · salida «${E(e.sd_salida||EM.est.sink)}» · bloques de ${EM.est.bloque} muestras · latencia ≈ ${EM.est.latencia_ms} ms. El reproductor del navegador queda en silencio mientras suena; los botones FX se oyen al instante.`;
    else if(!e.sounddevice&&!sinkTest())b.innerHTML=`<span class="meta">Sin el motor en directo, «Con efectos / Original» compara procesando la canción antes (tarda unos segundos en cada cambio). Para oírlo al instante hace falta «sounddevice».</span> <button class="chip" id="ms-sdinst">Instalar motor en directo</button>`;
    else b.innerHTML=`<span class="meta">${EM.fallo&&EM.motivo?E(EM.motivo):'La escucha en directo (sin esperas al cambiar efectos) se activa sola al pulsar ▶ cuando hay efectos definidos.'}</span>`;
    const bt=b.querySelector('#ms-sdinst');
    if(bt)bt.onclick=async()=>{bt.disabled=true;const r=await GM.mods.vst.motor.instalarSonido();if(r.ok){EM.fallo=false;GM.ui.toast('Motor en directo instalado ✓')}else if(!r.cancelado)GM.ui.toast(r.error||'No se pudo instalar');fxMotorUi()};
  }
  async function fxAbrir(){
    const b=$('#ms-fxbody');b.hidden=!b.hidden;$('#ms-fxtog').textContent=b.hidden?'▾ Configurar':'▴ Ocultar';
    if(b.hidden||fxMontado)return;fxMontado=true;
    if(!GM.mods.vst){$('#ms-fxed').innerHTML='<div class="callout">El módulo de efectos no está instalado en este gestor. La masterización funciona igual, sin efectos.</div>';return}
    fxH=await GM.mods.vst.montarCadena($('#ms-fxed'),{cadena:S.fx.cadena,max:5,onChange:l=>{
      const antes=S.fx.cadena.length;S.fx.cadena=JSON.parse(JSON.stringify(l)).slice(0,5);
      if(!antes&&S.fx.cadena.length&&!S.fx.on)S.fx.on=true;
      guardar();T.forEach(fxRevisar);fxBtnsTodos();fxResumen();
      if(EM.vivo){clearTimeout(fxST);fxST=setTimeout(()=>{EM.sig='';emCmd({c:'slots',items:S.fx.cadena});emGainPush()},450)}else fxDif();
    }});
  }
  $('#ms-fxtog').onclick=fxAbrir;
  el.querySelectorAll('#ms-fxsw button').forEach(b=>b.onclick=()=>fxConmutar(b.dataset.v==='1'));

  /* ---------- exportar ---------- */
  async function renderizar(L,destino){
    const total=L.length,relleno=Math.max(2,String(total).length);
    if(S.modo==='album'||L.some(t=>t.lufs==null)){log('Midiendo antes de exportar…','info');await medirTodas()}
    const copyAuto=()=>{const ti=((GM.cfg&&GM.cfg.titular)||'').trim();return ti?'© '+(String(S.anio||'').trim()||new Date().getFullYear())+' '+ti:''};
    const tags0={album:g.title,albumArtist:S.artista.trim(),year:String(S.anio||'').trim(),genre:S.genero.trim(),lang:S.idioma,copyright:g.mix&&GM.mixCopy?GM.mixCopy(g.mix):copyAuto()};
    const todasAct=activas();
    const res=[];
    for(let i=0;i<total;i++){
      const t=L[i];progreso(i/total);$('#ms-estadoOp').textContent=`Procesando ${i+1} de ${total}: ${nombreDe(t)}`;
      await asegurar(t);
      let ed=editar(t);const sr=t.info.sampleRate;t.ch=mantener(t)?t.ch:null; // el original se suelta en cuanto hay copia editada
      t.gain=ganancia(t);if(t.gain==null)t.gain=t.lufs<=-70?0:S.lufs-t.lufs;
      await ceder();aplicarGanancia(ed,dbALin(t.gain));
      /* Los efectos (módulo vst) ya se aplicaron al cargar la pista (traerFx): lo que se mide y se edita es el audio con efectos. */
      await ceder();if(S.techo!==0)limitar(ed,sr,techoLin());
      await ceder();
      const tags={...tags0,title:nombreDe(t),artist:(t.p.artist||'').trim()||tags0.albumArtist,track:`${todasAct.indexOf(t)+1}/${todasAct.length}`,meta:t.p.meta,composer:(t.p.artist||'').trim()||tags0.albumArtist,lyrics:(GM.lyrics&&GM.lyrics(t.id)||'').trim()};
      const wav=codificarWav(ed,sr,S.bits,tags,S.portada?portada:null,S.dither&&S.bits===16);
      ed=null;await ceder();
      const num2=String(todasAct.indexOf(t)+1).padStart(relleno,'0');
      const r=await destino(t,num2,wav);
      res.push(r);
      log(`  ✓ ${r.nombre} · ${t.gain>=0?'+':''}${num(t.gain)} dB · ${num(wav.length/1048576)} MB${r.nota?' · '+r.nota:''}`,'ok');
      liberar(t);filaEstado(t);await ceder();
    }
    return res;
  }
  function paramsTexto(){return `${S.bits===32?'32 bits flotante':S.bits+' bits'} · objetivo ${S.lufs} LUFS · techo ${num(S.techo)} dB · ${S.modo==='pista'?'cada canción al mismo volumen':'respetando diferencias'}`}
  async function exportarZip(){
    if(!confirmarOcupado())return;const L=activas();if(!L.length)return;
    ocupado=true;resumen();log(`Preparando el ZIP · ${L.length} canciones · ${paramsTexto()}…`,'info');
    try{
      const zip=new ZipSinCompresion();
      await renderizar(L,async(t,n,wav)=>{const nombre=`${n} - ${nombreSeguro(nombreDe(t))}.wav`;zip.add(nombre,wav);return {nombre}});
      const blob=zip.blob(),nm=nombreSeguro(g.title)+' (máster).zip';
      descargar(blob,nm);progreso(-1);
      log(`ZIP listo: ${nm} · ${num(blob.size/1048576)} MB.`,'ok');GM.ui.toast('ZIP listo: '+nm);
    }catch(e){progreso(-1);log('✗ No se pudo crear el ZIP: '+e.message,'warn')}
    finally{ocupado=false;$('#ms-estadoOp').textContent='';resumen()}
  }
  async function guardarEnBiblioteca(){
    if(g.mix)return guardarMix();
    if(!confirmarOcupado())return;
    const L=activas().filter(t=>t.song),omit=activas().filter(t=>!t.song);
    if(!L.length)return;
    let ya={};try{const r=await GM.api(ID,'masters?ids='+encodeURIComponent(L.map(t=>t.id).join(',')));if(r.ok)ya=r.masters||{}}catch(e){}
    const hay=Object.values(ya).reduce((a,x)=>a+x.length,0);
    const ok=await GM.ui.ask('Guardar másters en la biblioteca',
      `Se crearán <b>${L.length} archivos WAV</b> (${E(paramsTexto())}), cada uno en la carpeta <b>master</b> de su canción (se crea si no existe).<br><br>`+
      `<b>No se borra ni se sobrescribe nada</b>${hay?`: ya hay ${hay} archivo(s) en esas carpetas <i>master</i>; si algún nombre coincide, el nuevo llevará « (2)» al final`:''}.`+
      (omit.length?`<br><br>${omit.length} pista(s) añadidas a mano no se guardan aquí (no son de ninguna canción).`:'')+
      `<br><br>Puede tardar unos minutos; puedes seguir viendo la página mientras tanto.`,'Guardar másters');
    if(!ok)return;
    ocupado=true;resumen();log(`Guardando ${L.length} másters en la biblioteca · ${paramsTexto()}…`,'info');
    let guardados=0,fallos=0;
    try{
      await renderizar(L,async(t,n,wav)=>{
        const nombre=`${n} - ${nombreSeguro(nombreDe(t))} (máster).wav`;
        const r=await GM.api(ID,`guardar_master?id=${encodeURIComponent(t.id)}&nombre=${encodeURIComponent(nombre)}`,new Blob([wav],{type:'audio/wav'}));
        if(!r||!r.ok){fallos++;throw new Error((r&&r.error)||'el servidor no respondió')}
        guardados++;return {nombre:r.ruta,nota:r.renombrado?'ya existía uno con ese nombre: se añadió « (n)»':''};
      });
      progreso(-1);
      const msg=`Guardados ${guardados} másters en la carpeta master de sus canciones.`;
      log('✓ '+msg,'ok');informes[g.key]=msg+' Ya aparecen como versiones de cada canción.';
      GM.ui.toast(msg);
      destruir();GM.ui.reload();return;       // vuelve a leer las carpetas para que aparezcan
    }catch(e){progreso(-1);log(`✗ Se detuvo tras guardar ${guardados} de ${L.length}: ${e.message}`,'warn');if(guardados){GM.ui.toast('Se guardaron '+guardados+' másters; hubo un problema con el siguiente.')}}
    finally{if(vivo){ocupado=false;$('#ms-estadoOp').textContent='';resumen()}}
  }
  const mixEstado=()=>{
    const n=Object.keys(S.mixMasters).length,usados=g.mix.items.filter(it=>MIXM.test(it.p||'')).length;
    $('#ms-mixbar').innerHTML=n?`<div class="callout"><b>Másters del mixtape guardados (${n}).</b> ${usados?`El mixtape ya los usa (${usados}).`:'El mixtape todavía usa las versiones originales.'}
      <div class="ms-acciones"><button class="chip pri" id="ms-mixusar">Usar en este mixtape</button><button class="chip" id="ms-mixvolver"${usados?'':' disabled'}>Volver a las versiones originales</button></div></div>`:'';
    if(!n)return;
    $('#ms-mixusar').onclick=()=>{
      let c=0;g.mix.items.forEach(it=>{const r=S.mixMasters[it.id];if(!r)return;if(!MIXM.test(it.p||''))S.origMix[it.id]=it.p||null;it.p=r;c++});
      guardar();GM.mixSave();GM.ui.toast('El mixtape usa ahora los másters ('+c+')');mixEstado();
    };
    $('#ms-mixvolver').onclick=()=>{
      g.mix.items.forEach(it=>{if(MIXM.test(it.p||'')){const o=S.origMix[it.id];if(o)it.p=o;else delete it.p}});
      guardar();GM.mixSave();GM.ui.toast('El mixtape vuelve a sus versiones originales');mixEstado();
    };
  };
  async function guardarMix(){
    if(!confirmarOcupado())return;
    const L=activas().filter(t=>t.song);if(!L.length)return;
    const ok=await GM.ui.ask('Guardar másters del mixtape',
      `Se crearán <b>${L.length} archivos WAV</b> (${E(paramsTexto())}) en la carpeta <b>MIXTAPES/_masters</b> de este mixtape. <b>No se toca ninguna carpeta master de tus canciones</b> ni se sobrescribe nada (si un nombre coincide, el nuevo lleva « (2)»).<br><br>Después podrás elegir «Usar en este mixtape» para que sus MP3 salgan de estos másters.`,'Guardar másters');
    if(!ok)return;
    ocupado=true;resumen();log(`Guardando ${L.length} másters del mixtape · ${paramsTexto()}…`,'info');
    let n=0;
    try{
      await renderizar(L,async(t,num2,wav)=>{
        const nombre=`${num2} - ${nombreSeguro(nombreDe(t))}.wav`;
        const r=await GM.api(ID,`guardar_master?mix=${encodeURIComponent(g.mix.id)}&id=${encodeURIComponent(t.id)}&nombre=${encodeURIComponent(nombre)}`,new Blob([wav],{type:'audio/wav'}));
        if(!r||!r.ok)throw new Error((r&&r.error)||'el servidor no respondió');
        S.mixMasters[t.id]=r.ruta;n++;guardar();return {nombre:r.ruta};
      });
      progreso(-1);log(`✓ Guardados ${n} másters del mixtape.`,'ok');mixEstado();
    }catch(e){progreso(-1);log(`✗ Se detuvo tras guardar ${n} de ${L.length}: ${e.message}`,'warn');mixEstado()}
    finally{if(vivo){ocupado=false;$('#ms-estadoOp').textContent='';resumen()}}
  }
  $('#ms-analizar').onclick=analizar;$('#ms-zip').onclick=exportarZip;$('#ms-bib').onclick=guardarEnBiblioteca;

  /* ---------- añadir WAV a mano (extra): no se recuerdan al recargar ---------- */
  async function anadir(files){
    const L=[...files].filter(f=>/\.wav$/i.test(f.name)||/wav/i.test(f.type));
    if(!L.length){log('Solo se pueden añadir archivos WAV a mano.','warn');return}
    L.forEach(f=>{
      const id='m'+Date.now().toString(36)+(manualN++);
      const t=pistaDe(id,Object.assign(pista0(),{name:f.name.replace(/\.wav$/i,'')}),{file:f,manual:true,titulo:f.name.replace(/\.wav$/i,'')});
      T.push(t);cargarInfo(t);
    });
    pintarPistas();log(`${L.length} archivo(s) añadidos a mano. Ojo: estos no se recuerdan al recargar la página.`,'info');
  }
  $('#ms-anadir').onclick=()=>$('#ms-file').click();
  $('#ms-file').onchange=e=>{anadir(e.target.files);e.target.value=''};
  const zona=$('.ms-der');
  ['dragenter','dragover'].forEach(n=>zona.addEventListener(n,e=>{if(e.dataTransfer&&[...e.dataTransfer.types].includes('Files')){e.preventDefault();zona.classList.add('arrastrando')}}));
  ['dragleave','drop'].forEach(n=>zona.addEventListener(n,e=>{zona.classList.remove('arrastrando')}));
  zona.addEventListener('drop',e=>{if(e.dataTransfer&&e.dataTransfer.files.length){e.preventDefault();anadir(e.dataTransfer.files)}});

  /* ---------- fin de la pestaña ---------- */
  function destruir(){
    if(!vivo)return;vivo=false;parar();clearInterval(EM.poll);if(EM.vivo){EM.vivo=false;try{GM.mods.vst.motor.cerrar()}catch(e){}}ab.abort();clearTimeout(guardaT);GM.save();
    if(portada&&portada.url)URL.revokeObjectURL(portada.url);
    T.forEach(t=>{t.ch=null;t.edBuf=null;t.norm=null});if(activa&&activa.g===g)activa=null;if(g.overlay)g.overlay.remove();
  }
  activa={destruir,g};

  /* ---------- arranque ---------- */
  pintarAjustes();construirPistas();pintarPistas();
  if(informes[g.key]){log('✓ '+informes[g.key],'ok')}
  cargarCaratula(g).then(c=>{
    if(!vivo)return;portada=c;
    $('#ms-cover').innerHTML=c?`<img src="${c.url}" alt="Carátula">`:'<span class="meta">Sin carátula elegida.<br>Ponla con «Cambiar portada» y se incrustará aquí.</span>';
    if(!c)$('#ms-portada').disabled=true;
  });
  T.forEach(cargarInfo);fxResumen();fxMotorUi();if(g.mix)mixEstado();
}

GM.register({
  id:ID,
  albumTab:{id:'tab',label:'🎚 Masterización',render(el,g,GM){montar(el,g)}},
  mixtapeAction:{label:'Masterizar',icon:'🎚',run(mix,GM){
    const g={key:'mix:'+mix.id,title:mix.name||'Mixtape',cover:null,mix,unica:true};
    const o=GM.ui.modal('<div style="display:flex;justify-content:flex-end;margin-bottom:8px"><button class="chip" id="ms-cerrar">✕ Cerrar</button></div><div id="ms-mont"></div>');
    g.overlay=o;o.firstChild.style.width='min(1180px,96vw)';o.firstChild.style.maxHeight='92vh';
    o.querySelector('#ms-cerrar').onclick=()=>o.remove();
    montar(o.querySelector('#ms-mont'),g);
    const ob=new MutationObserver(()=>{if(!document.body.contains(o)){ob.disconnect();if(activa&&activa.g===g)activa.destruir()}});ob.observe(document.body,{childList:true});
  }},
  songAction:{label:'Masterizar',icon:'🎚',run(song,GM){
    const g={key:'cancion:'+song.id,title:GM.title(song),cover:GM.cover(song),canciones:[song],unica:true};
    const o=GM.ui.modal('<div style="display:flex;justify-content:flex-end;margin-bottom:8px"><button class="chip" id="ms-cerrar">✕ Cerrar</button></div><div id="ms-mont"></div>');
    g.overlay=o;o.firstChild.style.width='min(1180px,96vw)';o.firstChild.style.maxHeight='92vh';
    o.querySelector('#ms-cerrar').onclick=()=>o.remove();
    montar(o.querySelector('#ms-mont'),g);
    const ob=new MutationObserver(()=>{if(!document.body.contains(o)){ob.disconnect();if(activa&&activa.g===g)activa.destruir()}});ob.observe(document.body,{childList:true});
  }},
});
})();
