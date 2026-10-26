import {cohortKey,sectionState} from './dashboardRequests.js';
import {normalizeReaction,snapshotKey} from './investigationState.js';

export const VIEW_NAMES={overview:'Overview',reactions:'Reactions',reports:'Case reports',signals:'Signal explorer',severity:'Severity',network:'Network graph',narratives:'Narrative lab',models:'Model studio',changes:'What changed?'};
const number=value=>typeof value==='number'&&Number.isFinite(value)?value:null;
const rows=value=>Array.isArray(value)?value:[];
const pick=(value,keys)=>Object.fromEntries(keys.map(key=>[key,value?.[key]??null]));
export const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,character=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const text=escapeHTML;
const fmt=value=>number(value)===null?'Unavailable':value.toLocaleString('en-US',{maximumFractionDigits:2});
const time=value=>value&&Number.isFinite(Date.parse(value))?new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'long'}):'Unavailable';

// Freeze only aggregate evidence from this cohort and its compatible calculation basis.
// Raw case text, uploaded narratives, model outputs, and credentials never enter the brief.
export function createResearchBrief({cohort,view,reaction,periods,requestState,active,pending,comparison,generatedAt=new Date().toISOString()}){
  const state=requestState?.key===cohortKey(cohort)?requestState:{sections:{}};
  const core=sectionState(state,'core'),signals=sectionState(state,'signals');
  const signalRows=rows(signals.result?.data.signals);
  const selected=normalizeReaction(reaction);
  const available=signalRows.filter(row=>!selected||normalizeReaction(row.reaction)===selected)
    .sort((a,b)=>(number(b.prr)??-1)-(number(a.prr)??-1));
  const status=(entry,label)=>({label,status:entry.status,available:Boolean(entry.result),
    retrieved_at:entry.result?.freshness?.retrieved_at||entry.result?.generated_at||'',
    retrieval:entry.result?.freshness?.source||'unknown',error:entry.error||'',warnings:rows(entry.result?.warnings).map(String)});
  return structuredClone({title:active?.name||`${cohort.drug} · research brief`,generatedAt,
    cohort:pick(cohort,['mode','drug','compare','start','end','age','sex','reporters']),view,selected,periods,
    saved:active?pick(active,['id','revision','name','notes','updated_at']):null,
    workspaceChanged:Boolean(active&&snapshotKey(active)!==snapshotKey({cohort,view,reaction,periods})),pending:Boolean(pending),
    source:cohort.mode==='live'?'openFDA / FAERS':'Synthetic local archive',
    total:number(core.result?.data.summary?.total_reports),
    signalCount:signals.result?signalRows.filter(row=>row.signal===true).length:null,
    signalCoverage:signals.result?signalRows.length:null,
    timeseries:rows(core.result?.data.timeseries).map(row=>({date:String(row.date),count:number(row.count)})),
    reactions:rows(core.result?.data.reactions).map(row=>({reaction:String(row.reaction),count:number(row.reports)??number(row.count)}))
      .sort((a,b)=>(b.count??-1)-(a.count??-1)).slice(0,6),
    signals:available.slice(0,8).map(row=>pick(row,['reaction','a','prr','prr_low','prr_high','ror','ror_low','ror_high','chi2','signal'])),
    sections:[status(core,'Cohort & reactions'),status(signals,'Signal estimates')],
    comparison:comparison?{periods:comparison.periods,meta:pick(comparison.meta,['generated_at','method']),
      retrieved_at:comparison.meta?.freshness?.retrieved_at||comparison.meta?.generated_at||'',
      rows:rows(comparison.rows).filter(row=>!selected||normalizeReaction(row.reaction)===selected)
        .sort((a,b)=>Math.abs(b.share_delta_pp??0)-Math.abs(a.share_delta_pp??0)).slice(0,8)
        .map(row=>pick(row,['reaction','baseline_count','current_count','share_delta_pp','ci_low_pp','ci_high_pp']))}:null});
}

