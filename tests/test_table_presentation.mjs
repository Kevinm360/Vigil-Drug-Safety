import test from 'node:test';
import assert from 'node:assert/strict';
import {columnLabel,tableValue} from '../frontend/src/tablePresentation.js';
test('report values distinguish missing evidence, true zero, identifiers, and small model metrics',()=>{
  assert.equal(tableValue(null,'prr'),'—');
  assert.equal(tableValue(NaN,'accuracy'),'—');
  assert.equal(tableValue(0,'a'),'0');
  assert.equal(tableValue(43541,'count'),'43,541');
  assert.equal(tableValue(2026,'year'),'2026');
  assert.equal(tableValue(.0061,'importance_share'),'0.006');
  assert.equal(tableValue(2.45,'prr'),'2.45');
  assert.equal(tableValue(.91366,'roc_auc'),'0.914');
  assert.equal(tableValue(-.021,'f1_delta'),'-0.021');
  assert.equal(columnLabel('roc_auc'),'ROC AUC');
});
