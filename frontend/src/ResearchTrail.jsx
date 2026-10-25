import React,{useEffect,useState} from 'react';
import {Clock3,Download,RefreshCw,Save,LoaderCircle} from 'lucide-react';
import {BRIEF_CSS,VIEW_NAMES,briefFilename,createResearchBrief,renderResearchBrief,researchBriefHTML,revisionChanges} from './researchBrief.js';
import './research-trail.css';

const date=value=>value?new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'Unavailable';

export default function ResearchTrail({context,onSave}){
  const active=context.active;
  const [tab,setTab]=useState(active?'timeline':'brief'),[attempt,setAttempt]=useState(0);
  const [history,setHistory]=useState({events:[],status:active?'loading':'none',revision:null,error:''});
  const [brief,setBrief]=useState(()=>createResearchBrief(context)),[notice,setNotice]=useState(''),[exportError,setExportError]=useState('');
  useEffect(()=>{
    if(!active)return;
    const controller=new AbortController();let disposed=false;
    setHistory({events:[],status:'loading',revision:null,error:''});
    const timer=setTimeout(()=>controller.abort(),15000);
    fetch('/api/investigations/history?'+new URLSearchParams({id:active.id}),{signal:controller.signal})
      .then(async response=>{const result=await response.json();if(!response.ok)throw new Error(result.error||'The timeline could not be loaded.');
        if(result.id!==active.id||!Array.isArray(result.events))throw new Error('The timeline did not match this investigation.');
        if(!disposed)setHistory({events:result.events,status:'ready',revision:result.revision,error:''})})
      .catch(error=>{if(!disposed)setHistory({events:[],status:'error',revision:null,error:controller.signal.aborted?'The timeline request timed out. Retry to load saved history.':error.message})})
      .finally(()=>clearTimeout(timer));
    return()=>{disposed=true;clearTimeout(timer);controller.abort()};
  },[active?.id,active?.revision,attempt]);
  const exportHistory={events:history.events,historyStatus:history.status,historyTotal:history.events.length};
  function download(){
    setExportError('');let url;
    try{const blob=new Blob([researchBriefHTML(brief,exportHistory)],{type:'text/html;charset=utf-8'});url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=briefFilename(brief);anchor.click();setNotice('Brief downloaded. Open the HTML file in a browser; use Print to save a PDF.')}catch{setExportError('The brief could not be downloaded. Your investigation is still saved; try again.')}finally{if(url)setTimeout(()=>URL.revokeObjectURL(url),1000)}
  }
  return <div className="research-trail">
    <div className="trail-tabs" role="group" aria-label="Research trail view"><button className={tab==='timeline'?'selected':''} aria-pressed={tab==='timeline'} onClick={()=>setTab('timeline')}><Clock3 size={15}/> Timeline</button><button className={tab==='brief'?'selected':''} aria-pressed={tab==='brief'} onClick={()=>setTab('brief')}>Research brief</button></div>
    {notice&&<p className="investigation-notice" role="status">{notice}</p>}
    {history.status==='error'&&<div className="trail-error" role="alert"><p>{history.error}</p><button className="btn small ghost" onClick={()=>setAttempt(value=>value+1)}>Retry timeline</button></div>}
    {history.revision&&history.revision!==active?.revision&&<p className="pending-note">A newer revision was saved in another window. This timeline includes it; the open workspace and notes still use revision {active?.revision}. Reopen the investigation to use its latest context.</p>}
    {tab==='timeline'?<section aria-label="Saved investigation timeline">
      <div className="trail-intro"><span className="eyebrow">THE RESEARCH TRAIL</span><h3>{active?.name||'Every save tells a story.'}</h3><p>Follow changes to the cohort, reaction focus, and research notes. Each entry keeps its saved context; historical chart data is not stored.</p></div>
      {!active?<div className="trail-empty"><p>Save this workspace to start its timeline.</p><button className="btn small" onClick={onSave}><Save size={15}/> Save investigation</button></div>:history.status==='loading'?<p className="trail-loading" role="status"><LoaderCircle size={15} className="spin"/> Loading saved revisions…</p>:history.status==='ready'?<><p className="trail-count">{history.events.length} recorded save{history.events.length===1?'':'s'} · most recent first</p><ol className="investigation-timeline">{history.events.map((event,index)=>{const snapshot=event.snapshot;return <li key={event.revision}><span className="timeline-dot" aria-hidden="true"/><div className="timeline-date"><strong>Revision {event.revision}</strong><time dateTime={event.saved_at}>{date(event.saved_at)}</time></div><p className="timeline-changes">{revisionChanges(event,history.events[index+1]).join(' · ')}</p><p>{snapshot.cohort.drug} · {snapshot.reaction||'All reactions'} · {VIEW_NAMES[snapshot.view]||snapshot.view}</p><details><summary>View saved context & notes</summary><div className="timeline-snapshot"><strong>{snapshot.name}</strong><p>{snapshot.cohort.mode==='live'?'FDA / FAERS':'Synthetic archive'} · {snapshot.cohort.start} → {snapshot.cohort.end}</p><p>Comparison drug: {snapshot.cohort.compare||'None'} · Age: {snapshot.cohort.age} · Sex: {snapshot.cohort.sex||'All'} · Reporters: {snapshot.cohort.reporters||'All'}</p>{snapshot.periods?.baseline_start&&<p>Baseline: {snapshot.periods.baseline_start} → {snapshot.periods.baseline_end}</p>}<p>Retrieval time recorded at save: {date(snapshot.retrieved_at)}</p><div className="timeline-notes">{snapshot.notes||'No research notes saved.'}</div></div></details></li>})}</ol><button className="btn small ghost" onClick={()=>setAttempt(value=>value+1)}><RefreshCw size={13}/> Refresh timeline</button></>:null}
    </section>:<section aria-label="Research brief preview"><div className="brief-toolbar"><div><span className="eyebrow">A PORTABLE EVIDENCE SNAPSHOT</span><p>Prepared {date(brief.generatedAt)}. Preview and download use the same frozen evidence. Saved notes are included; unapplied edits are excluded.</p></div><div><button className="btn small ghost" onClick={()=>{setBrief(createResearchBrief(context));setNotice('Preview refreshed from the currently loaded evidence.')}}><RefreshCw size={14}/> Refresh preview</button><button className="btn small primary" disabled={history.status==='loading'} onClick={download}><Download size={14}/> Download brief</button></div></div><p className="field-hint">Self-contained HTML with charts. Open the downloaded file in a browser, then Print → Save as PDF. No sign-in or network connection is needed to read it.</p>{exportError&&<p className="inline-error" role="alert">{exportError}</p>}<style>{BRIEF_CSS}</style><div className="research-preview" dangerouslySetInnerHTML={{__html:renderResearchBrief(brief,exportHistory)}}/></section>}
  </div>;
}
