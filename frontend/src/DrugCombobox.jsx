import React,{useEffect,useId,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {Search,ChevronDown,Check,X,LoaderCircle} from 'lucide-react';

const nameCache=new Map();
const format=value=>String(value).toLowerCase().replace(/\b\w/g,c=>c.toUpperCase());
const matching=(name,query)=>query.trim().toLowerCase().split(/\s+/).every(token=>name.toLowerCase().includes(token));

export default function DrugCombobox({label='Subject drug',value,onChange,onApply,mode='live',localOptions=[],placeholder='Search brand or generic name…',optional=false}){
  const id=useId().replaceAll(':','');
  const host=useRef(null),input=useRef(null),options=useRef(null);
  const [open,setOpen]=useState(false),[browse,setBrowse]=useState(true),[active,setActive]=useState(-1),[shown,setShown]=useState(20);
  const [result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [above,setAbove]=useState(false),[listHeight,setListHeight]=useState(270);
  const query=browse?'':value.trim();
  const archive=useMemo(()=>[...new Set(localOptions.map(row=>typeof row==='string'?row:row.name))].filter(Boolean).map(name=>({name,kind:'Archive'})),[localOptions]);
  const names=mode==='reference'?archive.filter(row=>matching(row.name,query)):result?.query===query?result.drugs:[];
  const visible=names.slice(0,shown);
  useLayoutEffect(()=>{
    if(!open)return;
    const place=()=>{
      const bounds=host.current.getBoundingClientRect(),viewport=window.visualViewport;
      const top=viewport?.offsetTop||0,bottom=top+(viewport?.height||window.innerHeight);
      const below=bottom-bounds.bottom,up=below<330&&bounds.top-top>below;
      setAbove(up);setListHeight(Math.max(90,Math.min(270,(up?bounds.top-top:below)-145)));
    };
    place();window.addEventListener('resize',place);window.visualViewport?.addEventListener('resize',place);
    return()=>{window.removeEventListener('resize',place);window.visualViewport?.removeEventListener('resize',place);};
  },[open]);
  useEffect(()=>{
    if(!open)return;
    const close=event=>{if(!host.current?.contains(event.target))setOpen(false);};
    document.addEventListener('pointerdown',close);
    return()=>document.removeEventListener('pointerdown',close);
  },[open]);
  useEffect(()=>{
    setActive(-1);setShown(20);setError('');
    if(!open||mode==='reference'){setBusy(false);return;}
    const cached=nameCache.get(query.toLowerCase());
    if(cached&&Date.now()-cached.time<900000){setResult({...cached.data,query});setBusy(false);return;}
    setBusy(true);
    const controller=new AbortController();
    const timer=setTimeout(async()=>{
      try{
        const response=await fetch('/api/drugs?'+new URLSearchParams({q:query}),{signal:controller.signal});
        const data=await response.json();
        if(!response.ok)throw new Error(data.error||'FDA suggestions could not be loaded.');
        if(!controller.signal.aborted){if(nameCache.size>=30)nameCache.delete(nameCache.keys().next().value);nameCache.set(query.toLowerCase(),{time:Date.now(),data});setResult({...data,query});}
      }catch(e){if(!controller.signal.aborted)setError(e.message);}
      finally{if(!controller.signal.aborted)setBusy(false);}
    },query?240:0);
    return()=>{clearTimeout(timer);controller.abort();};
  },[open,query,mode]);
  useEffect(()=>{if(active>=0)options.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({block:'nearest'});},[active]);
  const choose=name=>{onChange(name);setOpen(false);setActive(-1);input.current?.focus();};
  const begin=()=>{setBrowse(true);setOpen(true);};
  const key=event=>{
    if(event.nativeEvent.isComposing)return;
    if(event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();setOpen(false);return;}
    if(['ArrowDown','ArrowUp'].includes(event.key)){
      event.preventDefault();
      if(!open){begin();return;}
      setActive(i=>visible.length?(i<0?(event.key==='ArrowDown'?0:visible.length-1):(i+(event.key==='ArrowDown'?1:-1)+visible.length)%visible.length):-1);
    }
    if(event.key==='Enter'){
      event.preventDefault();
      if(open&&busy)return;
      if(open&&visible.length&&(active>=0||(!browse&&query)))choose(visible[Math.max(0,active)].name);
      else{setOpen(false);onApply?.();}
    }
  };
  return <div ref={host} className={`drug-combobox ${open?'is-open':''} ${above?'opens-up':''}`} style={{'--drug-list-height':`${listHeight}px`}} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setOpen(false);}}>
    <div className="drug-combobox-control"><Search size={16}/><input ref={input} aria-label={label} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-names`} aria-activedescendant={open&&active>=0?`${id}-name-${active}`:undefined} value={value} placeholder={placeholder} autoComplete="off" spellCheck={false} maxLength={120} onFocus={event=>{begin();event.currentTarget.select();}} onChange={event=>{onChange(event.target.value);setBrowse(false);setOpen(true);setActive(-1);}} onKeyDown={key}/>{optional&&value&&<button type="button" className="drug-clear" aria-label={`Clear ${label.toLowerCase()}`} onMouseDown={event=>event.preventDefault()} onClick={()=>{onChange('');setBrowse(true);setOpen(true);input.current?.focus();}}><X size={13}/></button>}<button type="button" className="drug-dropdown-toggle" aria-label={`Browse ${label.toLowerCase()} names`} aria-expanded={open} onMouseDown={event=>event.preventDefault()} onClick={()=>{if(open)setOpen(false);else{begin();input.current?.focus();}}}><ChevronDown size={15}/></button></div>
    {open&&<div className="drug-suggestions">
      <div className="drug-suggestions-heading"><span>{mode==='reference'?'LOCAL ARCHIVE':query?'FDA NAME MATCHES':'BROWSE FDA DRUG NAMES'}</span><small>{busy?<LoaderCircle className="spin" size={12}/>:names.length?`${names.length.toLocaleString()} names`:''}</small></div>
      <div className="drug-suggestions-scroll" ref={options} id={`${id}-names`} role="listbox" aria-label={`${label} suggestions`} aria-busy={busy}>
        {busy?<div className="drug-suggestions-status" role="status">Searching FDA names…</div>:error?<div className="drug-suggestions-status is-error" role="status">{error}</div>:visible.length?visible.map((row,index)=><button type="button" role="option" tabIndex={-1} id={`${id}-name-${index}`} data-index={index} key={row.name} aria-selected={active===index} className={`drug-suggestion ${active===index?'is-active':''}`} onMouseDown={event=>event.preventDefault()} onPointerMove={()=>setActive(index)} onClick={()=>choose(row.name)}><span><strong>{format(row.name)}</strong><small>{row.kind}</small></span>{row.name.toUpperCase()===value.toUpperCase()&&<Check size={14}/>}</button>):<div className="drug-suggestions-status" role="status">No listed names match. You can still use the name you entered.</div>}
      </div>
      {!busy&&!error&&shown<names.length&&<button type="button" className="drug-show-more" onClick={()=>setShown(n=>n+40)}>Show more names <span>{names.length-shown} more</span></button>}
      <div className="drug-suggestions-footer"><span>{mode==='reference'?'Names available in the synthetic archive':result?.partial?'Some FDA names are unavailable · manual entry still works':'Brand + generic names · type to narrow the directory'}</span><small>↑ ↓ to browse · Enter to select</small></div>
    </div>}
  </div>;
}
