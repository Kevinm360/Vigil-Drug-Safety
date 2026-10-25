// One projection for the cube, axes, ticks, and signal points.
function rawPoint([x,y,z],angle){
  const ax=(x-.5)*400,ay=(y-.5)*260,az=(z-.5)*260;
  return [Math.cos(angle)*ax+Math.sin(angle)*az,-ay*.78+(Math.sin(angle)*ax-Math.cos(angle)*az)*.38];
}

export function cubeProjection(angle,width,height){
  const rawCorners=Array.from({length:8},(_,index)=>rawPoint([index&1?1:0,index&2?1:0,index&4?1:0],angle));
  const spanX=Math.max(...rawCorners.map(point=>Math.abs(point[0])))*2;
  const spanY=Math.max(...rawCorners.map(point=>Math.abs(point[1])))*2;
  const scale=Math.min((width-112)/spanX,(height-108)/spanY);
  const project=(x,y,z)=>{const point=rawPoint([x,y,z],angle);return [width/2+point[0]*scale,height/2+point[1]*scale]};
  return {project,corners:Array.from({length:8},(_,index)=>project(index&1?1:0,index&2?1:0,index&4?1:0))};
}

export function cubeAxes(project,width,height){
  const floor=[[0,0,0],[1,0,0],[0,0,1],[1,0,1]];
  const front=floor.reduce((best,point)=>project(...point)[1]>project(...best)[1]?point:best);
  const left=floor.reduce((best,point)=>project(...point)[0]<project(...best)[0]?point:best);
  return [['X',[1,0,0],'#487b72'],['Y',[0,1,0],'#866b98'],['Z',[0,0,1],'#a36e48']].map(([letter,unit,color])=>{
    const base=letter==='X'?[0,0,front[2]]:letter==='Y'?left:[front[0],0,0];
    const point=level=>project(...base.map((value,index)=>value+unit[index]*level));
    const origin=point(0),end=point(1),dx=end[0]-origin[0],dy=end[1]-origin[1],length=Math.hypot(dx,dy)||1;
    let normal=[-dy/length,dx/length];
    if(normal[0]*((origin[0]+end[0])/2-width/2)+normal[1]*((origin[1]+end[1])/2-height/2)<0)normal=normal.map(value=>-value);
    return {letter,unit,base,point,color,origin,end,normal,anchor:normal[0]<-.25?'end':normal[0]>.25?'start':'middle'};
  });
}
