import {normalizeReaction} from './investigationState.js';

const numeric=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0?value:null;
export const reactionReportKey=(cohort,reaction)=>JSON.stringify([cohort,normalizeReaction(reaction)]);

// Missing aggregates and missing statistics stay unknown, including graph-only terms.
export function reactionEvidence(data,reaction,reports){
  const term=normalizeReaction(reaction),rows=data?.reactions||[];
  const row=rows.find(item=>normalizeReaction(item.reaction)===term);
  const signal=(data?.signals||[]).find(item=>normalizeReaction(item.reaction)===term)||null;
  const count=numeric(reports?.total)??numeric(row?.reports)??numeric(row?.count)??numeric(signal?.a);
  const total=numeric(data?.summary?.total_reports);
  const share=count!==null&&total>0&&count<=total?count/total*100:null;
  return {count,total,share,signal,comparisonCount:numeric(row?.compare_reports)};
}

export function currentReactionReports(state,key){
  return state?.key===key&&!state.loading&&!state.error?state:null;
}

export async function fetchReactionReports(cohort,reaction,{signal,fetcher=fetch}={}){
  const response=await fetcher('/api/reaction-reports?'+new URLSearchParams({...cohort,reaction:normalizeReaction(reaction)}),{signal});
  const result=await response.json();
  if(!response.ok)throw new Error(result.error?.message||result.error||'Matching records could not be loaded.');
  if(!Array.isArray(result.records)||numeric(result.total)===null)throw new Error('The matching-record response was incomplete. Please retry.');
  if(normalizeReaction(result.reaction)!==normalizeReaction(reaction))throw new Error('The response did not match the selected reaction. Please retry.');
  return result;
}
