/* «estado» module · CSV/TSV reader (no dependencies). Everything happens on the computer: the file is not uploaded anywhere.
   EstadoCSV.leer(arrayBuffer)  → {texto, codificacion}
   EstadoCSV.separador(texto)   → ',' | ';' | '\t' | '|'
   EstadoCSV.filas(texto, sep)  → [[cell,…],…]
   EstadoCSV.cabecera(filas)    → index of the header row (skips preambles such as «Informe de …»)
   EstadoCSV.decimal(filas, desde, columnas) → ',' | '.'
   EstadoCSV.numero(texto, dec) → number (or null)
   EstadoCSV.fecha(texto, orden)→ 'YYYY-MM' (or null);  EstadoCSV.ordenFechas(valores) → 'dmy' | 'mdy' | null (if ambiguous)
   EstadoCSV.norm / titulo / titulos(texto) → keys to match titles */
(function(root){
  const MESES={ene:1,enero:1,jan:1,january:1,feb:2,febrero:2,february:2,mar:3,marzo:3,march:3,abr:4,abril:4,apr:4,april:4,may:5,mayo:5,jun:6,junio:6,june:6,
    jul:7,julio:7,july:7,ago:8,agosto:8,aug:8,august:8,sep:9,sept:9,septiembre:9,setiembre:9,september:9,oct:10,octubre:10,october:10,nov:11,noviembre:11,november:11,dic:12,diciembre:12,dec:12,december:12};

  function leer(buf){
    const u=new Uint8Array(buf);let enc='utf-8',off=0;
    if(u[0]===0xEF&&u[1]===0xBB&&u[2]===0xBF){off=3}
    else if(u[0]===0xFF&&u[1]===0xFE){enc='utf-16le';off=2}
    else if(u[0]===0xFE&&u[1]===0xFF){enc='utf-16be';off=2}
    else{
      let z=0;const n=Math.min(u.length,2000);for(let i=1;i<n;i+=2)if(u[i]===0)z++;
      if(n>20&&z>n/2*.6)enc='utf-16le';
      else{try{new TextDecoder('utf-8',{fatal:true}).decode(u);}catch(e){enc='windows-1252'}}
    }
    const texto=new TextDecoder(enc).decode(off?u.subarray(off):u);
    const nombres={'utf-8':'UTF-8','utf-16le':'UTF-16','utf-16be':'UTF-16','windows-1252':'Windows (ANSI)'};
    return{texto,codificacion:nombres[enc]||enc};
  }

  function filas(texto,sep){
    const R=[];let f=[],c='',q=false,i=0;const n=texto.length;
    while(i<n){
      const ch=texto[i];
      if(q){
        if(ch==='"'){if(texto[i+1]==='"'){c+='"';i+=2;continue}q=false;i++;continue}
        c+=ch;i++;continue;
      }
      if(ch==='"'&&c===''){q=true;i++;continue}
      if(ch===sep){f.push(c);c='';i++;continue}
      if(ch==='\r'){i++;continue}
      if(ch==='\n'){f.push(c);R.push(f);f=[];c='';i++;continue}
      c+=ch;i++;
    }
    if(c!==''||f.length){f.push(c);R.push(f)}
    return R.filter(r=>r.some(x=>String(x).trim()!==''));
  }

  function separador(texto){
    const muestra=texto.slice(0,60000);
    let best=',',bestScore=-1;
    for(const s of [',',';','\t','|']){
      const R=filas(muestra,s).slice(0,40);
      if(R.length<1)continue;
      const cnt={};R.forEach(r=>cnt[r.length]=(cnt[r.length]||0)+1);
      const moda=+Object.keys(cnt).sort((a,b)=>cnt[b]-cnt[a])[0];
      if(moda<2)continue;
      const score=(cnt[moda]/R.length)*100+Math.min(moda,30);
      if(score>bestScore){bestScore=score;best=s}
    }
    return best;
  }

  const esNum=v=>/^[\s€$£¥]*[-+(]?[\s€$£¥]*\d[\d.,\s'’]*[)]?[\s€$£¥%]*$/.test(String(v).trim());
  function cabecera(R){
    const m=R.slice(0,40);if(!m.length)return 0;
    const cnt={};m.forEach(r=>cnt[r.length]=(cnt[r.length]||0)+1);
    const ancho=Math.max(...Object.keys(cnt).filter(k=>cnt[k]>=Math.min(2,m.length)).map(Number),2);
    for(let i=0;i<m.length;i++){
      const r=m[i];if(r.length<ancho)continue;
      const llenas=r.filter(x=>String(x).trim()!=='').length,nums=r.filter(x=>esNum(x)).length;
      if(llenas>=Math.max(2,r.length*.6)&&nums<=r.length*.25&&R[i+1])return i;
    }
    return 0;
  }

  function evidencia(v){
    v=String(v).replace(/[\s€$£¥%'’]/g,'').replace(/^[-+(]+|[)]+$/g,'');
    if(/^\d{1,3}(\.\d{3})+,\d+$/.test(v))return 'c';
    if(/^\d{1,3}(,\d{3})+\.\d+$/.test(v))return 'p';
    if(/^\d+,\d+$/.test(v))return /^\d{1,3},\d{3}$/.test(v)?null:'c';
    if(/^\d+\.\d+$/.test(v))return /^\d{1,3}\.\d{3}$/.test(v)?null:'p';
    return null;
  }
  function decimal(R,desde,cols,sep){
    let c=0,p=0;
    for(let i=desde;i<Math.min(R.length,desde+400);i++){
      (cols||R[i].map((_,k)=>k)).forEach(k=>{const e=evidencia(R[i][k]||'');if(e==='c')c++;else if(e==='p')p++});
    }
    if(c===p)return sep===';'?',':'.';
    return c>p?',':'.';
  }
  function numero(t,dec){
    if(t==null)return null;let s=String(t).trim();if(s===''||s==='-'||s==='—')return null;
    const neg=/^\(.*\)$/.test(s)||/^-/.test(s.replace(/^[€$£¥\s]+/,''));
    s=s.replace(/[^0-9.,]/g,'');if(!s)return null;
    if(dec===','){s=s.replace(/\./g,'').replace(',','.')}else{s=s.replace(/,/g,'')}
    const x=parseFloat(s);if(isNaN(x))return null;return neg?-x:x;
  }

  const p2=n=>String(n).padStart(2,'0');
  function ordenFechas(vals){
    let dmy=0,mdy=0;
    vals.forEach(v=>{const m=String(v).trim().match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})/);if(m){if(+m[1]>12)dmy++;if(+m[2]>12)mdy++}});
    if(dmy&&!mdy)return 'dmy';if(mdy&&!dmy)return 'mdy';return null;
  }
  function fecha(t,orden){
    if(t==null)return null;const s=String(t).trim();if(!s)return null;let m;
    if((m=s.match(/^(\d{4})[-\/.](\d{1,2})(?:[-\/.](\d{1,2}))?/))&&+m[2]>=1&&+m[2]<=12)return m[1]+'-'+p2(m[2]);
    if((m=s.match(/^(\d{4})(\d{2})(\d{2})?$/))&&+m[2]>=1&&+m[2]<=12)return m[1]+'-'+m[2];
    if((m=s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})/))){
      let a=+m[1],b=+m[2],y=+m[3];if(y<100)y+=2000;
      const mes=(orden==='mdy')?a:b;if(mes>=1&&mes<=12)return y+'-'+p2(mes);
    }
    if((m=s.match(/^(\d{1,2})[\/\-.](\d{4})$/))&&+m[1]>=1&&+m[1]<=12)return m[2]+'-'+p2(m[1]);
    const nrm=s.normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
    if((m=nrm.match(/(?:^|[^a-z])([a-z]{3,10})\.?[\s\-\/,]*(?:de\s+)?(\d{4}|\d{2})\b/))&&MESES[m[1]]){let y=+m[2];if(y<100)y+=2000;return y+'-'+p2(MESES[m[1]])}
    if((m=nrm.match(/\b(\d{4})[\s\-\/,]*([a-z]{3,10})\b/))&&MESES[m[2]])return m[1]+'-'+p2(MESES[m[2]]);
    if((m=nrm.match(/\b\d{1,2}\s+(?:de\s+)?([a-z]{3,10})\.?\s+(?:de\s+)?(\d{4})/))&&MESES[m[1]])return m[2]+'-'+p2(MESES[m[1]]);
    return null;
  }

  /* ----- titles ----- */
  const norm=s=>String(s==null?'':s).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/&/g,' and ').replace(/[^a-z0-9]+/g,' ').trim();
  const SUFIJOS='remaster(?:ed)?(?:\\s+\\d{4})?|\\d{4}\\s+remaster(?:ed)?|remasterizad[oa]|radio\\s+edit|single(?:\\s+version)?|album\\s+version|version|versi[oó]n|edit|mix|remix|live|en\\s+vivo|acoustic|ac[uú]stic[oa]|feat\\.?[^)\\]]*|ft\\.?[^)\\]]*|with\\s[^)\\]]*|con\\s[^)\\]]*|demo|instrumental|official[^)\\]]*|video[^)\\]]*|lyric[^)\\]]*|audio|bonus[^)\\]]*|explicit|clean|deluxe[^)\\]]*|prod\\.?[^)\\]]*';
  const reParen=new RegExp('\\s*[\\(\\[]\\s*(?:'+SUFIJOS+')\\s*[\\)\\]]','gi');
  const reGuion=new RegExp('\\s+[-–—]\\s+(?:'+SUFIJOS+')\\s*$','i');
  function titulo(s){ // «relaxed» key: without (Remastered), - Single, (feat. X)…
    let t=String(s==null?'':s);
    for(let i=0;i<3;i++){t=t.replace(reParen,'');t=t.replace(reGuion,'')}
    return norm(t);
  }
  const compacta=s=>norm(s).replace(/ /g,'');
  function distancia(a,b){ // Levenshtein sobre claves cortas
    if(a===b)return 0;if(!a.length)return b.length;if(!b.length)return a.length;
    let prev=Array.from({length:b.length+1},(_,i)=>i);
    for(let i=1;i<=a.length;i++){const cur=[i];for(let j=1;j<=b.length;j++)cur[j]=Math.min(prev[j]+1,cur[j-1]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));prev=cur}
    return prev[b.length];
  }
  function parecido(a,b){a=compacta(a);b=compacta(b);if(!a||!b)return 0;if(a.includes(b)||b.includes(a)){return Math.min(a.length,b.length)/Math.max(a.length,b.length)*.4+.6}
    return 1-distancia(a,b)/Math.max(a.length,b.length)}

  root.EstadoCSV={leer,filas,separador,cabecera,decimal,numero,fecha,ordenFechas,norm,titulo,compacta,parecido,esNum};
})(typeof window!=='undefined'?window:globalThis);
