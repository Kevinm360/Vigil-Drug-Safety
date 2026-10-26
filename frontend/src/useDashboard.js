import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {DashboardRequests,assembleDashboard,cohortKey} from './dashboardRequests.js';

export default function useDashboard(cohort,refresh){
  const [state,setState]=useState({key:'',sections:{}}),loader=useRef(null);
  if(!loader.current)loader.current=new DashboardRequests(setState);
  useEffect(()=>{loader.current.start(cohort);return()=>loader.current.cancel()},[cohort,refresh]);
  const current=state.key===cohortKey(cohort)?state:{key:cohortKey(cohort),sections:{}};
  const results=['core','signals','severity','reports','comparison'].map(name=>current.sections[name]?.result);
  const data=useMemo(()=>assembleDashboard(current),[current.key,...results]);
  const core=current.sections.core;
  const retry=useCallback(name=>loader.current.retry(name),[]);
  return {data,loading:!data&&core?.status!=='error',error:!data&&core?.error||'',requestState:current,retry,busy:Object.values(current.sections).some(entry=>entry.status==='loading')};
}
