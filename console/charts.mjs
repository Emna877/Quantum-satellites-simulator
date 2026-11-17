import {finite} from './core.mjs';
const NS='http://www.w3.org/2000/svg';
const colors={baseline:'#7d96ad',scenario:'#64d9ef',optical:'#b59fff',warning:'#eab477'};
function node(tag,attrs={},text){const element=document.createElementNS(NS,tag);for(const [key,value]of Object.entries(attrs))element.setAttribute(key,value);if(text!=null)element.textContent=text;return element;}
export const compact=value=>!finite(value)?'—':Math.abs(value)>=1e9?(value/1e9).toFixed(1)+'G':Math.abs(value)>=1e6?(value/1e6).toFixed(1)+'M':Math.abs(value)>=1e3?(value/1e3).toFixed(1)+'k':Math.abs(value)<.01&&value!==0?value.toExponential(1):Number(value.toFixed(2)).toString();
export function chart({title,unit,series,start,end,events=[],seek}){
 const card=document.createElement('article');card.className='chart-card';
 const heading=document.createElement('div');heading.className='chart-heading';const h=document.createElement('h3');h.textContent=title;const caption=document.createElement('small');caption.textContent=unit;heading.append(h,caption);card.append(heading);
 const all=series.flatMap(s=>s.points.filter(p=>p.time>=start&&p.time<=end&&finite(p.value)));
 if(!all.length){const empty=document.createElement('div');empty.className='chart-empty';empty.textContent='Not recorded for this interval.\nNo values have been substituted.';card.append(empty);return card;}
 const W=620,H=190,L=52,R=12,T=17,B=29;
 let low=Math.min(...all.map(p=>p.value)),high=Math.max(...all.map(p=>p.value));const nonNegative=low>=0;
 if(low===high){const pad=Math.max(1,Math.abs(low)*.1);low=Math.min(0,low-pad);high+=pad;}
 else{const pad=(high-low)*.1;low-=pad;high+=pad;}
 // Rates, counts and losses cannot be negative; padding must not suggest otherwise.
 if(nonNegative)low=Math.max(0,low);
 const x=t=>L+(t-start)/(end-start)*(W-L-R),y=v=>T+(high-v)/(high-low)*(H-T-B);
 const svg=node('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':`${title} over UTC time`});
 for(let i=0;i<4;i++){const v=low+(high-low)*i/3;svg.append(node('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),stroke:'#233344','stroke-width':.7}),node('text',{x:L-8,y:y(v)+3,'text-anchor':'end',fill:'#768fa5','font-size':9,'font-family':'monospace'},compact(v)));}
 for(const event of events.filter(e=>e.kind==='disturbance'&&e.endMs>start&&e.startMs<end)){svg.append(node('rect',{x:x(Math.max(start,event.startMs)),y:T,width:Math.max(1,x(Math.min(end,event.endMs))-x(Math.max(start,event.startMs))),height:H-T-B,fill:'#d88b6a',opacity:.035}));}
 for(const s of series){let path='',last=null;const points=s.points.filter(p=>p.time>=start&&p.time<=end);const gaps=points.slice(1).map((p,i)=>p.time-points[i].time).filter(n=>n>0).sort((a,b)=>a-b);const gap=gaps[Math.floor(gaps.length/2)]||Infinity;
  for(const point of points){if(!finite(point.value)){last=null;continue;}path+=(last&&point.time-last.time<=gap*2.1?'L':'M')+x(point.time).toFixed(2)+','+y(point.value).toFixed(2)+' ';last=point;}
  svg.append(node('path',{d:path,fill:'none',stroke:colors[s.color]||s.color||colors.scenario,'stroke-width':1.8,'stroke-linejoin':'round','stroke-linecap':'round'}));
  if(points.length===1&&finite(points[0].value))svg.append(node('circle',{cx:x(points[0].time),cy:y(points[0].value),r:3,fill:colors[s.color]||colors.scenario}));
 }
 for(let i=0;i<3;i++){const t=start+(end-start)*i/2;const label=new Date(t).toISOString().slice(11,19);svg.append(node('text',{x:x(t),y:H-8,'text-anchor':i===0?'start':i===2?'end':'middle',fill:'#7893a9','font-size':9,'font-family':'monospace'},label));}
 const cursor=node('line',{y1:T,y2:H-B,class:'chart-cursor'});svg.append(cursor);svg.dataset.chartStart=start;svg.dataset.chartEnd=end;svg.dataset.chartLeft=L;svg.dataset.chartRight=W-R;svg.dataset.chartWidth=W;
 svg.addEventListener('click',e=>{const rect=svg.getBoundingClientRect();const value=(e.clientX-rect.left)/rect.width*W;seek(Math.max(start,Math.min(end,start+(value-L)/(W-L-R)*(end-start))));});
 card.append(svg);const legend=document.createElement('div');legend.className='chart-caption';for(const s of series){const swatch=document.createElement('i');swatch.className='key';swatch.style.background=colors[s.color]||s.color;const label=document.createElement('span');label.textContent=s.label;legend.append(swatch,label);}card.append(legend);return card;
}
export function moveCursors(time){for(const svg of document.querySelectorAll('svg[data-chart-start]')){const start=Number(svg.dataset.chartStart),end=Number(svg.dataset.chartEnd);const line=svg.querySelector('.chart-cursor');const x=Number(svg.dataset.chartLeft)+(time-start)/(end-start)*(Number(svg.dataset.chartRight)-Number(svg.dataset.chartLeft));line.setAttribute('x1',x);line.setAttribute('x2',x);line.style.display=time<start||time>end?'none':'';}}
