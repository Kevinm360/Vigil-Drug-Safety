import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_COHORT, loadCohort, saveCohort, exportForView } from '../frontend/src/workspaceState.js';

test('FDA is the initial source, migrating earlier cohorts once while preserving later explicit choices',()=>{
  const storage=new Map();
  storage.getItem=key=>storage.get(key)??null;
  storage.setItem=storage.set.bind(storage);
  assert.equal(loadCohort(storage).mode,'live');
  storage.set('vigil.applied-cohort.v1',JSON.stringify({...DEFAULT_COHORT,mode:'reference',drug:'IBUPROFEN'}));
  assert.equal(loadCohort(storage).drug,'IBUPROFEN');
  assert.equal(loadCohort(storage).mode,'live');
  saveCohort(storage,{...DEFAULT_COHORT,mode:'reference'});
  assert.equal(loadCohort(storage).mode,'reference');
});

test('only applied cohort fields survive a reload, without sensitive analysis data', () => {
  const storage = new Map();
  storage.setItem = storage.set.bind(storage);
  storage.getItem = storage.get.bind(storage);
  const applied = { ...DEFAULT_COHORT, drug: 'IBUPROFEN', compare: 'METFORMIN', mode: 'live' };
  saveCohort(storage, { ...applied, narrative: 'private text', api_key: 'not-for-storage', model: {} });
  assert.deepEqual(loadCohort(storage), applied);
  assert.ok(![...storage.values()].join('').includes('private text'));
  assert.ok(![...storage.values()].join('').includes('not-for-storage'));
});

test('malformed or unavailable browser storage recovers a usable cohort', () => {
  for (const value of ['broken-json', 'null', JSON.stringify({ ...DEFAULT_COHORT, start: '2025-02-30' }),
    JSON.stringify({ ...DEFAULT_COHORT, end: '2023-01-01' }),
    JSON.stringify({ ...DEFAULT_COHORT, sex: 'unsupported' })]) {
    assert.deepEqual(loadCohort({ getItem: () => value }), DEFAULT_COHORT);
  }
  assert.deepEqual(loadCohort({ getItem: () => { throw new Error('blocked'); } }), DEFAULT_COHORT);
  assert.doesNotThrow(() => saveCohort({ setItem: () => { throw new Error('blocked'); } }, DEFAULT_COHORT));
});

test('each research view exports its own evidence rather than unrelated signal rows', () => {
  const data = { timeseries: [{ date: '2025-01-01', count: 10 }],
    reactions: [{ reaction: 'NAUSEA', reports: 4 }], signals: [{ reaction: 'NAUSEA', prr: 2 }],
    reports: [{ safetyreportid: 'real-report' }], narratives: { records: [{ id: 'archive-review' }] },
    severity: { reactions: [{ reaction: 'NAUSEA', serious: 2 }] }, model: { audit: [{ predictor: 'age' }] } };
  assert.deepEqual(exportForView('overview', data).rows, data.timeseries);
  assert.deepEqual(exportForView('reactions', data).rows, data.reactions);
  assert.deepEqual(exportForView('reports', data).rows, data.reports);
  assert.deepEqual(exportForView('reports', data, { reference: true }).rows, data.narratives.records);
  assert.deepEqual(exportForView('severity', data).rows, data.severity.reactions);
  assert.deepEqual(exportForView('models', data).rows, data.model.audit);
  assert.deepEqual(exportForView('models', data, { model: { evaluation: { comparison: [{ model: 'LR' }] } } }).rows, [{ model: 'LR' }]);
  assert.deepEqual(exportForView('signals', data, { signals: [] }).rows, []);
});

test('narrative and comparison-network exports retain the actual data source and counts', () => {
  const ownText = { records: [{ id: 1, source: 'user-provided text', text: 'No seizure.' }] };
  assert.deepEqual(exportForView('narratives', { signals: [] }, { narratives: ownText }).rows, ownText.records);
  const data = { graph: { nodes: [{ id: 'drug:B', label: 'B' },
    { id: 'rx', label: 'NAUSEA', a: 4, prr: 2, ror: 3 }],
    links: [{ source: 'drug:B', target: 'rx', value: 7 }] } };
  assert.deepEqual(exportForView('network', data).rows, [{ drug: 'B', reaction: 'NAUSEA',
    co_occurrences: 7, primary_drug_count: 4, primary_drug_prr: 2, primary_drug_ror: 3 }]);
  assert.deepEqual(exportForView('overview', null).rows, []);
});
