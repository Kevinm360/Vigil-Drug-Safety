const DAY=86400000;
const iso=time=>new Date(time).toISOString().slice(0,10);
export function previousPeriod(cohort){
  const start=Date.parse(cohort.start+'T00:00:00Z'),end=Date.parse(cohort.end+'T00:00:00Z');
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<start)return {};
  const baseline_start=iso(start-(end-start+DAY));
  return baseline_start<'1900-01-01'?{}:{baseline_start,baseline_end:iso(start-DAY)};
}
export function periodPreset(end,days){
  const endTime=Date.parse(end+'T00:00:00Z');
  const current={start:iso(endTime-(days-1)*DAY),end};
  return {...current,...previousPeriod(current)};
}
export function changesKey(cohort,periods){
  return JSON.stringify([['mode','drug','start','end','age','sex','reporters'].map(key=>cohort[key]),periods.baseline_start,periods.baseline_end]);
}
export function filterChanges(rows,{search='',direction='all',minimum=0,sort='change'}={}){
  const result=(rows||[]).filter(row=>row.reaction.toLowerCase().includes(search.toLowerCase())&&
    (direction==='all'||direction==='current_only'?direction==='all'||row.current_only:direction==='sparse'?row.sparse:row.direction===direction)&&
    (row.current_count==null||row.baseline_count==null||row.current_count+row.baseline_count>=minimum));
  return result.sort((a,b)=>sort==='name'?a.reaction.localeCompare(b.reaction):sort==='count'?(b.current_count??-1)-(a.current_count??-1):
    (a.share_delta_pp==null)-(b.share_delta_pp==null)||Math.abs(b.share_delta_pp||0)-Math.abs(a.share_delta_pp||0));
}
