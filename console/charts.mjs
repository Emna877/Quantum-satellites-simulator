import {finite} from './core.mjs';
const NS='http://www.w3.org/2000/svg';
const colors={baseline:'#7d96ad',scenario:'#64d9ef',optical:'#b59fff',warning:'#eab477'};
// Print palette for exported figures: dark ink on white, same hue order as the screen.
const print={'#7d96ad':'#56677a','#64d9ef':'#0b7fa0','#b59fff':'#6a4fc9','#eab477':'#b5701c','#768fa5':'#333','#7893a9':'#333','#233344':'#d6d6d6','#9db3c6':'#333','#d88b6a':'#d88b6a'};
function node(tag,attrs={},text){const element=document.createElementNS(NS,tag);for(const [key,value]of Object.entries(attrs))element.setAttribute(key,value);if(text!=null)element.textContent=text;return element;}
export const compact=value=>!finite(value)?'—':Math.abs(value)>=1e9?(value/1e9).toFixed(1)+'G':Math.abs(value)>=1e6?(value/1e6).toFixed(1)+'M':Math.abs(value)>=1e3?(value/1e3).toFixed(1)+'k':Math.abs(value)<.01&&value!==0?value.toExponential(1):Number(value.toFixed(2)).toString();
const slug=text=>text.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
function save(name,blob){const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

/** Standalone, light-background SVG of a chart with title, axis titles and legend for papers. */
export function exportSvg(svg,{title,legend=[]}){
 const [,,width,height]=svg.getAttribute('viewBox').split(' ').map(Number);const head=30,foot=legend.length?24:6;
 const out=node('svg',{xmlns:NS,width,height:height+head+foot,viewBox:`0 0 ${width} ${height+head+foot}`,'font-family':'Helvetica, Arial, sans-serif'});
 out.append(node('rect',{x:0,y:0,width,height:height+head+foot,fill:'#fff'}),node('text',{x:12,y:20,'font-size':13,'font-weight':600,fill:'#111'},title));
 const body=svg.cloneNode(true);body.removeAttribute('role');body.removeAttribute('aria-label');body.setAttribute('y',head);body.setAttribute('width',width);body.setAttribute('height',height);body.removeAttribute('style');
 body.querySelector('.chart-cursor')?.remove();
 for(const item of body.querySelectorAll('[fill],[stroke]'))for(const key of ['fill','stroke']){const value=item.getAttribute(key);if(value&&print[value])item.setAttribute(key,print[value]);}
 for(const item of body.querySelectorAll('text'))item.setAttribute('font-family','Helvetica, Arial, sans-serif');
 out.append(body);
 let x=12;for(const entry of legend){const color=print[entry.color]||entry.color;out.append(node('line',{x1:x,x2:x+16,y1:height+head+12,y2:height+head+12,stroke:color,'stroke-width':2.5}),node('text',{x:x+21,y:height+head+16,'font-size':10,fill:'#333'},entry.label));x+=36+entry.label.length*6;}
 return {text:'<?xml version="1.0" encoding="UTF-8"?>\n'+new XMLSerializer().serializeToString(out),width,height:height+head+foot};
}
function svgToPng({text,width,height},scale=3){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>{const canvas=document.createElement('canvas');canvas.width=width*scale;canvas.height=height*scale;const context=canvas.getContext('2d');context.scale(scale,scale);context.drawImage(image,0,0,width,height);canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('PNG export failed.')),'image/png');};image.onerror=()=>reject(new Error('PNG export failed.'));image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(text);});}
function exportButtons(getSvg,title,legend){const tools=document.createElement('span');tools.className='chart-export';
 for(const format of ['SVG','PNG']){const button=document.createElement('button');button.type='button';button.className='text-button';button.textContent='↧ '+format;button.title=`Download "${title}" as ${format} for publication`;
  button.onclick=async event=>{event.stopPropagation();const figure=exportSvg(getSvg(),{title,legend});try{save(slug(title)+'.'+format.toLowerCase(),format==='SVG'?new Blob([figure.text],{type:'image/svg+xml'}):await svgToPng(figure));}catch(error){document.dispatchEvent(new CustomEvent('console-info',{detail:error.message}));}};tools.append(button);}
 return tools;}

