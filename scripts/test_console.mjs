import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {prepareRun,physicalAt,communicationAt,stepTime,nextContact,availabilitySeconds,csvRows,serializableRun,reportText} from '../console/core.mjs';

const utc=seconds=>new Date(Date.parse('2025-11-09T12:00:00Z')+seconds*1000).toISOString();
function fixture(){
 const pass={pass_id:'p1',window_start:utc(0),window_end:utc(20),duration_s:20,
  samples:[{timestamp:utc(0),rf:{snr_db:0,available:true,shannon_capacity_bps:0},optical:{qber:0.5},qkd_asymptotic:{secret_key_rate_bit_s:0}},
           {timestamp:utc(10),rf:{snr_db:-10,available:false},optical:{qber:0.5},qkd_asymptotic:{secret_key_rate_bit_s:0}}],
  qkd_finite_pass:{key_status:'aborted',secure_key_bits:0,abort_reason:'Insufficient detections'}};
 return {format:'console_run.v1',run_id:'test',start_time:utc(0),end_time:utc(30),
  frames:{position:'ITRF',velocity:'ITRF'},request:{},telemetry:[0,10,20,30].map(t=>({timestamp:utc(t),position_m:[7078137,t,0]})),
  events:[{id:'one',label:'Model condition',start:utc(2),end:utc(15),kind:'disturbance',targets:['rf_data']}],
  baseline:{passes:[structuredClone(pass)]},scenario:{scenario_name:'test',passes:[structuredClone(pass)]},limitations:['A prototype estimate.']};
}
test('No future samples or communication values leak into playback',()=>{
 const run=prepareRun(fixture()),start=run.startMs;
 assert.equal(physicalAt(run,start+5000).position_m[1],0);
 assert.equal(communicationAt(run,start+5000).rf.snr_db,0);
 assert.equal(communicationAt(run,start+25000),null);
});
test('Step/reset operations use recorded timestamps',()=>{
 const run=prepareRun(fixture()),start=run.startMs;
 assert.equal(stepTime(run,start+15000,-1),start+10000);
 assert.equal(stepTime(run,start+15000,1),start+20000);
 assert.equal(nextContact(run,start),start);
});
test('Availability is time-weighted, not a count of green samples',()=>{
 const run=prepareRun(fixture());assert.equal(availabilitySeconds(run.scenario),10);
});
test('Zero keys, zero SNR and negative results survive report/export roundtrip',()=>{
 const run=prepareRun(fixture());
 const roundtrip=prepareRun(JSON.parse(JSON.stringify(serializableRun(run))));
 assert.equal(roundtrip.scenario.passes[0].qkd_finite_pass.secure_key_bits,0);
 assert.match(csvRows(run),/0,true,0/);assert.match(reportText(run),/bits=0/);
});
test('Reject unaligned cases, duplicate events, false frames and non-finite geometry',()=>{
 for(const change of [r=>r.baseline.passes[0].samples.pop(),r=>r.events.push(structuredClone(r.events[0])),r=>r.frames.position='INERTIAL',r=>r.telemetry[0].position_m[0]=NaN]){
  const value=fixture();change(value);assert.throws(()=>prepareRun(value));
 }
});
test('Raw legacy channel results cannot masquerade as an orbital recording',()=>{assert.throws(()=>prepareRun({passes:[]}));});
if(process.env.CONSOLE_RUN)test('Actual Orekit console recording has aligned cases and strict JSON',()=>{
 const run=prepareRun(JSON.parse(fs.readFileSync(process.env.CONSOLE_RUN,'utf8')));
 assert.ok(run.telemetry.length>2);assert.ok(run.scenario.passes.length>0);
 assert.equal(run.baseline._series.length,run.scenario._series.length);
 for(let i=0;i<run.scenario._series.length;i++){
  assert.equal(run.baseline._series[i].timestamp,run.scenario._series[i].timestamp);
  assert.ok(Math.abs(run.baseline._series[i].rf.snr_db-run.scenario._series[i].rf.snr_db-20)<1e-7);
  assert.equal(run.baseline._series[i].optical.qber,run.scenario._series[i].optical.qber);
 }
});
