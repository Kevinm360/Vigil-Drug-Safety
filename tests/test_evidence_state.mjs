import {test} from 'node:test';
import assert from 'node:assert/strict';
import {reactionEvidence,reactionReportKey,currentReactionReports,fetchReactionReports} from '../frontend/src/evidenceState.js';

const cohort={mode:'live',drug:'METFORMIN',compare:'IBUPROFEN',start:'2025-01-01',end:'2025-01-31',age:'All',sex:'Female',reporters:'Physician'};
const data={summary:{total_reports:100},reactions:[{reaction:'Nausea',reports:12,compare_reports:0}],signals:[{reaction:'NAUSEA',a:12,prr:2.5,prr_low:1.3,prr_high:4.8,signal:true}]};

test('drawer combines exact reaction counts and intervals without losing a genuine comparison zero',()=>{
  const result=reactionEvidence(data,' nausea ');
  assert.equal(result.count,12);
  assert.equal(result.share,12);
  assert.equal(result.comparisonCount,0);
  assert.equal(result.signal.prr_low,1.3);
  assert.equal(result.signal.prr_high,4.8);
  assert.equal(reactionEvidence(data,'NAUSEA, PERSISTENT').count,null);
});

test('missing or graph-only evidence remains unknown instead of becoming zero',()=>{
  const result=reactionEvidence({...data,graph:{nodes:[{label:'FATIGUE',value:999}]}},'FATIGUE');
  assert.equal(result.count,null);
  assert.equal(result.share,null);
  assert.equal(result.comparisonCount,null);
  assert.equal(result.signal,null);
  assert.equal(reactionEvidence({summary:{total_reports:0}},'NAUSEA',{total:0}).share,null);
  assert.equal(reactionEvidence(data,'NAUSEA',{total:101}).share,null);
  assert.equal(reactionEvidence(data,'NAUSEA',{total:0}).count,0);
});

test('late results never attach records to another reaction or cohort',()=>{
  const key=reactionReportKey(cohort,'NAUSEA'),loaded={key,loading:false,error:'',rows:[{id:'sample'}],total:1};
  assert.equal(currentReactionReports(loaded,key),loaded);
  assert.equal(currentReactionReports(loaded,reactionReportKey(cohort,'RASH')),null);
  assert.equal(currentReactionReports(loaded,reactionReportKey({...cohort,sex:'Male'},'NAUSEA')),null);
  assert.equal(currentReactionReports({...loaded,loading:true},key),null);
  assert.equal(currentReactionReports({...loaded,error:'FDA unavailable'},key),null);
});

test('drawer request retains exact term and every applied filter and supports cancellation',async()=>{
  const controller=new AbortController();let seen;
  const result=await fetchReactionReports(cohort,' nausea, persistent ',{signal:controller.signal,fetcher:async(url,options)=>{
    seen={url,options};return {ok:true,json:async()=>({reaction:'NAUSEA, PERSISTENT',total:0,records:[]})};
  }});
  const query=new URL(seen.url,'http://localhost').searchParams;
  for(const [key,value] of Object.entries(cohort))assert.equal(query.get(key),value);
  assert.equal(query.get('reaction'),'NAUSEA, PERSISTENT');
  assert.equal(seen.options.signal,controller.signal);
  assert.equal(result.total,0);
  await assert.rejects(fetchReactionReports(cohort,'NAUSEA',{signal:AbortSignal.abort(),fetcher:async(_,options)=>{options.signal.throwIfAborted()}}),{name:'AbortError'});
});

test('failed, incomplete, and mismatched responses cannot look like an empty result',async()=>{
  for(const response of [
    {ok:false,json:async()=>({error:'FDA unavailable'})},
    {ok:true,json:async()=>({reaction:'NAUSEA',records:[]})},
    {ok:true,json:async()=>({reaction:'RASH',total:5,records:[]})},
  ])await assert.rejects(fetchReactionReports(cohort,'NAUSEA',{fetcher:async()=>response}));
});