export function chart({title,unit,series,start,end,events=[],seek}){
 const card=document.createElement('article');card.className='chart-card';
 const heading=document.createElement('div');heading.className='chart-heading';const h=document.createElement('h3');h.textContent=title;const caption=document.createElement('small');caption.textContent=unit;heading.append(h,caption);card.append(heading);
 const all=series.flatMap(s=>s.points.filter(p=>p.time>=start&&p.time<=end&&finite(p.value)));
 if(!all.length){const empty=document.createElement('div');empty.className='chart-empty';empty.textContent='Not recorded for this interval.\nNo values have been substituted.';card.append(empty);return card;}
 const W=620,H=200,L=58,R=12,T=12,B=38;
 let low=Math.min(...all.map(p=>p.value)),high=Math.max(...all.map(p=>p.value));const nonNegative=low>=0;
 if(low===high){const pad=Math.max(1,Math.abs(low)*.1);low=Math.min(0,low-pad);high+=pad;}
 else{const pad=(high-low)*.1;low-=pad;high+=pad;}
 // Rates, counts and losses cannot be negative; padding must not suggest otherwise.
 if(nonNegative)low=Math.max(0,low);
 const x=t=>L+(t-start)/(end-start)*(W-L-R),y=v=>T+(high-v)/(high-low)*(H-T-B);
 const svg=node('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':`${title} (${unit}) over UTC time`});
 for(let i=0;i<4;i++){const v=low+(high-low)*i/3;svg.append(node('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),stroke:'#233344','stroke-width':.7}),node('text',{x:L-6,y:y(v)+3,'text-anchor':'end',fill:'#768fa5','font-size':9,'font-family':'monospace'},compact(v)));}
 for(const event of events.filter(e=>e.kind==='disturbance'&&e.endMs>start&&e.startMs<end)){svg.append(node('rect',{x:x(Math.max(start,event.startMs)),y:T,width:Math.max(1,x(Math.min(end,event.endMs))-x(Math.max(start,event.startMs))),height:H-T-B,fill:'#d88b6a',opacity:.035}));}
 for(const s of series){let path='',last=null;const points=s.points.filter(p=>p.time>=start&&p.time<=end);const gaps=points.slice(1).map((p,i)=>p.time-points[i].time).filter(n=>n>0).sort((a,b)=>a-b);const gap=gaps[Math.floor(gaps.length/2)]||Infinity;
  for(const point of points){if(!finite(point.value)){last=null;continue;}path+=(last&&point.time-last.time<=gap*2.1?'L':'M')+x(point.time).toFixed(2)+','+y(point.value).toFixed(2)+' ';last=point;}
  svg.append(node('path',{d:path,fill:'none',stroke:colors[s.color]||s.color||colors.scenario,'stroke-width':1.8,'stroke-linejoin':'round','stroke-linecap':'round'}));
  if(points.length===1&&finite(points[0].value))svg.append(node('circle',{cx:x(points[0].time),cy:y(points[0].value),r:3,fill:colors[s.color]||colors.scenario}));
 }
 for(let i=0;i<3;i++){const t=start+(end-start)*i/2;const label=new Date(t).toISOString().slice(11,19);svg.append(node('text',{x:x(t),y:H-22,'text-anchor':i===0?'start':i===2?'end':'middle',fill:'#7893a9','font-size':9,'font-family':'monospace'},label));}
 // Axis titles, so an exported figure is self-describing.
 svg.append(node('text',{x:(L+W-R)/2,y:H-5,'text-anchor':'middle',fill:'#9db3c6','font-size':9},'Time (UTC)'),
  node('text',{x:11,y:(T+H-B)/2,'text-anchor':'middle',fill:'#9db3c6','font-size':9,transform:`rotate(-90 11 ${(T+H-B)/2})`},unit));
 const cursor=node('line',{y1:T,y2:H-B,class:'chart-cursor'});svg.append(cursor);svg.dataset.chartStart=start;svg.dataset.chartEnd=end;svg.dataset.chartLeft=L;svg.dataset.chartRight=W-R;svg.dataset.chartWidth=W;
 svg.addEventListener('click',e=>{const rect=svg.getBoundingClientRect();const value=(e.clientX-rect.left)/rect.width*W;seek(Math.max(start,Math.min(end,start+(value-L)/(W-L-R)*(end-start))));});
 const legend=series.map(s=>({label:s.label,color:colors[s.color]||s.color}));
 heading.append(exportButtons(()=>svg,title,legend));
 card.append(svg);const legendRow=document.createElement('div');legendRow.className='chart-caption';for(const entry of legend){const swatch=document.createElement('i');swatch.className='key';swatch.style.background=entry.color;const label=document.createElement('span');label.textContent=entry.label;legendRow.append(swatch,label);}card.append(legendRow);return card;
}

/** Horizontal range chart: one row per scenario, bar = sweep range, dot = nominal value. */
export function rangeChart({title,unit,rows,note}){
 const card=document.createElement('article');card.className='chart-card range-card';
 const heading=document.createElement('div');heading.className='chart-heading';const h=document.createElement('h3');h.textContent=title;const caption=document.createElement('small');caption.textContent=unit;heading.append(h,caption);card.append(heading);
 const W=760,L=232,R=70,T=8,row=21,B=36,H=T+rows.length*row+B;
 const high=Math.max(1e-9,...rows.map(r=>r.high))*1.05;const x=v=>L+v/high*(W-L-R);
 const svg=node('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':`${title} (${unit}) per scenario`});
 for(let i=0;i<5;i++){const v=high*i/4;svg.append(node('line',{x1:x(v),x2:x(v),y1:T,y2:H-B,stroke:'#233344','stroke-width':.7}),node('text',{x:x(v),y:H-B+13,'text-anchor':'middle',fill:'#768fa5','font-size':9,'font-family':'monospace'},compact(v)));}
 rows.forEach((r,i)=>{const cy=T+i*row+row/2;
  svg.append(node('text',{x:L-8,y:cy+3,'text-anchor':'end',fill:'#9db3c6','font-size':10},r.label));
  if(r.high<=0){svg.append(node('text',{x:L+4,y:cy+3,fill:'#eab477','font-size':9,'font-family':'monospace'},'0 · no key'));return;}
  svg.append(node('line',{x1:x(r.low),x2:x(r.high),y1:cy,y2:cy,stroke:'#b59fff','stroke-width':5,'stroke-linecap':'round',opacity:.45}),
   node('circle',{cx:x(r.value),cy,r:3.6,fill:'#b59fff'}),
   node('text',{x:Math.min(W-4,x(r.high)+8),y:cy+3,fill:'#768fa5','font-size':9,'font-family':'monospace'},compact(r.value)));
 });
 svg.append(node('text',{x:(L+W-R)/2,y:H-6,'text-anchor':'middle',fill:'#9db3c6','font-size':9},unit));
 heading.append(exportButtons(()=>svg,title,[{label:'nominal',color:'#b59fff'},{label:'range over uncertainty sweep',color:'#b59fff'}]));
 card.append(svg);if(note){const p=document.createElement('p');p.className='fine';p.textContent=note;card.append(p);}return card;
}
export function moveCursors(time){for(const svg of document.querySelectorAll('svg[data-chart-start]')){const start=Number(svg.dataset.chartStart),end=Number(svg.dataset.chartEnd);const line=svg.querySelector('.chart-cursor');const x=Number(svg.dataset.chartLeft)+(time-start)/(end-start)*(Number(svg.dataset.chartRight)-Number(svg.dataset.chartLeft));line.setAttribute('x1',x);line.setAttribute('x2',x);line.style.display=time<start||time>end?'none':'';}}