export function revisionChanges(event,previous){
  if(event.kind==='legacy')return ['Earlier saves were not recorded; this is the earliest available snapshot.'];
  if(!previous)return [event.revision===1?'Investigation created.':'Earliest available saved context.'];
  const left=previous.snapshot,right=event.snapshot,changes=[];
  if(left.name!==right.name)changes.push('Name updated');
  if(cohortKey(left.cohort)!==cohortKey(right.cohort))changes.push('Cohort / filters updated');
  if(normalizeReaction(left.reaction)!==normalizeReaction(right.reaction))changes.push('Reaction focus updated');
  if(left.view!==right.view)changes.push('Research view updated');
  if(JSON.stringify(left.periods||{})!==JSON.stringify(right.periods||{}))changes.push('Comparison baseline updated');
  if(left.notes!==right.notes)changes.push('Research notes updated');
  return changes.length?changes:['Context saved again'];
}

const cell=value=>`<td>${text(value)}</td>`;
const table=(headers,values)=>`<div class="brief-table"><table><thead><tr>${headers.map(value=>`<th>${text(value)}</th>`).join('')}</tr></thead><tbody>${values.map(row=>`<tr>${row.map(cell).join('')}</tr>`).join('')}</tbody></table></div>`;
const interval=(low,high)=>number(low)===null||number(high)===null?'Unavailable':`${fmt(low)} – ${fmt(high)}`;
const contextHTML=cohort=>`<dl class="brief-context">${[
  ['Subject drug',cohort.drug],['Comparison drug',cohort.compare||'None'],['Receipt dates',`${cohort.start} → ${cohort.end}`],
  ['Age',cohort.age],['Sex',cohort.sex||'All'],['Reporters',cohort.reporters||'All']
].map(([label,value])=>`<div><dt>${text(label)}</dt><dd>${text(value)}</dd></div>`).join('')}</dl>`;

function volumeChart(data){
  const valid=data.filter(row=>number(row.count)!==null&&row.count>=0);
  if(!valid.length)return '<p>Weekly counts are unavailable.</p>';
  const max=Math.max(1,...valid.map(row=>row.count)),x=index=>58+index/Math.max(1,data.length-1)*650,y=value=>190-value/max*150;
  const lines=[0,.5,1].map(level=>`<line x1="58" x2="708" y1="${y(max*level)}" y2="${y(max*level)}" stroke="#dbe2d3"/><text x="49" y="${y(max*level)+4}" text-anchor="end">${text(fmt(max*level))}</text>`).join('');
  // Break at unknown weeks instead of drawing through missing data.
  let pen=false;
  const path=data.map((row,index)=>{if(number(row.count)===null||row.count<0){pen=false;return ''}const segment=`${pen?'L':'M'}${x(index)},${y(row.count)}`;pen=true;return segment}).join(' ');
  return `<div class="brief-figure"><svg viewBox="0 0 760 230" role="img" aria-label="Weekly subject-drug report counts"><title>Weekly volume, full applied cohort</title>${lines}<path d="${path}" fill="none" stroke="#477f79" stroke-width="2"/><text x="58" y="213">${text(data[0].date)}</text><text x="708" y="213" text-anchor="end">${text(data.at(-1).date)}</text></svg></div>`;
}
function reactionChart(data){
  const valid=data.filter(row=>number(row.count)!==null&&row.count>=0);
  if(!valid.length)return '<p>Reaction counts are unavailable.</p>';
  const max=Math.max(1,...valid.map(row=>row.count)),height=valid.length*39+25;
  return `<div class="brief-figure"><svg viewBox="0 0 760 ${height}" role="img" aria-label="Most mentioned reactions and counts"><title>Top reactions in the available reaction list</title>${valid.map((row,index)=>{
    const y=index*39+18,label=row.reaction.length>28?row.reaction.slice(0,27)+'…':row.reaction;
    return `<g><title>${text(row.reaction)}: ${text(fmt(row.count))}</title><text x="0" y="${y+4}">${text(label)}</text><rect x="255" y="${y-9}" width="${row.count/max*410}" height="18" fill="#76928b"/><text x="${268+row.count/max*410}" y="${y+4}">${text(fmt(row.count))}</text></g>`;
  }).join('')}</svg></div>`;
}

