import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cohortKey} from '../frontend/src/dashboardRequests.js';
import {createResearchBrief,renderResearchBrief,researchBriefHTML,revisionChanges,briefFilename} from '../frontend/src/researchBrief.js';

const cohort={mode:'live',drug:'METFORMIN',compare:'',start:'2025-01-01',end:'2025-01-31',age:'All',sex:'',reporters:''};
const source=()=>({key:cohortKey(cohort),sections:{
  core:{status:'ready',result:{basis:'same',freshness:{source:'cache',retrieved_at:'2026-10-24T12:00:00Z'},data:{summary:{total_reports:100},reactions:[{reaction:'NAUSEA',reports:0}],timeseries:[{date:'2025-01-06',count:100}],reports:[{text:'raw private record'}],api_key:'secret'}}},
  signals:{status:'ready',result:{basis:'same',generated_at:'2026-10-24T13:00:00Z',data:{signals:[{reaction:'NAUSEA',a:0,prr:2,prr_low:1,prr_high:3,ror:2.1,signal:false},{reaction:'NAUSEA, PERSISTENT',a:3,prr:5,signal:true}]}}}
}});
const input=requestState=>({cohort,view:'signals',reaction:'NAUSEA',periods:{},requestState,generatedAt:'2026-10-25T10:00:00Z'});

test('brief freezes exact reaction evidence, true zeros, retrieval times and applied context',()=>{
  const state=source(),brief=createResearchBrief({...input(state),pending:true});
  state.sections.core.result.data.summary.total_reports=999;
  assert.equal(brief.total,100);assert.equal(brief.signals.length,1);assert.equal(brief.signals[0].reaction,'NAUSEA');assert.equal(brief.signals[0].a,0);
  assert.equal(brief.signalCount,1);assert.equal(brief.signalCoverage,2);assert.equal(brief.sections[0].retrieved_at,'2026-10-24T12:00:00Z');
  assert.equal(brief.reactions[0].count,0);assert.equal(brief.pending,true);
  const html=renderResearchBrief(brief);assert.match(html,/Unapplied filter or period edits are excluded/);assert.match(html,/Below rule/);
  assert.ok(!JSON.stringify(brief).includes('raw private record'));assert.ok(!JSON.stringify(brief).includes('secret'));
});

test('foreign cohorts and mismatched calculation bases cannot enter a brief; retained failures are explicit',()=>{
  const state=source();state.sections.signals.result.basis='old';
  const mismatch=createResearchBrief(input(state));assert.deepEqual(mismatch.signals,[]);assert.equal(mismatch.signalCount,null);
  state.key=cohortKey({...cohort,drug:'IBUPROFEN'});
  const foreign=createResearchBrief(input(state));assert.equal(foreign.total,null);assert.deepEqual(foreign.timeseries,[]);
  const retained=source();retained.sections.signals.status='error';retained.sections.signals.error='FDA unavailable';
  const html=renderResearchBrief(createResearchBrief(input(retained)));
  assert.match(html,/last successful result/);assert.match(html,/FDA unavailable/);
});

test('HTML export escapes research text and chart labels and contains no scripts or external assets',()=>{
  const state=source(),attack='<img src="https://evil.test" onerror="alert(1)">';
  state.sections.core.result.data.reactions[0].reaction=attack;
  const brief=createResearchBrief({...input(state),active:{name:attack,notes:'</style><script>alert(1)</script>',revision:1,id:'local-id',updated_at:'2026-10-25T10:00:00Z',cohort,view:'signals',reaction:'NAUSEA',periods:{}}});
  const html=researchBriefHTML(brief,{events:[],historyStatus:'error'});
  assert.ok(!html.includes('<script'));assert.ok(!html.includes('<img'));assert.ok(!html.includes('<link'));assert.ok(!html.includes('<iframe'));
  assert.match(html,/&lt;img/);assert.match(html,/&lt;script&gt;/);assert.match(html,/Content-Security-Policy/);assert.match(html,/Timeline could not be retrieved/);
  assert.match(html,/<svg/);assert.equal(briefFilename(brief),'vigil-metformin-2026-10-25.html');
});

test('timeline distinguishes migrated history, notes changes and unknown earlier saves',()=>{
  const first={revision:4,kind:'legacy',snapshot:{name:'Study',cohort,reaction:'NAUSEA',view:'signals',notes:'Before',periods:{}}};
  const next={revision:5,kind:'updated',snapshot:{...first.snapshot,notes:'After',reaction:'RASH',cohort:{...cohort,sex:'Female'}}};
  assert.match(revisionChanges(first).join(' '),/Earlier saves were not recorded/);
  assert.deepEqual(revisionChanges(next,first),['Cohort / filters updated','Reaction focus updated','Research notes updated']);
});

test('synthetic briefs label the source and preserve unavailable data instead of reporting zero',()=>{
  const brief=createResearchBrief({...input({sections:{}}),cohort:{...cohort,mode:'reference'}});
  const html=renderResearchBrief(brief);assert.equal(brief.total,null);assert.match(html,/Synthetic demonstration data/);assert.match(html,/Missing evidence is not a zero/);
  assert.ok(!html.includes('href="https://open.fda.gov'));
});
