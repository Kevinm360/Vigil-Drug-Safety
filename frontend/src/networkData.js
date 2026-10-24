const count=value=>value!=null&&Number.isFinite(Number(value))?Math.max(0,Number(value)):null;
const endpoint=value=>String(typeof value==='object'?value.id:value);

export function relationshipData(data,drug){
  if(!Array.isArray(data?.nodes)){
    const rows=Array.isArray(data)?data:data?.rows||[];
    const sources=[{id:'subject',label:drug,type:'drug'}];
    const reactions=rows.map((row,i)=>({...row,id:`rx-${i}`,label:String(row.reaction??row.label??row.name??'Unknown'),a:count(row.a??row.count??row.reports)}));
    return {sources,reactions,links:reactions.filter(r=>r.a!=null).map(r=>({source:'subject',target:r.id,value:r.a}))};
  }
  const sources=data.nodes.filter(n=>n.type==='drug'||n.group==='drug').map(n=>({...n,id:String(n.id),label:String(n.label??n.name??n.id)}));
  const reactions=data.nodes.filter(n=>!sources.some(s=>s.id===String(n.id))).map(n=>({...n,id:String(n.id),label:String(n.label??n.name??n.id),a:count(n.a??n.count??n.value)}));
  const sourceIds=new Set(sources.map(s=>s.id)), reactionIds=new Set(reactions.map(r=>r.id));
  const links=(data.links??data.edges??[]).map(e=>({source:endpoint(e.source),target:endpoint(e.target),value:count(e.value??e.count)})).map(e=>reactionIds.has(e.source)&&sourceIds.has(e.target)?{...e,source:e.target,target:e.source}:e).filter(e=>sourceIds.has(e.source)&&reactionIds.has(e.target)&&e.value!=null);
  return {sources,reactions,links};
}

export function connectionCount(graph,source,target){
  const matching=graph.links.filter(e=>e.source===source&&e.target===target);
  return matching.reduce((sum,e)=>sum+e.value,0);
}
