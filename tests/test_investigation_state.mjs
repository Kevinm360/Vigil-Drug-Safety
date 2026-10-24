import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizeReaction,reactionChoices,snapshotKey} from '../frontend/src/investigationState.js';

test('reaction focus preserves complete exact terms, including punctuation',()=>{
  assert.equal(normalizeReaction(' Chest pain '),'CHEST PAIN');
  assert.equal(normalizeReaction(' Nausea, persistent '),'NAUSEA, PERSISTENT');
});
test('workspace changes compare normalized focus and cohort values independent of object key order',()=>{
  const cohort={mode:'live',drug:'METFORMIN',compare:'',start:'2025-01-01',end:'2025-01-31',age:'All',sex:'',reporters:''};
  const original={cohort,view:'signals',reaction:'Nausea'};
  assert.equal(snapshotKey(original),snapshotKey({...original,cohort:{...cohort},reaction:'NAUSEA'}));
  assert.notEqual(snapshotKey(original),snapshotKey({...original,cohort:{...cohort,drug:'IBUPROFEN'}}));
  assert.notEqual(snapshotKey(original),snapshotKey({...original,view:'reports'}));
});
test('focus choices include network-only comparison terms and deduplicate case variants',()=>{
  assert.deepEqual(reactionChoices({reactions:[{reaction:'Nausea'}],graph:{nodes:[{type:'reaction',label:'NAUSEA'},{type:'reaction',label:'Chest pain'},{type:'drug',label:'METFORMIN'}]}}),['CHEST PAIN','NAUSEA']);
});
