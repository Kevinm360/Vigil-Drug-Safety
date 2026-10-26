import React,{useEffect,useRef} from 'react';
import {LayoutDashboard,ChartNoAxesCombined,FileText,FlaskConical} from 'lucide-react';
import {NAV_GROUPS,VIEW_NAV_LABELS,groupForView,groupDestination} from './navigation.js';
import './workspace-navigation.css';

const ICONS={overview:LayoutDashboard,explore:ChartNoAxesCombined,reports:FileText,lab:FlaskConical};

export default function WorkspaceNavigation({view,views,onNavigate}){
  const active=groupForView(view),lastViews=useRef({});
  useEffect(()=>{lastViews.current[active.id]=view},[view,active.id]);
  const secondary=active.views.length>1;
  return <div className={`workspace-navigation ${secondary?'has-section-views':''}`}>
    <nav className="primary-navigation" aria-label="Main sections">
      {NAV_GROUPS.map(group=>{const Icon=ICONS[group.id],selected=group.id===active.id;return <button key={group.id} className={`nav-item ${selected?'active':''}`} aria-current={selected?'true':undefined} onClick={()=>onNavigate(groupDestination(group.id,lastViews.current))}><span className="nav-icon-socket"><Icon size={16}/></span><span>{group.label}</span></button>})}
    </nav>
    {secondary&&<nav className="secondary-navigation" aria-label={`${active.label} views`}>
      {active.views.map(id=>{const entry=views.find(item=>item[0]===id);if(!entry)return null;const Icon=entry[2],selected=id===view;return <button key={id} className={`section-view-link ${selected?'is-current':''}`} aria-current={selected?'page':undefined} onClick={()=>onNavigate(id)}><Icon size={14}/><span>{VIEW_NAV_LABELS[id]||entry[1]}</span></button>})}
    </nav>}
  </div>;
}
