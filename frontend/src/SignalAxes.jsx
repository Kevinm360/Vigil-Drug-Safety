import React from 'react';
import {cubeAxes} from './signalProjection.js';
import './signal-axes.css';

const tick=value=>Math.abs(value)>=10000?value.toExponential(1):new Intl.NumberFormat('en-US',{maximumFractionDigits:1}).format(value);

export function SignalAxes({project,width,height,logMin,logMax,sigMax,zMax}){
  const axes=cubeAxes(project,width,height);
  const ranges={X:[logMin,logMax],Y:[0,sigMax],Z:[0,zMax]};
  const levels=width<500?[0,.5,1]:[0,.25,.5,.75,1];
  return <g className="signal-cube-axes" aria-label="Labeled X, Y, and Z axes with numeric tick marks" pointerEvents="none">
    {axes.map(axis=>{const {letter,color,origin,end,normal,anchor}=axis;return <g key={letter} style={{'--axis-color':color}}>
      <line className="signal-axis-line" x1={origin[0]} y1={origin[1]} x2={end[0]} y2={end[1]}/>
      {levels.map(level=>{const point=axis.point(level),value=ranges[letter][0]+level*(ranges[letter][1]-ranges[letter][0]),labelOffset=letter==='Z'&&level===0?24:12;return <g key={level}><line className="signal-axis-tick" x1={point[0]+normal[0]*2} y1={point[1]+normal[1]*2} x2={point[0]+normal[0]*7} y2={point[1]+normal[1]*7}/><text className="signal-axis-number" x={point[0]+normal[0]*labelOffset} y={point[1]+normal[1]*labelOffset+4} textAnchor={anchor}>{tick(value)}</text></g>})}
      <text className="signal-axis-letter" x={letter==='Y'?end[0]:(origin[0]+end[0])/2+normal[0]*35} y={letter==='Y'?end[1]-22:(origin[1]+end[1])/2+normal[1]*35+4} textAnchor="middle">{letter}</text>
    </g>})}
  </g>;
}

export function SignalAxisGuide({recordLabel,angle}){
  const {project}=cubeProjectionForCompass(angle);
  const origin=project(0,0,0),axes=[['X',[1,0,0],'#487b72'],['Y',[0,1,0],'#866b98'],['Z',[0,0,1],'#a36e48']];
  return <div className="signal-axis-guide">
    <div className="signal-axis-definitions" aria-label={`3D signal axis meanings; a is the number of ${recordLabel.toLowerCase()} mentioning the drug and reaction`}>
      {[['X','Reporting ratio','log₂(PRR)','#487b72'],['Y','Significance','−log₁₀(p)','#866b98'],['Z','Co-occurrences','log₁₀(a + 1)','#a36e48']].map(([letter,label,scale,color])=><div key={letter} style={{'--axis-color':color}}><b>{letter}</b><span>{label}<small>{scale}</small></span></div>)}
    </div>
    <svg className="signal-axis-compass" viewBox="0 0 104 88" role="img" aria-label="Axis orientation follows the current rotation"><circle cx={origin[0]} cy={origin[1]} r="2.5" fill="#73836a"/>{axes.map(([letter,unit,color])=>{const end=project(...unit);return <g key={letter}><line x1={origin[0]} y1={origin[1]} x2={end[0]} y2={end[1]} stroke={color} strokeWidth="1.5"/><circle cx={end[0]} cy={end[1]} r="8" fill="#f7f8f2"/><text x={end[0]} y={end[1]+4} textAnchor="middle" fill={color}>{letter}</text></g>})}</svg>
  </div>;
}

function cubeProjectionForCompass(angle){
  const origin=[52,56];
  return {project:(x,y,z)=>[origin[0]+Math.cos(angle)*x*31+Math.sin(angle)*z*25,origin[1]-y*31+(Math.sin(angle)*x-Math.cos(angle)*z)*15]};
}
