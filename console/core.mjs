// Pure record adapters and timeline operations. No orbital or communication models.
export const finite = value => typeof value === 'number' && Number.isFinite(value);
export function utcMs(value) {
 if (typeof value !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) throw new Error('A valid, timezone-qualified UTC timestamp is required.');
 return Date.parse(value);
}
export function indexAtOrBefore(values, time, getTime = v => v.time) {
 let low=0, high=values.length-1, found=-1;
 while(low<=high){const middle=(low+high)>>1;if(getTime(values[middle])<=time){found=middle;low=middle+1;}else high=middle-1;}return found;
}
export function eventState(event,time){if(time<event.startMs)return 'scheduled';return time<=event.endMs&&event.endMs>event.startMs?'active':'completed';}
export function prepareRun(input) {
 let run=structuredClone(input);
 if(run.schema_version==='1.0'&&Array.isArray(run.samples))run=physicalAdapter(run);
 if(run.format!=='console_run.v1')throw new Error('Import a Threat Analysis Console run or schema 1.0 experiment.json. Raw legacy result.json is not a globe recording.');
 const start=utcMs(run.start_time),end=utcMs(run.end_time);
 if(end<=start||!Array.isArray(run.telemetry)||run.telemetry.length<2||run.telemetry.length>100000)throw new Error('The recording needs a positive interval and 2–100,000 physical samples.');
 let previous=-Infinity;
 for(const item of run.telemetry){item.time=utcMs(item.timestamp);if(item.time<=previous||item.time<start||item.time>end||!Array.isArray(item.position_m)||item.position_m.length!==3||!item.position_m.every(finite))throw new Error('Invalid or unordered orbital samples.');previous=item.time;}
 if(run.frames?.position!=='ITRF'||run.frames?.velocity!=='ITRF')throw new Error('The console requires explicit ITRF orbital coordinates.');
 if(!Array.isArray(run.events))throw new Error('Event records must be an array.');
 if(run.study!=null&&!Array.isArray(run.study.rows))throw new Error('Scenario study rows must be an array.');
 const seen=new Set();for(const item of run.events){if(typeof item.id!=='string'||seen.has(item.id))throw new Error('Events need unique IDs.');seen.add(item.id);item.startMs=utcMs(item.start);item.endMs=utcMs(item.end);if(item.endMs<item.startMs||item.startMs<start||item.startMs>end)throw new Error('Event times are outside this recording.');}
 for(const name of ['baseline','scenario']){
  const result=run[name];if(!result||!Array.isArray(result.passes))throw new Error('Missing comparison records.');
  result._series=[];
  for(const [i,pass] of result.passes.entries()){
   pass.startMs=utcMs(pass.window_start);pass.endMs=utcMs(pass.window_end);
   if(pass.endMs<pass.startMs||pass.startMs<start||pass.endMs>end||!Array.isArray(pass.samples))throw new Error('Invalid contact bounds.');
   let last=-Infinity;for(const item of pass.samples){item.time=utcMs(item.timestamp);item.passIndex=i;if(item.time<pass.startMs||item.time>pass.endMs+1||item.time<=last)throw new Error('Communication samples must match their contact window.');last=item.time;result._series.push(item);}
  }
  result._series.sort((a,b)=>a.time-b.time);
 }
 const a=run.baseline.passes,b=run.scenario.passes;
 if(a.length!==b.length||a.some((pass,i)=>pass.startMs!==b[i].startMs||pass.endMs!==b[i].endMs||pass.samples.length!==b[i].samples.length||pass.samples.some((sample,j)=>sample.time!==b[i].samples[j].time)))throw new Error('The comparison cases do not share aligned contact windows and sample timestamps.');
 run.startMs=start;run.endMs=end;run.events.sort((a,b)=>a.startMs-b.startMs);return run;
}
function physicalAdapter(record){
 const metadata=record.metadata;
 return {format:'console_run.v1',run_id:metadata.run_id,start_time:metadata.start_time,end_time:metadata.end_time,
  request:metadata.config||{},period_seconds:null,frames:{position:'ITRF',velocity:'ITRF'},station:null,
  telemetry:record.samples.map(s=>({timestamp:s.timestamp,position_m:s.state.position,velocity_m_s:s.state.velocity,altitude_m:s.state.altitude,in_eclipse:s.state.in_eclipse})),
  events:record.events.map(e=>({id:e.event_id,label:e.event_type.replaceAll('_',' '),start:e.timestamp,end:new Date(utcMs(e.timestamp)+e.duration_seconds*1000).toISOString(),kind:'prototype',targets:e.targets,description:e.description+' Uncalibrated surrogate event; channel metrics are not included in this physical recording.',severity:e.severity})),
  baseline:{passes:[],config_summary:{}},scenario:{passes:[],scenario_name:'Physical baseline',config_summary:{}},
  limitations:[...(metadata.assumptions||[]),'Physical experiment import: station geometry and communication comparison were not recorded. No channel results have been inferred.'],model_status:'physical_baseline'};
}
export function physicalAt(run,time){const i=indexAtOrBefore(run.telemetry,time);return i<0?null:run.telemetry[i];}
export function passAt(run,time,which='scenario'){return run[which].passes.find(p=>time>=p.startMs&&time<=p.endMs)||null;}
export function communicationAt(run,time,which='scenario'){
 const pass=passAt(run,time,which);if(!pass)return null;
 const index=indexAtOrBefore(pass.samples,time);return index<0?null:pass.samples[index];
}
export function stepTime(run,time,direction){
 const i=indexAtOrBefore(run.telemetry,time);
 if(direction>0)return run.telemetry[Math.min(run.telemetry.length-1,i+1)].time;
 const target=i>=0&&run.telemetry[i].time<time?i:i-1;return run.telemetry[Math.max(0,target)].time;
}
export function nextContact(run,time){return run.scenario.passes.find(p=>p.startMs>time+1)?.startMs??run.scenario.passes[0]?.startMs??run.startMs;}
export function availabilitySeconds(result){
 if(!result._series?.length)return null;let seconds=0;
 for(const pass of result.passes)for(let i=0;i<pass.samples.length;i++){
  const sample=pass.samples[i];const end=Math.min(pass.endMs,pass.samples[i+1]?.time??pass.endMs);
  if(sample.rf?.available===true)seconds+=Math.max(0,end-sample.time)/1000;
 }return seconds;
}
export function getMetric(sample,path){let value=sample;for(const key of path.split('.'))value=value?.[key];return finite(value)?value:null;}
const csvEscape=value=>{const text=value==null?'':String(value);return /[",\n\r]/.test(text)?'"'+text.replaceAll('"','""')+'"':text;};
/** One row per scenario: the paper's results table, including the uncertainty range. */
export function studyCsv(study){
 const columns=['scenario_id','scenario','passes','ecdh_sessions','mlkem_sessions','qkd_passes_with_key','qkd_key_bits_nominal','qkd_key_bits_min','qkd_key_bits_max','qkd_pass_qber','attack_verdict','attack_detected','main_qkd_abort_reason'];
 const rows=[columns];for(const r of study.rows){const n=r.nominal;rows.push([r.scenario_id,r.name,n.passes,n.ecdh_passes,n.mlkem_passes,n.qkd_passes,Math.round(n.qkd_key_bits),Math.round(r.qkd_key_bits_min),Math.round(r.qkd_key_bits_max),n.qkd_qber,r.detection.verdict,r.detection.text,n.main_abort_reason]);}
 return rows.map(row=>row.map(csvEscape).join(',')).join('\r\n');
}
export function csvRows(run){
 const columns=['timestamp_utc','case','elevation_deg','range_m','rf_snr_db','rf_available','shannon_capacity_bps','optical_loss_db','photon_detection_hz','qber','asymptotic_key_rate_bit_s'];
 const escape=value=>{const text=value==null?'':String(value);return /[",\n\r]/.test(text)?'"'+text.replaceAll('"','""')+'"':text;};
 const rows=[columns];for(const name of ['baseline','scenario'])for(const s of run[name]._series)rows.push([s.timestamp,name,s.elev_deg,s.range_m,s.rf?.snr_db,s.rf?.available,s.rf?.shannon_capacity_bps,s.optical?.total_loss_db,s.optical?.signal_count_hz,s.optical?.qber,s.qkd_asymptotic?.secret_key_rate_bit_s]);
 return rows.map(row=>row.map(escape).join(',')).join('\r\n');
}
export function reportText(run){return [
 'Quantum Satellites Simulator — recorded experiment summary',`Run: ${run.run_id}`,`Scenario: ${run.scenario.scenario_name||'Physical baseline'}`,`UTC: ${run.start_time} to ${run.end_time}`,
 `Contacts: ${run.scenario.passes.length}`,`Baseline sampled RF availability: ${availabilitySeconds(run.baseline)??'not recorded'} s`,
 `Selected sampled RF availability: ${availabilitySeconds(run.scenario)??'not recorded'} s`,
 'All channel and key outputs are engineering estimates. No actual application messages were encrypted.',
 'QKD key is credited only when the authenticated RF link can carry post-processing (time and traffic check); the messages themselves are not executed. No blanket quantum-security conclusion follows.',
 ...(run.study?['','All scenarios (nominal QKD key; range over the optical uncertainty sweep):',...run.study.rows.map(r=>`${r.name}: ECDH ${r.nominal.ecdh_passes}/${r.nominal.passes}, ML-KEM ${r.nominal.mlkem_passes}/${r.nominal.passes}, QKD ${Math.round(r.nominal.qkd_key_bits)} bits [${Math.round(r.qkd_key_bits_min)}-${Math.round(r.qkd_key_bits_max)}]; ${r.detection.text}`)]:[]),
 '', 'Pass outcomes:',...run.scenario.passes.map((p,i)=>`Pass ${i+1}: ${p.window_start} to ${p.window_end}; finite-key estimate=${p.qkd_finite_pass?.key_status??'unknown'}; bits=${p.qkd_finite_pass?.secure_key_bits??'unknown'}; reason=${p.qkd_finite_pass?.abort_reason??'none recorded'}`),
 '', 'Assumptions and limitations:',...(run.limitations||[]).map(x=>'- '+x)].join('\n');}
export function serializableRun(run){const copy=structuredClone(run);delete copy.startMs;delete copy.endMs;for(const sample of copy.telemetry)delete sample.time;for(const event of copy.events){delete event.startMs;delete event.endMs;}for(const name of ['baseline','scenario']){delete copy[name]._series;for(const pass of copy[name].passes){delete pass.startMs;delete pass.endMs;for(const sample of pass.samples){delete sample.time;delete sample.passIndex;}}}return copy;}
