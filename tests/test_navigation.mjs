import {test} from 'node:test';
import assert from 'node:assert/strict';
import {NAV_GROUPS,VIEW_NAV_LABELS,groupForView,groupDestination} from '../frontend/src/navigation.js';

test('every existing bookmarked view belongs to exactly one section',()=>{
  const routes=['overview','reactions','reports','signals','changes','severity','network','narratives','models'];
  const assigned=NAV_GROUPS.flatMap(group=>group.views);
  assert.deepEqual([...assigned].sort(),[...routes].sort());
  assert.equal(new Set(assigned).size,routes.length);
  for(const route of routes)assert.ok(VIEW_NAV_LABELS[route]);
});

test('deep links and saved investigation destinations select the correct section',()=>{
  for(const [view,section] of [['network','explore'],['signals','explore'],['changes','explore'],['reports','reports'],['severity','reports'],['narratives','lab'],['models','lab']]){
    assert.equal(groupForView(view).id,section);
  }
  assert.equal(groupForView('unknown').id,'overview');
});

test('section switching restores its last view and rejects unrelated remembered routes',()=>{
  assert.equal(groupDestination('explore'),'reactions');
  assert.equal(groupDestination('reports'),'reports');
  assert.equal(groupDestination('lab'),'narratives');
  assert.equal(groupDestination('explore',{explore:'network'}),'network');
  assert.equal(groupDestination('lab',{lab:'models'}),'models');
  assert.equal(groupDestination('reports',{reports:'network'}),'reports');
  assert.equal(groupDestination('missing',{missing:'models'}),'overview');
});
