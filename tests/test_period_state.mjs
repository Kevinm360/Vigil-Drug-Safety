import {test} from 'node:test';
import assert from 'node:assert/strict';
import {previousPeriod,periodPreset,changesKey,filterChanges} from '../frontend/src/periodState.js';
import {snapshotKey} from '../frontend/src/investigationState.js';

test('equal inclusive periods cross leap day and month/year boundaries without overlap',()=>{
  assert.deepEqual(previousPeriod({start:'2024-03-01',end:'2024-03-30'}),{baseline_start:'2024-01-31',baseline_end:'2024-02-29'});
  assert.deepEqual(periodPreset('2025-06-29',90),{start:'2025-04-01',end:'2025-06-29',baseline_start:'2025-01-01',baseline_end:'2025-03-31'});
  assert.deepEqual(previousPeriod({start:'1900-01-01',end:'1900-01-31'}),{});
});
test('comparison results stay tied to date windows and subject filters, excluding comparison drug',()=>{
  const cohort={mode:'live',drug:'METFORMIN',start:'2025-04-01',end:'2025-06-29',age:'All',sex:'',reporters:''};
  const periods=previousPeriod(cohort),key=changesKey(cohort,periods);
  assert.notEqual(key,changesKey({...cohort,sex:'Female'},periods));
  assert.notEqual(key,changesKey(cohort,{...periods,baseline_start:'2025-01-02'}));
  assert.equal(key,changesKey({...cohort,compare:'IBUPROFEN'},periods));
});
test('saved workspaces recognize baseline edits and retain compatibility with previous saves',()=>{
  const value={cohort:{start:'2025-04-01',end:'2025-06-29'},view:'signals',reaction:'NAUSEA'};
  assert.equal(snapshotKey(value),snapshotKey({...value,periods:previousPeriod(value.cohort)}));
  assert.notEqual(snapshotKey(value),snapshotKey({...value,periods:{baseline_start:'2025-02-01',baseline_end:'2025-03-31'}}));
});
test('table filters preserve unknown counts and distinguish only-current from unavailable',()=>{
  const rows=[{reaction:'A',direction:'higher',current_only:true,sparse:true,current_count:12,baseline_count:0,share_delta_pp:2},
    {reaction:'B',direction:'unavailable',current_only:false,sparse:false,current_count:10,baseline_count:null,share_delta_pp:null},
    {reaction:'C',direction:'lower',current_only:false,sparse:false,current_count:8,baseline_count:30,share_delta_pp:-3}];
  assert.deepEqual(filterChanges(rows,{direction:'current_only'}).map(row=>row.reaction),['A']);
  assert.deepEqual(filterChanges(rows,{direction:'unavailable',minimum:25}).map(row=>row.reaction),['B']);
  assert.deepEqual(filterChanges(rows).map(row=>row.reaction),['C','A','B']);
  assert.deepEqual(filterChanges(rows,{search:'c'}).map(row=>row.reaction),['C']);
});
