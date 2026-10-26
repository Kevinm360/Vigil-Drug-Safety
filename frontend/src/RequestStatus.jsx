import React,{createContext,useContext} from 'react';
import {Clock3,RefreshCw,LoaderCircle,AlertCircle} from 'lucide-react';
import {SECTION_NAMES,sectionState} from './dashboardRequests.js';
import './request-status.css';

export const RequestContext=createContext(null);
const date=value=>value?new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'Time unavailable';
export function freshnessLabel(freshness){return {network:'Retrieved from FDA',cache:'From FDA cache',mixed:'FDA + cached responses',local:'Local synthetic archive',unknown:'Retrieval details unavailable'}[freshness?.source]||'Retrieval details unavailable'}

export function SectionStatus({name,compact=false}){
  const context=useContext(RequestContext);if(!context)return null;
  const entry=sectionState(context.state,name),freshness=entry.result?.freshness;
  const loading=entry.status==='loading'||entry.status==='idle',failed=entry.status==='error'||entry.status==='partial';
  return <div className={`section-request-status ${failed?'has-error':''} ${compact?'is-compact':''}`} aria-busy={loading}>
    <div role={failed?'status':undefined}>{loading?<LoaderCircle size={13} className="spin"/>:failed?<AlertCircle size={13}/>:<Clock3 size={13}/>}<span>{loading?(entry.result?'Refreshing · showing the last successful result':'Loading '+SECTION_NAMES[name]+'…'):entry.status==='partial'?'Some data unavailable':failed?(entry.result?'Last successful result retained':'Section unavailable'):freshnessLabel(freshness)}{entry.result&&!loading&&<small>{freshness?.source==='local'?'Prepared':'Oldest response'}: {date(freshness?.retrieved_at||entry.result.generated_at)}</small>}</span></div>
    {entry.error&&<p>{entry.error}</p>}
    {entry.result&&entry.status==='error'&&<p>The displayed result has not been updated by this attempt.</p>}
    <button className="section-retry" disabled={loading} aria-label={`${failed?'Retry':'Refresh'} ${SECTION_NAMES[name]}`} onClick={()=>context.retry(entry.needsRefresh?'core':name)}><RefreshCw size={12}/>{entry.needsRefresh?'Refresh cohort':failed?'Retry section':'Refresh'}</button>
  </div>;
}

export function DataStatus(){
  const context=useContext(RequestContext);if(!context)return null;
  const entries=Object.entries(context.state.sections),pending=entries.filter(([,value])=>value.status==='loading').length,failed=entries.filter(([,value])=>['error','partial'].includes(value.status)).length;
  const core=sectionState(context.state,'core').result;
  return <details className="data-request-status"><summary><Clock3 size={13}/><span>{pending?`${pending} data section${pending===1?'':'s'} loading`:failed?`${failed} section${failed===1?' needs':'s need'} attention`:freshnessLabel(core?.freshness)}</span>{core&&<small>Oldest core response: {date(core.freshness?.retrieved_at||core.generated_at)}</small>}</summary><div className="data-status-list">{entries.map(([name])=><section key={name}><h3>{SECTION_NAMES[name]}</h3><SectionStatus name={name}/>{sectionState(context.state,name).result?.freshness?.expires_at&&<p>Cached responses expire by {date(sectionState(context.state,name).result.freshness.expires_at)}. Expired entries are fetched again; refreshing can reuse unexpired responses.</p>}</section>)}</div></details>;
}