export function renderResearchBrief(brief,{events=[],historyStatus='none',historyTotal=events.length}={}){
  const unit=brief.cohort.mode==='live'?'reports':'reviews';
  const statusLabels={ready:'Loaded',partial:'Partially available',loading:'Refreshing',error:'Refresh failed',idle:'Not loaded'};
  const provenance=brief.sections.map(entry=>`<li><strong>${text(entry.label)}</strong> · ${text(statusLabels[entry.status]||entry.status)}${entry.available?' · values included':' · unavailable; no values included'}<br/>Oldest response / preparation time: ${text(time(entry.retrieved_at))} · ${text(({network:'FDA response',cache:'Cached FDA response',mixed:'FDA + cached responses',local:'Local synthetic archive'})[entry.retrieval]||'Retrieval details unavailable')}${entry.available&&['loading','error'].includes(entry.status)?'<p class="brief-alert">Values are from the last successful result, retained during this request.</p>':''}${entry.error?`<p>${text(entry.error)}</p>`:''}${entry.warnings.map(warning=>`<p>${text(warning)}</p>`).join('')}</li>`).join('');
  const history=events.slice(0,10);
  const notes=brief.saved?`<p class="brief-caption">Saved notes · revision ${text(brief.saved.revision)} · ${text(time(brief.saved.updated_at))}</p>${brief.workspaceChanged?'<p class="brief-alert">The current workspace differs from this saved revision. Read these notes in their saved context.</p>':''}<div class="brief-notes">${text(brief.saved.notes||'No research notes saved.')}</div>`:'<p>No saved investigation is open. Save an investigation to attach research notes and a revision trail.</p>';
  return `<article class="research-document"><header><span class="brief-kicker">VIGIL / RESEARCH BRIEF</span><h1>${text(brief.title)}</h1><p>${text(brief.source)} · prepared ${text(time(brief.generatedAt))}</p><p class="brief-caption">Current evidence snapshot · ${text(VIEW_NAMES[brief.view]||brief.view)} · ${text(brief.selected||'All reactions')}</p></header>
    ${brief.pending?'<p class="brief-alert">Unapplied filter or period edits are excluded. This brief uses the applied workspace.</p>':''}
    ${brief.cohort.mode==='reference'?'<p class="brief-alert">Synthetic demonstration data. These values are illustrative and do not describe FDA reports.</p>':''}
    <section><h2>01 / Research context</h2>${contextHTML(brief.cohort)}${brief.periods?.baseline_start?`<p>Workspace comparison baseline: ${text(brief.periods.baseline_start)} → ${text(brief.periods.baseline_end)}${brief.comparison?'':' · comparison results not loaded in this snapshot'}</p>`:''}<p>This brief includes aggregate cohort counts, the available signal list, and saved notes. Raw case text, uploaded narratives, and model outputs are outside this brief’s scope.</p></section>
    <section><h2>02 / Evidence at a glance</h2><div class="brief-metrics"><div><strong>${text(fmt(brief.total))}</strong><span>Subject-drug ${unit}</span></div><div><strong>${text(fmt(brief.signalCount))}</strong><span>${brief.signalCoverage===null?'Signal estimates unavailable':`Flags among ${text(fmt(brief.signalCoverage))} available signal estimates`}</span></div></div><p class="brief-caption">Flag rule: PRR ≥ 2, χ² ≥ 4, a ≥ 3. A flag prompts review; it is not a clinical conclusion.</p><h3>Weekly ${unit}</h3><p class="brief-caption">Bins are labeled by week start. The first and last weeks may be partial.</p><p class="brief-chart-hint">Scroll charts and tables sideways to read the full figure.</p>${volumeChart(brief.timeseries)}<h3>Most mentioned reactions</h3><p class="brief-caption">Top ${brief.reactions.length} in the available cohort reaction list. Records may mention more than one reaction.</p>${reactionChart(brief.reactions)}</section>
    <section><h2>03 / Signal evidence${brief.selected?' · selected reaction':''}</h2><p>${text(brief.selected||'Up to eight available reactions, ordered by PRR. This is a bounded list, not a complete scan of all FDA reactions.')}</p>${brief.signals.length?table(['Reaction','a','PRR (95% interval)','ROR (95% interval)','χ²','Screening'],brief.signals.map(row=>[row.reaction,fmt(row.a),`${fmt(row.prr)} (${interval(row.prr_low,row.prr_high)})`,`${fmt(row.ror)} (${interval(row.ror_low,row.ror_high)})`,fmt(row.chi2),row.signal===true?'Meets rule':row.signal===false?'Below rule':'Unavailable'])):'<p>No signal estimate is available for this selection. Missing evidence is not a zero or a negative result.</p>'}</section>
    ${brief.comparison?`<section><h2>04 / Period comparison</h2><p>Baseline ${text(brief.comparison.periods?.baseline?.start)} → ${text(brief.comparison.periods?.baseline?.end)} · current ${text(brief.comparison.periods?.current?.start)} → ${text(brief.comparison.periods?.current?.end)}</p><p>Up to eight reactions ${brief.selected?'matching the focus':'ordered by absolute reporting-share change'}. pp = percentage points.</p>${table(['Reaction','Baseline count','Current count','Change (pp)','95% interval (pp)'],brief.comparison.rows.map(row=>[row.reaction,fmt(row.baseline_count),fmt(row.current_count),fmt(row.share_delta_pp),interval(row.ci_low_pp,row.ci_high_pp)]))}<p>${text(brief.comparison.meta.method)}</p><p class="brief-caption">Oldest response: ${text(time(brief.comparison.retrieved_at))}</p></section>`:''}
    <section><h2>Research notes</h2>${notes}</section>
    <section><h2>Investigation timeline</h2><p>Saved research context and notes; historical charts and report contents were not stored.</p>${historyStatus==='loading'?'<p>Timeline is loading.</p>':historyStatus==='error'?'<p>Timeline could not be retrieved; this brief contains no revision history.</p>':history.length?`<p class="brief-caption">Most recent ${history.length} of ${historyTotal} available saves. Full recorded history remains in Vigil.</p><ol class="brief-history">${history.map((event,index)=>`<li><strong>Revision ${text(event.revision)} · ${text(time(event.saved_at))}</strong><p>${text(revisionChanges(event,events[index+1]).join(' · '))}</p><p>${text(event.snapshot.name)} · ${text(event.snapshot.cohort.drug)} · ${text(event.snapshot.cohort.start)} → ${text(event.snapshot.cohort.end)} · ${text(event.snapshot.reaction||'All reactions')}</p></li>`).join('')}</ol>`:'<p>No saved timeline is attached.</p>'}</section>
    <section><h2>Sources, retrieval & limitations</h2><ul class="brief-provenance">${provenance}</ul><p>Counts describe submitted records. Reporting bias, missing information, duplicates, and multiple products per record affect interpretation. These associations establish neither causation nor incidence. Comparisons do not show that a medicine became safer or less safe.</p>${brief.cohort.mode==='live'?'<p>Source and responsible-use guidance: <a href="https://open.fda.gov/apis/drug/event/" rel="noreferrer">FDA drug adverse event API documentation</a>.</p>':'<p>Source: the project’s local synthetic review archive. No FDA data is represented in this brief.</p>'}<p class="brief-caption">Prepared from the results available when the preview opened. This file does not refresh itself. No automated medical recommendation is generated.</p></section>
    <footer>vigil. / Evidence, with context. · ${text(brief.saved?`Investigation ${brief.saved.id} · saved revision ${brief.saved.revision}`:'Unsaved workspace')}</footer></article>`;
}

