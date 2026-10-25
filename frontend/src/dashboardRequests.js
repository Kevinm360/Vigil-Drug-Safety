export const SECTION_NAMES={core:'Cohort & reactions',signals:'Signal estimates',severity:'Severity & demographics',reports:'Case report sample',comparison:'Drug comparison'};
export const cohortKey=cohort=>JSON.stringify(['mode','drug','compare','start','end','age','sex','reporters'].map(key=>Array.isArray(cohort[key])?cohort[key].join(','):cohort[key]));

export function sectionState(state,name){
  const entry=state.sections?.[name]||{status:'idle',result:null,error:''};
  const basis=state.sections?.core?.result?.basis;
  return name!=='core'&&entry.result&&entry.result.basis!==basis?{...entry,result:null}:entry;
}

export function assembleDashboard(state){
  const core=sectionState(state,'core').result;
  if(!core)return null;
  const data=structuredClone(core.data),signals=sectionState(state,'signals').result,comparison=sectionState(state,'comparison').result;
  for(const name of ['signals','severity','reports']){
    const result=sectionState(state,name).result;
    if(!result)continue;
    const {summary,...patch}=result.data;
    Object.assign(data,patch);Object.assign(data.summary,summary);
  }
  if(comparison){
    const patch=comparison.data,byReaction=new Map(patch.comparison_reactions.map(row=>[row.reaction.toUpperCase(),row]));
    data.reactions=data.reactions.map(row=>({...row,compare_reports:byReaction.get(row.reaction.toUpperCase())?.compare_reports??null}));
    if(data.summary.total_reports===0)data.reactions=patch.comparison_reactions;
    const weeks=new Map(patch.comparison_timeseries.map(row=>[row.date,row.compare_count]));
    data.timeseries=data.timeseries.map(row=>({...row,compare_count:weeks.get(row.date)??null}));
    data.summary.compare_total=patch.summary.compare_total;data.meta.comparison=patch.comparison;
    data.graph=patch.comparison_graph;
  }
  // Comparison graphs carry source-specific counts; add only subject signal statistics.
  if(signals){
    const stats=new Map(signals.data.signals.map(row=>[row.reaction.toUpperCase(),row]));
    data.graph.nodes=data.graph.nodes.map(node=>{const row=stats.get(String(node.label).toUpperCase());if(node.type!=='reaction'||!row)return node;const keys=['prr','prr_low','prr_high','ror','ror_low','ror_high','chi2','signal'];return {...node,...Object.fromEntries(keys.filter(key=>key in row).map(key=>[key,row[key]]))}});
  }
  data.meta.warnings=[...new Set(Object.values(state.sections).flatMap(entry=>entry.result?.warnings||[]))];
  return data;
}

export class DashboardRequests{
  constructor(onChange,fetcher=(...args)=>fetch(...args)){this.onChange=onChange;this.fetcher=fetcher;this.generation=0;this.sequence={};this.controllers=new Map();this.state={key:'',sections:{}}}
  emit(){this.state={...this.state,sections:{...this.state.sections}};this.onChange(this.state)}
  cancel(){this.generation++;for(const controller of this.controllers.values())controller.abort();this.controllers.clear()}
  async start(cohort){
    this.cancel();this.cohort={...cohort};const key=cohortKey(cohort),generation=this.generation;
    if(this.state.key!==key)this.state={key,sections:{}};
    const core=await this.load('core',generation);
    if(!core||generation!==this.generation)return;
    await Promise.all(['signals','severity','reports',...(cohort.compare?['comparison']:[])].map(name=>this.load(name,generation)));
  }
  retry(name){return name==='core'?this.start(this.cohort):this.load(name,this.generation)}
  async load(name,generation){
    const sequence=(this.sequence[name]||0)+1;this.sequence[name]=sequence;
    this.controllers.get(name)?.abort();const controller=new AbortController();this.controllers.set(name,controller);
    const previous=this.state.sections[name];this.state.sections[name]={...previous,status:'loading',error:'',needsRefresh:false};this.emit();
    const current=()=>generation===this.generation&&sequence===this.sequence[name];
    const timeout=setTimeout(()=>controller.abort(),120000);
    try{
      const response=await this.fetcher('/api/dashboard/section?'+new URLSearchParams({...this.cohort,section:name}),{signal:controller.signal});
      const result=await response.json();if(!current())return false;
      if(!response.ok)throw new Error(result.error?.message||result.error||'This section could not be loaded.');
      if(result.section!==name||!result.data||cohortKey(result.cohort)!==this.state.key)throw new Error('The response did not match the current cohort. Retry this section.');
      if(name!=='core'&&result.basis!==this.state.sections.core?.result?.basis){const error=new Error('The cohort counts changed while this section loaded. Refresh the cohort to keep its calculations consistent.');error.needsRefresh=true;throw error}
      if(result.status==='error')throw new Error(result.errors?.join(' ')||'This section is unavailable.');
      this.state.sections[name]={status:result.status==='partial'?'partial':'ready',result,error:result.errors?.join(' ')||'',needsRefresh:false};this.emit();return true;
    }catch(error){
      if(!current())return false;
      const message=error instanceof TypeError&&/fetch|network/i.test(error.message)?'Could not reach the local API. Check that Vigil is running, then retry this section.':error.message;
      this.state.sections[name]={...previous,status:'error',error:controller.signal.aborted?'This section timed out. Retry or choose a shorter date range.':message,needsRefresh:Boolean(error.needsRefresh)};this.emit();return false;
    }finally{clearTimeout(timeout);if(this.controllers.get(name)===controller)this.controllers.delete(name)}
  }
}
