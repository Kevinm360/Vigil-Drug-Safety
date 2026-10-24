import React, {useId} from 'react';
import {Pause, Play} from 'lucide-react';
import useAmbientMotion from './useAmbientMotion.js';

// Original medical/data symbols, revealed through a moving vertical line screen.
// CSS handles motion, including the user's reduced-motion preference.
export default function ScanlineField(){
  const id=useId().replaceAll(':','');
  const {host,paused,stopped,toggle}=useAmbientMotion();
  const wave=(cx,cy,width,height,color,phase)=>Array.from({length:19},(_,i)=>{
    const x=(i-9)*12, envelope=Math.pow(Math.max(0,1-Math.pow(x/(width/2),2)),1.8);
    return <line key={i} x1={cx+x} x2={cx+x} y1={cy-height*envelope/2} y2={cy+height*envelope/2} stroke={color} strokeWidth="2" style={{animationDelay:`${phase+i*.11}s`}}/>;
  });
  return <div ref={host} className={`scanline-field ${stopped?'is-paused':''}`}>
    <svg viewBox="0 0 1200 440" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <pattern id={`${id}-grid`} width="12" height="440" patternUnits="userSpaceOnUse"><path d="M.5 0v440" stroke="#dedfd7" strokeWidth=".7"/></pattern>
        <pattern id={`${id}-screen`} width="4" height="440" patternUnits="userSpaceOnUse"><rect width="1.5" height="440" fill="white"/></pattern>
        <mask id={`${id}-stripes`}><rect width="1200" height="440" fill={`url(#${id}-screen)`}/></mask>
        <linearGradient id={`${id}-ink`}><stop stopColor="#6962b4"/><stop offset=".5" stopColor="#159da4"/><stop offset="1" stopColor="#d29065"/></linearGradient>
      </defs>
      <rect width="1200" height="440" fill={`url(#${id}-grid)`}/>
      <g className="wave-bundle">{wave(80,180,210,180,'#7271af',-2)}{wave(400,45,190,80,'#3e8d88',-5)}{wave(1000,330,200,130,'#d08d70',-8)}{wave(720,90,140,100,'#6183b3',-1)}</g>
      <g mask={`url(#${id}-stripes)`}>
        <g className="field-symbol symbol-pill" fill="none" stroke={`url(#${id}-ink)`} strokeWidth="14"><rect x="815" y="125" width="110" height="49" rx="24.5" transform="rotate(-34 870 150)"/><path d="M856 130l27 41"/></g>
        <g className="field-symbol symbol-plus" fill="#5e9b8a"><path d="M1050 60h28v28h28v28h-28v28h-28v-28h-28V88h28z"/></g>
        <g className="field-symbol symbol-records" fill="none" stroke="#a079a0" strokeWidth="12"><path d="M1050 216h74v66h-74zM1064 234h45m-45 17h45m-45 17h26"/></g>
        <g className="field-symbol symbol-chart" fill="#7870bd"><path d="M192 280h14v53h-14zm24-28h14v81h-14zm24 43h14v38h-14zm24-67h14v105h-14z"/></g>
        <g className="field-symbol symbol-pulse" fill="none" stroke="#3f929c" strokeWidth="13"><path d="M651 342h28l13-30 20 62 18-43 12 11h39"/></g>
      </g>
    </svg>
    <div className="field-color-wash"/>
    <button className="field-motion" onClick={toggle} aria-label={paused?'Play background animation':'Pause background animation'}>{paused?<Play size={12}/>:<Pause size={12}/>}<span>{paused?'Play':'Pause'} motion</span></button>
  </div>;
}
