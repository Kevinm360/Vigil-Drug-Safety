import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cubeProjection,cubeAxes} from '../frontend/src/signalProjection.js';

test('cube corners and signal points remain inside the plot through a full rotation on mobile and desktop',()=>{
  for(const width of [320,390,920,1440])for(let step=0;step<=48;step++){
    const angle=step*Math.PI/24,height=width<500?360:440,{project,corners}=cubeProjection(angle,width,height);
    for(const [x,y] of [...corners,project(.2,.8,.5),project(.5,.5,.5)]){
      assert.ok(Number.isFinite(x)&&Number.isFinite(y));
      assert.ok(x>=55&&x<=width-55,`x outside label margin at ${width}px`);
      assert.ok(y>=53&&y<=height-53,`y outside label margin at ${width}px`);
    }
  }
});

test('axis lines use the same transform and direction as the data, with outward tick normals',()=>{
  for(const angle of [-.58,0,Math.PI/2,Math.PI,Math.PI*1.5]){
    const {project}=cubeProjection(angle,700,440),axes=cubeAxes(project,700,440);
    assert.deepEqual(axes.map(axis=>axis.letter),['X','Y','Z']);
    for(const axis of axes){
      assert.deepEqual(axis.origin,project(...axis.base));assert.deepEqual(axis.end,project(...axis.base.map((value,index)=>value+axis.unit[index])));
      assert.ok(Math.abs(Math.hypot(...axis.normal)-1)<1e-10);
      const outward=axis.normal[0]*((axis.origin[0]+axis.end[0])/2-350)+axis.normal[1]*((axis.origin[1]+axis.end[1])/2-220);
      assert.ok(outward>=-1e-10);
    }
  }
});

test('reset angle restores the exact coordinates and rotation moves the plot around its center',()=>{
  const point=[.7,.4,.8],initial=cubeProjection(-.58,920,440).project(...point);
  assert.deepEqual(initial,cubeProjection(-.58,920,440).project(...point));
  assert.notDeepEqual(initial,cubeProjection(-.58+Math.PI/6,920,440).project(...point));
  assert.deepEqual(cubeProjection(2,920,440).project(.5,.5,.5),[460,220]);
});
