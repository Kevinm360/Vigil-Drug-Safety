import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DashboardRequests,assembleDashboard,cohortKey,sectionState} from '../frontend/src/dashboardRequests.js';

const cohort={mode:'live',drug:'METFORMIN',compare:'',start:'2025-01-01',end:'2025-01-31',age:'All',sex:'',reporters:''};
function result(section,subject=cohort,basis='same'){
  const patches={core:{meta:{warnings:[]},summary:{total_reports:10,signal_count:null},reactions:[{reaction:'NAUSEA',reports:4,compare_reports:null}],timeseries:[{date:'2025-01-06',count:10,compare_count:null}],graph:{nodes:[{id:'subject',type:'drug',label:subject.drug},{id:'rx',type:'reaction',label:'NAUSEA',a:4}],links:[{source:'subject',target:'rx',value:4}]}},signals:{signals:[{reaction:'NAUSEA',a:4,prr:3}],summary:{signal_count:1}},severity:{severity:{outcomes:[],demographics:[],reactions:[]},summary:{serious_reports:0}},reports:{reports:[]}};
  return {section,cohort:subject,basis,data:patches[section],status:'ready',freshness:{source:'cache'},generated_at:'2026-10-25T10:00:00Z'};
}
const response=value=>({ok:true,json:async()=>value});

test('validated API filter lists match the applied string-based controls',()=>{
  assert.equal(cohortKey(cohort),cohortKey({...cohort,sex:[],reporters:[]}));
  assert.equal(cohortKey({...cohort,sex:'Female',reporters:'Physician,Consumer'}),cohortKey({...cohort,sex:['Female'],reporters:['Physician','Consumer']}));
});

test('a section retry leaves other results intact, including the last good result after failure',async()=>{
  let fail=false;const calls=[];
  const loader=new DashboardRequests(()=>{},async url=>{const section=new URL(url,'http://localhost').searchParams.get('section');calls.push(section);if(fail&&section==='signals')throw new Error('FDA unavailable');return response(result(section))});
  await loader.start(cohort);const core=loader.state.sections.core.result,reports=loader.state.sections.reports.result;
  fail=true;calls.length=0;await loader.retry('signals');
  assert.deepEqual(calls,['signals']);assert.equal(loader.state.sections.core.result,core);assert.equal(loader.state.sections.reports.result,reports);
  assert.equal(loader.state.sections.signals.status,'error');assert.equal(assembleDashboard(loader.state).signals[0].prr,3);
  fail=false;await loader.retry('signals');assert.equal(loader.state.sections.signals.status,'ready');
});

test('late successes and late failures cannot overwrite a newer cohort or its error state',async()=>{
  const pending=[];const loader=new DashboardRequests(()=>{},(url,options)=>new Promise((resolve,reject)=>pending.push({url,resolve,reject,signal:options.signal})));
  const old=loader.start(cohort),next={...cohort,drug:'IBUPROFEN'};const fresh=loader.start(next);
  assert.equal(pending[0].signal.aborted,true);assert.equal(assembleDashboard(loader.state),null);
  pending[0].reject(new Error('Late old error'));await old;assert.equal(loader.state.sections.core.status,'loading');
  pending[1].resolve(response(result('core',next)));await new Promise(resolve=>setImmediate(resolve));
  for(const request of pending.slice(2)){const section=new URL(request.url,'http://localhost').searchParams.get('section');request.resolve(response(result(section,next)))}
  await fresh;assert.equal(loader.state.key,cohortKey(next));assert.equal(loader.state.sections.core.status,'ready');
});

test('the latest retry wins even when cancellation is ignored by a transport',async()=>{
  let defer=false;const pending=[];
  const loader=new DashboardRequests(()=>{},async url=>{const section=new URL(url,'http://localhost').searchParams.get('section');if(defer)return new Promise(resolve=>pending.push(resolve));return response(result(section))});
  await loader.start(cohort);defer=true;const first=loader.retry('signals'),second=loader.retry('signals');
  const newer=result('signals');newer.data={signals:[{reaction:'NAUSEA',prr:7}],summary:{signal_count:1}};
  pending[1](response(newer));await second;pending[0](response(result('signals')));await first;
  assert.equal(assembleDashboard(loader.state).signals[0].prr,7);
});

test('sections with changed calculation counts require a cohort refresh instead of mixing denominators',async()=>{
  const loader=new DashboardRequests(()=>{},async url=>{const section=new URL(url,'http://localhost').searchParams.get('section');return response(result(section,cohort,section==='signals'?'changed':'same'))});
  await loader.start(cohort);assert.equal(loader.state.sections.signals.needsRefresh,true);assert.equal(sectionState(loader.state,'signals').result,undefined);
  assert.equal(assembleDashboard(loader.state).summary.signal_count,null);
});

test('comparison counts, week alignment, and signal metadata survive merging in either completion order',()=>{
  const comparison={...result('comparison'),data:{comparison_reactions:[{reaction:'NAUSEA',reports:4,compare_reports:0}],summary:{compare_total:0},comparison:{status:'complete'},comparison_timeseries:[{date:'2025-01-06',compare_count:0}],comparison_graph:{nodes:[{id:'subject',type:'drug',label:'METFORMIN'},{id:'other',type:'drug',label:'IBUPROFEN'},{id:'rx',type:'reaction',label:'NAUSEA',a:4,value:4}],links:[{source:'subject',target:'rx',value:4},{source:'other',target:'rx',value:0}]}}};
  const state={sections:Object.fromEntries(['core','signals'].map(name=>[name,{result:result(name)}]))};state.sections.comparison={result:comparison};
  const data=assembleDashboard(state);assert.equal(data.reactions[0].compare_reports,0);assert.equal(data.timeseries[0].compare_count,0);assert.equal(data.graph.nodes.at(-1).prr,3);assert.equal(data.graph.nodes.at(-1).a,4);assert.equal(data.graph.links[1].value,0);
});
