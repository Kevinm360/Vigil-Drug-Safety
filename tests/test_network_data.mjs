import test from 'node:test';
import assert from 'node:assert/strict';
import {relationshipData,connectionCount} from '../frontend/src/networkData.js';

test('comparison network retains source-specific counts and subject-only statistics',()=>{
  const graph=relationshipData({nodes:[
    {id:'A',type:'drug',label:'Subject'}, {id:'B',type:'drug',label:'Comparison'},
    {id:'nausea',type:'reaction',label:'Nausea',a:4,value:13,prr:2.4},
    {id:'rash',type:'reaction',label:'Rash',a:0,value:3}
  ],links:[{source:'A',target:'nausea',value:4},{source:'B',target:'nausea',value:9},{source:'B',target:'rash',value:3}]},'Subject');
  assert.equal(connectionCount(graph,'A','nausea'),4);
  assert.equal(connectionCount(graph,'B','nausea'),9);
  assert.equal(connectionCount(graph,'A','rash'),0);
  assert.equal(graph.reactions[0].a,4);
  assert.equal(graph.reactions[0].prr,2.4);
  assert.equal(graph.reactions[1].a,0);
  assert.equal(graph.reactions[1].prr,undefined);
});

test('object endpoints and reversed edges keep their source and real zero values',()=>{
  const graph=relationshipData({nodes:[{id:1,type:'drug'},{id:2,type:'reaction',a:0}],edges:[
    {source:{id:2},target:{id:1},value:0}, {source:'missing',target:2,value:99},
    {source:1,target:2,value:'not a count'}
  ]},'Subject');
  assert.deepEqual(graph.links,[{source:'1',target:'2',value:0}]);
});

test('signal rows remain usable without graph metadata and do not invent missing counts',()=>{
  const graph=relationshipData([{reaction:'Nausea',reports:5,prr:2},{reaction:'Unknown count',a:null}], 'Drug');
  assert.equal(connectionCount(graph,'subject','rx-0'),5);
  assert.equal(graph.reactions[1].a,null);
  assert.equal(graph.links.length,1);
  assert.equal(graph.reactions[0].prr,2);
  assert.deepEqual(relationshipData(null,'Drug').reactions,[]);
});