export function researchBriefHTML(brief,history){
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${text(brief.title)} · Vigil</title><style>${BRIEF_CSS}</style></head><body>${renderResearchBrief(brief,history)}</body></html>`;
}
export function briefFilename(brief){return `vigil-${String(brief.cohort.drug).toLowerCase().replace(/[^a-z0-9]+/g,'-').slice(0,60)||'research'}-${brief.generatedAt.slice(0,10)}.html`}

export const BRIEF_CSS=`
.research-document{box-sizing:border-box;max-width:920px;margin:0 auto;padding:42px;background:#fbfcf7;color:#303c2b;font:14px/1.7 Arial,sans-serif;overflow-wrap:anywhere;text-align:left}
.research-document *{box-sizing:border-box}.research-document header{border-bottom:1px solid #bfcbb5;padding-bottom:24px}.research-document .brief-kicker{font-size:10px;letter-spacing:2px;color:#667958}.research-document h1{font:40px/1.12 Georgia,serif;letter-spacing:-1px;margin:15px 0}.research-document h2{font:25px/1.25 Georgia,serif;margin:0 0 18px}.research-document h3{font:19px Georgia,serif;margin:26px 0 12px}.research-document section{padding:28px 0;border-bottom:1px solid #dce3d5}.research-document p{font-size:13px;margin:10px 0;color:#53644a}.research-document .brief-caption{font-size:11px;color:#637359}.research-document .brief-context{display:grid;grid-template-columns:1fr 1fr;gap:13px 24px;margin:0 0 18px}.research-document dt{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#78886c}.research-document dd{margin:3px 0;font-size:14px}.research-document .brief-metrics{display:flex;gap:40px}.research-document .brief-metrics strong{font:34px Georgia,serif;display:block}.research-document .brief-metrics span{font-size:11px;display:block;max-width:230px}.research-document svg{display:block;width:100%;height:auto;margin:14px 0;color:#53644a}.research-document svg text{font:12px Arial,sans-serif;fill:#53644a}.research-document .brief-table,.research-document .brief-figure{overflow-x:auto}.research-document .brief-chart-hint{display:none}.research-document table{width:100%;border-collapse:collapse;font-size:11px;margin:12px 0;min-width:600px}.research-document th,.research-document td{padding:10px 9px;border-bottom:1px solid #dce3d5;text-align:left;vertical-align:top;color:#37472e}.research-document th{background:#edf2e6;font-weight:500}.research-document .brief-notes{white-space:pre-wrap;font-size:13px}.research-document .brief-alert{padding:12px 15px;border-left:2px solid #b39164;background:#f4efdf;color:#715c3e}.research-document .brief-provenance{padding-left:18px;font-size:12px}.research-document .brief-provenance li{margin:12px 0}.research-document .brief-history{padding-left:22px;font-size:12px}.research-document .brief-history li{padding:7px 0}.research-document a{color:#47756a;text-decoration:underline}.research-document footer{padding-top:25px;font-size:10px;color:#6c7b60}
@media(max-width:600px){.research-document .brief-figure svg{min-width:600px}.research-document .brief-chart-hint{display:block;font-size:11px}.research-document{padding:22px 16px}.research-document h1{font-size:30px}.research-document .brief-context{grid-template-columns:1fr}.research-document .brief-metrics{gap:20px;flex-wrap:wrap}}
@media print{.research-document{max-width:none;margin:0;padding:0;color:#111;background:white;font-size:11pt}.research-document header,.research-document svg,.research-document tr{break-inside:avoid}.research-document h2,.research-document h3{break-after:avoid}.research-document .brief-table,.research-document .brief-figure{overflow:visible}.research-document .brief-figure svg{min-width:0}.research-document .brief-chart-hint{display:none}.research-document table{min-width:0;table-layout:fixed;font-size:8pt}.research-document th,.research-document td{padding:5px;overflow-wrap:anywhere}.research-document a{color:#222}.research-document section{padding:20px 0}.research-document .brief-context{grid-template-columns:1fr 1fr}}
`;
