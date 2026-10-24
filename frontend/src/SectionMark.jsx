import React,{useId} from 'react';
import {ChartNoAxesCombined,FileText,ScanLine,HeartPulse,Network,BrainCircuit,FlaskConical,Pause,Play} from 'lucide-react';
import useAmbientMotion from './useAmbientMotion.js';

const SECTIONS={reactions:['02','Reported reactions',ChartNoAxesCombined,'#668e82'],reports:['03','Source records',FileText,'#8a95ac'],signals:['04','Statistical screening',ScanLine,'#9c8cb2'],severity:['05','Recorded outcomes',HeartPulse,'#b18b79'],network:['06','Connected evidence',Network,'#719798'],narratives:['07','Language & context',BrainCircuit,'#9c92af'],models:['08','Held-out evaluation',FlaskConical,'#8b9c77']};

export default function SectionMark({view}){
  const id=useId().replaceAll(':',''),section=SECTIONS[view];
  const {host,paused,stopped,toggle}=useAmbientMotion();
  if(!section)return null;
  const [number,label,Icon,ink]=section;
  const waves=(cx,cy,width,height,phase)=>Array.from({length:17},(_,i)=>{
    const dx=(i-8)*10,curve=Math.pow(Math.max(0,1-(dx/(width/2))**2),1.8);
    return <line key={i} x1={cx+dx} x2={cx+dx} y1={cy-height*curve/2} y2={cy+height*curve/2} stroke={ink} strokeWidth="1.7" style={{animationDelay:`${phase+i*.14}s`}}/>;
  });
  return <div ref={host} className={`section-mark section-atmosphere ${stopped?'section-motion-paused':''}`} data-section={view} style={{'--section-ink':ink}}>
    <svg className="section-accent-lines" viewBox="0 0 1200 185" preserveAspectRatio="xMaxYMid slice" aria-hidden="true"><g className="section-wave">{waves(820,20,180,72,-2)}{waves(1130,140,140,90,-5)}{waves(625,170,120,48,-4)}</g></svg>
    <svg className="section-icon" viewBox="0 0 270 155" aria-hidden="true"><defs>
      <pattern id={`${id}-screen`} width="3.5" height="155" patternUnits="userSpaceOnUse"><rect className="section-screen-line" width="1.5" height="155" fill="white"/></pattern>
      <mask id={`${id}-mask`}><rect width="270" height="155" fill={`url(#${id}-screen)`}/></mask>
    </defs><g mask={`url(#${id}-mask)`} color={ink}><g className="section-glyph"><Icon x="18" y="7" width="130" height="130" strokeWidth="1.35"/></g></g><text x="166" y="91" className="section-number">{number}</text><text x="21" y="149" className="section-caption">{label.toUpperCase()}</text></svg>
    <div className="section-panel-tint" aria-hidden="true"/>
    <div className="section-bottom-wash" aria-hidden="true"/>
    <button className="section-motion-control" onClick={toggle} aria-label={paused?'Play tab animation':'Pause tab animation'}>{paused?<Play size={11}/>:<Pause size={11}/>}<span>{paused?'Play':'Pause'} motion</span></button>
  </div>;
}
