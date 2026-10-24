import {useEffect,useRef,useState} from 'react';

// Pause decorative work when hidden; CSS also supplies a static reduced-motion view.
export default function useAmbientMotion(){
  const host=useRef(null);
  const [paused,setPaused]=useState(false),[visible,setVisible]=useState(true);
  useEffect(()=>{
    let intersecting=true;
    const sync=()=>setVisible(intersecting&&!document.hidden);
    const observer=new IntersectionObserver(([entry])=>{intersecting=entry.isIntersecting;sync();});
    observer.observe(host.current);
    document.addEventListener('visibilitychange',sync);sync();
    return()=>{observer.disconnect();document.removeEventListener('visibilitychange',sync);};
  },[]);
  return {host,paused,stopped:paused||!visible,toggle:()=>setPaused(value=>!value)};
}
