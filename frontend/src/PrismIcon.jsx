import React, { useId } from 'react';
import './PrismIcon.css';

/** Small, dimensional glass objects. Labels belong to the containing control. */
export default function PrismIcon({ name = 'overview', size = 28, className = '' }) {
  const unique = useId().replace(/:/g, '');
  const id = key => `prism-${unique}-${key}`;
  const paint = key => `url(#${id(key)})`;
  const line = { stroke: paint('rim'), strokeWidth: 1.05, strokeLinejoin: 'round' };
  const orb = (cx, cy, r, tone = 'pearl') => <g key={`${cx}-${cy}`}><circle cx={cx} cy={cy + 1.4} r={r} fill="#151452" opacity=".65"/><circle cx={cx} cy={cy} r={r} fill={paint(tone)} stroke="#b3dfff" strokeOpacity=".65" strokeWidth=".7"/><ellipse cx={cx - r * .26} cy={cy - r * .38} rx={r * .42} ry={r * .2} fill="#fff" opacity=".78" transform={`rotate(-30 ${cx} ${cy})`}/></g>;
  const art = {
    overview: <>
      <path d="M9 16 25 10 27 29 11 35ZM33 9 49 14 53 32 35 27ZM12 40 28 34 30 52 14 57ZM36 33 54 38 55 55 38 51Z" fill={paint('shadow')} opacity=".9"/>
      <path d="M8 13 24 8 26 26 10 32Z" fill={paint('cyan')} {...line}/>
      <path d="m31 8 17 5 4 17-18-5Z" fill={paint('lavender')} {...line}/>
      <path d="m11 37 16-6 2 18-16 5Z" fill={paint('lavender')} {...line}/>
      <path d="m34 30 18 5 1 17-17-4Z" fill={paint('cyan')} {...line}/>
      <path d="m10 15 12-4M34 11l12 4M14 39l10-4m13-2 12 4" fill="none" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" opacity=".78"/>
    </>,
    reactions: <>
      <g transform="rotate(-43 32 32)">
        <rect x="7" y="22" width="50" height="24" rx="12" fill={paint('shadow')}/>
        <rect x="7" y="18" width="50" height="24" rx="12" fill={paint('pearl')} {...line}/>
        <path d="M32 18h13a12 12 0 0 1 0 24H32Z" fill={paint('cyan')} stroke="#b8c5ff" strokeWidth=".6"/>
        <path d="M19 21h24c7 0 9 3 10 5" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" opacity=".8"/>
        <path d="M32 19v22" stroke="#fff" strokeWidth="1.1" opacity=".6"/>
        <path d="M12 35q5 7 14 5h18" fill="none" stroke="#7153eb" strokeWidth="1.4" opacity=".6"/>
      </g>
      <circle cx="52" cy="13" r="3.5" fill={paint('pearl')} stroke="#d9edff" strokeWidth=".8"/>
    </>,
    reports: <>
      <path d="m22 9 28 4 4 39-28 5-10-10Z" fill={paint('lavender')} stroke="#b4b5ff" strokeWidth=".8"/>
      <path d="m15 10 28 4 5 39-28 3-8-8Z" fill={paint('shadow')} stroke="#a7caff" strokeOpacity=".6" strokeWidth=".8"/>
      <path d="m12 7 27 5 5 36-27 5-8-8Z" fill={paint('pearl')} {...line}/>
      <path d="m12 7 27 5 1 8-27-5Z" fill={paint('cyan')} opacity=".88"/>
      <path d="m15 11 20 4" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" opacity=".85"/>
      <path d="m16 25 19 3m-18 5 18 3m-17 4 11 2" fill="none" stroke="#42409d" strokeWidth="2.4" strokeLinecap="round" opacity=".72"/>
      <path d="m17 53-1-9-7 1" fill={paint('cyan')} stroke="#e6faff" strokeWidth=".8"/>
    </>,
    signals: <>
      <g transform="rotate(-31 32 32)">
        <path d="M32 13C16 13 5 23 5 34s11 20 27 20 27-9 27-20-11-21-27-21Zm0 10c10 0 17 4 17 10s-7 10-17 10-17-4-17-10 7-10 17-10Z" fill={paint('shadow')} fillRule="evenodd"/>
        <path d="M32 9C16 9 5 19 5 30s11 20 27 20 27-9 27-20S48 9 32 9Zm0 11c10 0 17 4 17 10s-7 10-17 10-17-4-17-10 7-10 17-10Z" fill={paint('holo')} stroke={paint('rim')} strokeWidth="1" fillRule="evenodd"/>
        <path d="M9 27C11 13 43 8 54 24M16 34c5 9 26 9 32 0" fill="none" stroke="#fff" strokeOpacity=".75" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M9 33c8 16 40 17 47-3" fill="none" stroke="#4943ec" strokeWidth="2.3" opacity=".64"/>
      </g>
      <circle cx="48" cy="13" r="4.2" fill={paint('cyan')} stroke="#e7feff" strokeWidth=".9"/>
      <path d="M48 6v-3m7 10h4" stroke="#b8dcff" strokeWidth="1" strokeLinecap="round"/>
    </>,
    severity: <>
      <path d="M32 58 9 35C-5 19 16 6 32 20 47 6 68 21 55 36Z" fill={paint('shadow')} transform="translate(0 -1)"/>
      <path d="M32 53 9 31C-3 17 16 3 32 16 47 3 67 18 55 32Z" fill={paint('rose')} {...line}/>
      <path d="M12 27c-5-10 8-17 17-10" fill="none" stroke="#fff" strokeWidth="2.3" strokeLinecap="round" opacity=".85"/>
      <path d="m14 33 10 1 5-9 7 16 5-9h10" fill="none" stroke="#f6ffff" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" opacity=".94"/>
      <path d="m35 48 15-15" stroke="#7556e9" strokeWidth="2.5" strokeLinecap="round" opacity=".58"/>
    </>,
    network: <>
      <path d="m17 20 30 3M18 22l12 27m19-25L31 49M18 23l26 17" fill="none" stroke="#202064" strokeWidth="7" strokeLinecap="round"/>
      <path d="m17 17 30 3M18 19l12 27m19-25L31 46M18 20l26 17" fill="none" stroke={paint('rim')} strokeWidth="4.7" strokeLinecap="round"/>
      <path d="m18 16 28 3M19 20l10 24m19-22L32 43" fill="none" stroke="#c7fbff" strokeWidth="1.2" opacity=".65"/>
      {orb(16, 17, 10, 'cyan')}{orb(48, 20, 8)}{orb(44, 38, 6, 'cyan')}{orb(30, 48, 10)}
    </>,
    narratives: <>
      <path d="m19 13 34 5 2 27-9 8-27-7Z" fill={paint('lavender')} stroke="#bdc2ff" strokeWidth=".8"/>
      <path d="m9 10 37 6 3 27-19 3-13 10-1-12-6-5Z" fill={paint('pearl')} {...line}/>
      <path d="m10 10 36 6 1 6-36-6Z" fill={paint('cyan')} opacity=".7"/>
      <path d="m13 13 29 5" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" opacity=".9"/>
      <path d="m19 26 6 1-1 6-6-1 1-8m13 4 6 1-1 6-6-1 1-8" fill={paint('shadow')} stroke="#7c68d9" strokeWidth="1.4" strokeLinejoin="round"/>
      <path d="m17 56 13-10 19-3" fill="none" stroke="#9af5ff" strokeWidth="1"/>
    </>,
    models: <>
      <path d="m31 7 23 23-18 29L9 37Z" fill={paint('shadow')}/>
      <path d="m29 4 24 23-18 29L8 34Z" fill={paint('lavender')} {...line}/>
      <path d="m29 4 8 25 16-2Z" fill={paint('pearl')} {...line}/>
      <path d="m29 4 8 25-29 5Z" fill={paint('cyan')} {...line}/>
      <path d="m8 34 29-5-2 27Z" fill={paint('lavender')} {...line}/>
      <path d="m37 29 16-2-18 29Z" fill={paint('rose')} {...line}/>
      <path d="m29 6 7 22-25 5" fill="none" stroke="#efffff" strokeWidth="1.5" strokeLinecap="round" opacity=".9"/>
      <circle cx="52" cy="9" r="2" fill="#c0eaff"/><path d="M57 13v5m-2.5-2.5h5" stroke="#dcd3ff" strokeLinecap="round"/>
    </>,
    volume: <>
      <path d="m8 35 11-4 7 4v20l-11 5-7-4Zm18-13 11-4 7 4v29l-11 5-7-4Zm18-12 9-4 6 4v35l-9 5-6-4Z" fill={paint('shadow')} opacity=".9"/>
      <path d="m7 31 11-4 7 4v20l-11 5-7-4Z" fill={paint('lavender')} {...line}/>
      <path d="m7 31 11-4 7 4-11 4Z" fill={paint('pearl')} {...line}/>
      <path d="m14 35 11-4v20l-11 5Z" fill={paint('cyan')} {...line}/>
      <path d="m25 18 11-4 7 4v29l-11 5-7-4Z" fill={paint('lavender')} {...line}/>
      <path d="m25 18 11-4 7 4-11 4Z" fill={paint('pearl')} {...line}/>
      <path d="m32 22 11-4v29l-11 5Z" fill={paint('cyan')} {...line}/>
      <path d="m43 7 9-4 6 4v35l-9 5-6-4Z" fill={paint('lavender')} {...line}/>
      <path d="m43 7 9-4 6 4-9 4Z" fill={paint('pearl')} {...line}/>
      <path d="m49 11 9-4v35l-9 5Z" fill={paint('cyan')} {...line}/>
    </>,
    trend: <>
      <path d="m7 46 17-17 10 9 13-16-8-5 20-5-1 21-6-6-17 23-10-10-13 13Z" fill={paint('shadow')} transform="translate(0 3)"/>
      <path d="m6 43 17-17 10 9 13-16-8-5 20-5-1 21-6-6-17 23-10-10-13 13Z" fill={paint('holo')} {...line}/>
      <path d="m9 42 14-13 10 9 15-19-6-4 13-3" fill="none" stroke="#f1ffff" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" opacity=".8"/>
      <path d="m15 54 9-9 10 9 20-25" fill="none" stroke="#7565f7" strokeWidth="1" opacity=".7"/>
    </>,
    coverage: <>
      <path d="m13 13 39 6 3 35-37 5-8-8Z" fill={paint('shadow')}/>
      <path d="m11 10 39 6 3 35-37 5-8-8Z" fill={paint('pearl')} {...line}/>
      <path d="m11 10 39 6 1 10-42-6Z" fill={paint('cyan')} {...line}/>
      <path d="m17 7 1 9m24-5 1 8" stroke={paint('rim')} strokeWidth="4" strokeLinecap="round"/>
      <path d="m18 7 1 7m24-2 1 5" stroke="#fff" strokeWidth="1" strokeLinecap="round" opacity=".8"/>
      <g fill="#7263c9" opacity=".7"><path d="m16 29 6 1 .4 5-6-1Zm11 1 6 1 .4 5-6-1Zm11 2 6 1 .4 5-6-1Zm-21 7 6 1 .4 5-6-1Zm11 1 6 1 .4 5-6-1Z"/></g>
      <path d="m37 44 3 3 7-9" fill="none" stroke="#06b9df" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="m16 56-1-9-7 1" fill={paint('lavender')} stroke="#d0efff" strokeWidth=".8"/>
    </>,
    brand: <>
      <g transform="rotate(-29 32 32)">
        <path d="M32 7C16 7 4 18 4 32s12 25 28 25 28-11 28-25S48 7 32 7Zm0 12c9 0 16 6 16 13s-7 13-16 13-16-6-16-13 7-13 16-13Z" fill={paint('holo')} fillRule="evenodd" stroke={paint('rim')} strokeWidth="1.1"/>
        <path d="M8 28C11 9 44 5 55 25M17 34c3 11 25 15 31 0" fill="none" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" opacity=".9"/>
        <path d="M9 37c11 22 39 17 47-3" fill="none" stroke="#6450f3" strokeWidth="2.8" opacity=".75"/>
      </g>
      <path d="m27 27 6 10 8-17" fill="none" stroke="#e0ffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </>,
  };
  return <svg className={`prism-icon prism-icon--${name} ${className}`.trim()} width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id={id('holo')} x1="7" y1="9" x2="54" y2="54" gradientUnits="userSpaceOnUse"><stop stopColor="#f8c9ed"/><stop offset=".18" stopColor="#aaa3ff"/><stop offset=".35" stopColor="#3ce7f9"/><stop offset=".49" stopColor="#a1fff2"/><stop offset=".62" stopColor="#6975f7"/><stop offset=".78" stopColor="#e09afb"/><stop offset=".9" stopColor="#ffc6da"/><stop offset="1" stopColor="#7770ff"/></linearGradient>
      <linearGradient id={id('cyan')} x1="8" y1="6" x2="51" y2="54" gradientUnits="userSpaceOnUse"><stop stopColor="#f1ffff"/><stop offset=".22" stopColor="#9bf7f3"/><stop offset=".46" stopColor="#33d8f0"/><stop offset=".69" stopColor="#4f9ef0"/><stop offset=".87" stopColor="#8d7de5"/><stop offset="1" stopColor="#cca9ff"/></linearGradient>
      <linearGradient id={id('lavender')} x1="9" y1="7" x2="52" y2="55" gradientUnits="userSpaceOnUse"><stop stopColor="#e9ddff"/><stop offset=".25" stopColor="#b6adff"/><stop offset=".52" stopColor="#8278ec"/><stop offset=".75" stopColor="#be8af0"/><stop offset=".9" stopColor="#f6b0db"/><stop offset="1" stopColor="#7c68cb"/></linearGradient>
      <radialGradient id={id('pearl')} cx=".23" cy=".13" r="1"><stop stopColor="#fff9fb"/><stop offset=".28" stopColor="#d4ddff"/><stop offset=".5" stopColor="#9dd9f6"/><stop offset=".74" stopColor="#ac95ee"/><stop offset=".89" stopColor="#e8a9e5"/><stop offset="1" stopColor="#6c62ba"/></radialGradient>
      <linearGradient id={id('rose')} x1="10" y1="9" x2="48" y2="56" gradientUnits="userSpaceOnUse"><stop stopColor="#fff2f8"/><stop offset=".23" stopColor="#f4b6e2"/><stop offset=".48" stopColor="#c18dfa"/><stop offset=".7" stopColor="#8a79e9"/><stop offset=".9" stopColor="#58d4ed"/><stop offset="1" stopColor="#c3a5f9"/></linearGradient>
      <linearGradient id={id('shadow')} x1="13" y1="13" x2="48" y2="59" gradientUnits="userSpaceOnUse"><stop stopColor="#8a68c5"/><stop offset=".4" stopColor="#4b3b96"/><stop offset=".7" stopColor="#283778"/><stop offset="1" stopColor="#171d4a"/></linearGradient>
      <linearGradient id={id('rim')} x1="9" y1="5" x2="51" y2="57" gradientUnits="userSpaceOnUse"><stop stopColor="#fff"/><stop offset=".32" stopColor="#d4eeff"/><stop offset=".55" stopColor="#a3eaf8"/><stop offset=".78" stopColor="#ddb3fc"/><stop offset="1" stopColor="#a6b7ff"/></linearGradient>
    </defs>
    <g className="prism-icon__object">{art[name] || art.overview}</g>
  </svg>;
}
