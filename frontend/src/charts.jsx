import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import './charts.css';
import ReactionNetwork from './ReactionNetwork.jsx';

const PALETTE = ['#477f79', '#8773a5', '#b77d59', '#6e8ba6', '#8a9a64', '#c2a675', '#9c839a'];
const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const finite = (value) => value !== null && value !== '' && Number.isFinite(Number(value));
const list = (data) => Array.isArray(data) ? data : Array.isArray(data?.rows) ? data.rows : Array.isArray(data?.results) ? data.results : [];
const fmt = (value, digits = 0) => number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
const clip = (value, min, max) => Math.max(min, Math.min(max, value));
const short = (value, length = 25) => String(value ?? '').length > length ? `${String(value).slice(0, length - 1)}…` : String(value ?? '');
const label = (value) => String(value ?? 'Unknown').replaceAll('_', ' ');
const flagged = (row) => row.signal === true || row.signal === 1 || row.signal === 'true' || (row.signal == null && number(row.a ?? row.count ?? row.reports) >= 3 && number(row.prr) >= 2 && number(row.chi2) >= 4);
const chartRows = (row, recordLabel = 'Reports') => [
  [recordLabel, fmt(row.a ?? row.count ?? row.reports)],
  ...(finite(row.prr) ? [['PRR', fmt(row.prr, 2)]] : []),
  ...(finite(row.ror) ? [['Reporting odds ratio', fmt(row.ror, 2)]] : []),
  ...(finite(row.chi2) ? [['Chi-square', fmt(row.chi2, 2)]] : []),
  ...(row.signal != null ? [['Statistical flag', flagged(row) ? 'Meets screening rule' : 'Below screening rule']] : []),
];

function EmptyChart({ message = 'No chart data is available for these filters.' }) {
  return <div className="chart-empty" role="status"><svg viewBox="0 0 56 44" aria-hidden="true"><path d="M5 36V8M5 36h46M13 29l10-12 10 7L47 9" /><circle cx="47" cy="9" r="3" /></svg><span>{message}</span><small>Try a different drug, date range, or cohort.</small></div>;
}

function useTooltip() {
  const elementRef = useRef(null);
  const observerRef = useRef(null);
  const [width, setWidth] = useState(920);
  const ref = useCallback((element) => {
    observerRef.current?.disconnect();
    elementRef.current = element;
    if (element) {
      const measure = () => setWidth(Math.round(element.clientWidth) || 920);
      measure();
      if (typeof ResizeObserver !== 'undefined') {
        observerRef.current = new ResizeObserver(measure);
        observerRef.current.observe(element);
      }
    }
  }, []);
  useEffect(() => () => observerRef.current?.disconnect(), []);
  const [tip, setTip] = useState(null);
  const show = (event, title, rows, color = PALETTE[0]) => {
    const bounds = elementRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const target = event.currentTarget?.getBoundingClientRect?.();
    const x = event.clientX || (target ? target.left + target.width / 2 : bounds.left + bounds.width / 2);
    const y = event.clientY || (target ? target.top : bounds.top + 30);
    const below = y - bounds.top < 155;
    setTip({ title, rows, color, below, x: clip(x - bounds.left, 125, Math.max(125, bounds.width - 125)), y: clip(y - bounds.top + (below ? 16 : -12), 12, bounds.height - 20) });
  };
  const hide = () => setTip(null);
  const bind = (title, rows, color) => ({
    onPointerEnter: (event) => show(event, title, rows, color),
    onPointerMove: (event) => show(event, title, rows, color),
    onPointerLeave: hide,
    onFocus: (event) => show(event, title, rows, color),
    onBlur: hide,
    onKeyDown: (event) => { if (event.key === 'Escape') hide(); },
  });
  const tooltip = tip && <div className="chart-tooltip" role="tooltip" style={{ left: tip.x, top: tip.y, transform: `translate(-50%, ${tip.below ? '0' : '-100%'})`, '--tip-color': tip.color }}><strong>{tip.title}</strong>{tip.rows.map(([key, value], index) => <div key={`${key}-${index}`}><span>{key}</span><b>{value}</b></div>)}</div>;
  return { ref, width, tip, show, hide, bind, tooltip };
}

function Legend({ items, note }) {
  return <div className="chart-legend">{items.map((item, index) => <span className="chart-legend-item" key={`${item.label}-${index}`}><i style={{ background: item.color || PALETTE[index % PALETTE.length] }} />{item.label}</span>)}{note && <small>{note}</small>}</div>;
}

function Grid({ width = 920, height = 310, left = 58, right = 24, top = 20, bottom = 48, xTicks = [], yTicks = [], x, y, xLabel, yLabel }) {
  return <g className="chart-grid">
    {yTicks.map((tick, index) => <g key={`y${index}`}><line x1={left} x2={width - right} y1={y(tick.value ?? tick)} y2={y(tick.value ?? tick)} /><text x={left - 14} y={y(tick.value ?? tick) + 4} textAnchor="end">{tick.label ?? fmt(tick)}</text></g>)}
    {xTicks.map((tick, index) => <g key={`x${index}`}><text x={x(tick.value ?? tick)} y={height - bottom + 26} textAnchor="middle">{tick.label ?? fmt(tick)}</text></g>)}
    {xLabel && <text className="chart-axis-label" x={(left + width - right) / 2} y={height - 4} textAnchor="middle">{xLabel}</text>}
    {yLabel && <text className="chart-axis-label" transform={`translate(15 ${(top + height - bottom) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>}
  </g>;
}

function parseDate(value) {
  const raw = String(value ?? '');
  const normalized = /^\d{8}$/.test(raw) ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}` : raw;
  const date = new Date(normalized);
  return Number.isFinite(date.getTime()) ? date : null;
}

export function TimeSeriesChart({ data, compareData, drug = 'Selected drug', compareDrug = 'Comparison', recordLabel = 'Reports' }) {
  const tooltip = useTooltip();
  const gradient = useId().replaceAll(':', '');
  const [active, setActive] = useState(null);
  const normalize = (input) => list(input).map((row) => ({ ...row, dateObject: parseDate(row.date ?? row.week ?? row.time), value: number(row.count ?? row.weekly_reports ?? row.reports) })).filter((row) => row.dateObject).sort((a, b) => a.dateObject - b.dateObject);
  const main = useMemo(() => normalize(data), [data]);
  const other = useMemo(() => normalize(compareData), [compareData]);
  if (!main.length && !other.length) return <EmptyChart message={`No ${recordLabel.toLowerCase()} history is available for this selection.`} />;
  const all = [...main, ...other];
  const W = Math.max(320, tooltip.width), H = W < 550 ? 260 : 304, L = 52, R = 21, T = 22, B = 41;
  const min = Math.min(...all.map((row) => row.dateObject.getTime()));
  const max = Math.max(...all.map((row) => row.dateObject.getTime()));
  const maxValue = Math.max(1, ...all.map((row) => row.value)) * 1.12;
  const step = Math.max(1, Math.pow(10, Math.floor(Math.log10(maxValue))) / 2);
  const ceiling = Math.ceil(maxValue / step) * step;
  const x = (value) => max === min ? (L + W - R) / 2 : L + ((Number(value) - min) / (max - min)) * (W - L - R);
  const y = (value) => H - B - (value / ceiling) * (H - T - B);
  const path = (points) => points.map((row, index) => `${index ? 'L' : 'M'}${x(row.dateObject)},${y(row.value)}`).join(' ');
  const yTicks = Array.from({ length: 5 }, (_, index) => ({ value: ceiling * index / 4, label: fmt(ceiling * index / 4, ceiling < 4 ? 1 : 0) }));
  const tickCount = W < 550 ? 4 : 6;
  const xTicks = Array.from({ length: max === min ? 1 : tickCount }, (_, index) => { const date = new Date(min + (max - min) * index / (tickCount - 1)); return { value: date.getTime(), label: date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' }) }; });
  const onPoint = (event, row, name, color) => { setActive({ row, color }); tooltip.show(event, row.dateObject.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' }), [[name, `${fmt(row.value)} ${recordLabel.toLowerCase()}`]], color); };
  return <div ref={tooltip.ref} className="chart-shell time-series-chart" onPointerLeave={() => { tooltip.hide(); setActive(null); }}>
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${recordLabel} over time for ${drug}${other.length ? ` compared with ${compareDrug}` : ''}`}>
      <title>{recordLabel} over time. Focus a point or move over the chart to inspect its count.</title>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={PALETTE[0]} stopOpacity=".10" /><stop offset="55%" stopColor={PALETTE[0]} stopOpacity=".04" /><stop offset="100%" stopColor={PALETTE[1]} stopOpacity="0" /></linearGradient>
        <linearGradient id={`${gradient}-line`} x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="#8fa9ff" /><stop offset="30%" stopColor={PALETTE[0]} /><stop offset="65%" stopColor="#9aeeff" /><stop offset="100%" stopColor={PALETTE[1]} /></linearGradient>
      </defs>
      <Grid width={W} height={H} left={L} right={R} top={T} bottom={B} xTicks={xTicks} yTicks={yTicks} x={x} y={y} />
      {main.length > 1 && <path d={`${path(main)} L${x(main.at(-1).dateObject)},${y(0)} L${x(main[0].dateObject)},${y(0)} Z`} fill={`url(#${gradient})`} />}
      {other.length > 1 && <path d={path(other)} fill="none" stroke={PALETTE[1]} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" strokeDasharray="6 5" />}
      {main.length > 1 && <path className="chart-primary-line" d={path(main)} fill="none" stroke={PALETTE[0]} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />}
      <rect x={L} y={T} width={W - L - R} height={H - T - B} fill="transparent" onPointerMove={(event) => { const bounds = event.currentTarget.ownerSVGElement.getBoundingClientRect(); const mouseX = (event.clientX - bounds.left) / bounds.width * W; const point = all.reduce((best, row) => Math.abs(x(row.dateObject) - mouseX) < Math.abs(x(best.dateObject) - mouseX) ? row : best, all[0]); const isMain = main.includes(point); onPoint(event, point, isMain ? drug : compareDrug, isMain ? PALETTE[0] : PALETTE[1]); }} />
      {[{ points: main, name: drug, color: PALETTE[0] }, { points: other, name: compareDrug, color: PALETTE[1] }].map((series) => series.points.map((row, index) => <circle key={`${series.name}-${index}`} cx={x(row.dateObject)} cy={y(row.value)} r={series.points.length === 1 ? 5 : 8} fill={series.points.length === 1 ? series.color : 'transparent'} className="chart-focus-point" tabIndex={0} role="graphics-symbol" aria-label={`${series.name}, ${row.dateObject.toLocaleDateString(undefined, { timeZone: 'UTC' })}, ${fmt(row.value)} ${recordLabel.toLowerCase()}`} onFocus={(event) => onPoint(event, row, series.name, series.color)} onBlur={() => { tooltip.hide(); setActive(null); }} onPointerMove={(event) => onPoint(event, row, series.name, series.color)} />))}
      {active && <g pointerEvents="none"><line x1={x(active.row.dateObject)} x2={x(active.row.dateObject)} y1={T} y2={H - B} stroke={active.color} strokeOpacity=".4" strokeDasharray="4 5" /><circle cx={x(active.row.dateObject)} cy={y(active.row.value)} r="11" fill={active.color} fillOpacity=".13" /><circle cx={x(active.row.dateObject)} cy={y(active.row.value)} r="5" fill="#f7f8f2" stroke={active.color} strokeWidth="2.5" /></g>}
    </svg>
    <Legend items={[{ label: drug, color: PALETTE[0] }, ...(other.length ? [{ label: compareDrug, color: PALETTE[1] }] : [])]} note={`${recordLabel} by date · hover or focus for detail`} />
    {tooltip.tooltip}
  </div>;
}

function reactionInteraction(onSelect,value,selected){
  if(!onSelect)return {};
  return {role:'button','aria-pressed':String(value||'').toUpperCase()===selected,onClick:()=>onSelect(value),onKeyDown:event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(value)}}};
}

export function HorizontalBars({ onSelect, selectedReaction='', data, valueKey = 'count', labelKey = 'reaction', color = PALETTE[0], valueLabel, showComparison, compareLabel = 'Comparison' }) {
  const tooltip = useTooltip();
  const rows = list(data).filter((row) => finite(row[valueKey] ?? row.count ?? row.reports ?? row.a));
  if (!rows.length) return <EmptyChart message="No reactions match this selection." />;
  const compare = showComparison ?? rows.some((row) => number(row.compare_reports) > 0);
  const max = Math.max(0, ...rows.map((row) => number(row[valueKey] ?? row.count ?? row.reports ?? row.a)), ...(compare ? rows.map((row) => number(row.compare_reports)) : [])) || 1;
  const values = rows.map((row) => number(row[valueKey] ?? row.count ?? row.reports ?? row.a));
  const decimals = valueKey === 'prr' ? 2 : values.some((value) => !Number.isInteger(value)) ? Math.max(...values) < 2 ? 3 : 2 : 0;
  const heading = valueLabel ?? (valueKey === 'prr' ? 'PRR' : decimals ? 'Score' : 'Reports');
  const total = values.reduce((sum, value) => sum + value, 0);
  return <div className="chart-shell horizontal-bars" ref={tooltip.ref}>
    <div className="bar-column-head"><span>{labelKey === 'reaction' ? 'Reaction' : 'Term / feature'}</span><span>{heading}</span></div>
    {rows.map((row, index) => { const value = number(row[valueKey] ?? row.count ?? row.reports ?? row.a); const name = label(row[labelKey] ?? row.label ?? row.name); const comparison = compare && finite(row.compare_reports); return <div className="horizontal-bar-row" {...reactionInteraction(onSelect,row[labelKey],selectedReaction)} key={`${name}-${index}`} tabIndex={0} aria-label={`${name}: ${fmt(value, decimals)}${comparison ? `, ${compareLabel} ${fmt(row.compare_reports)}` : ''}`} {...tooltip.bind(name, valueKey === 'prr' ? chartRows(row) : [[heading, fmt(value, decimals)], ...(finite(row.coefficient) ? [['Signed coefficient', fmt(row.coefficient, 4)]] : []), ...(comparison ? [[`${compareLabel} ${heading.toLowerCase()}`, fmt(row.compare_reports)]] : []), ...(!decimals ? [['Share of displayed reactions', `${fmt(total ? value / total * 100 : 0, 1)}%`]] : [])], color)}>
      <div className="horizontal-bar-label"><span className="bar-rank">{String(index + 1).padStart(2, '0')}</span><span>{name}</span></div>
      <div className="horizontal-bar-track"><span className="horizontal-bar-fill" style={{ width: `${Math.max(0, value) / max * 100}%`, minWidth: value > 0 ? 2 : 0, '--bar-color': color }} />{comparison && <span className="horizontal-bar-comparison" style={{ width: `${Math.max(0, number(row.compare_reports)) / max * 100}%` }} />}</div>
      <b>{fmt(value, decimals)}</b>
    </div>; })}
    {compare && <Legend items={[{ label: 'Selected drug', color }, { label: compareLabel, color: PALETTE[1] }]} />}
    {tooltip.tooltip}
  </div>;
}

function logPFromChiSquare(value) {
  const z = Math.sqrt(Math.max(0, number(value)) / 2);
  const t = 1 / (1 + .5 * z);
  const exponent = -z * z - 1.26551223 + t * (1.00002368 + t * (.37409196 + t * (.09678418 + t * (-.18628806 + t * (.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-.82215223 + t * .17087277))))))));
  return Math.max(0, -(Math.log(t) + exponent) / Math.LN10);
}

export function SignalPlot({ onSelect, selectedReaction='', data, recordLabel = 'Reports' }) {
  const tooltip = useTooltip();
  const [mode, setMode] = useState('volume');
  const [angle, setAngle] = useState(-.58);
  const drag = useRef(null);
  const rows = list(data).filter((row) => finite(row.prr) && number(row.prr) > 0).map((row) => ({ ...row, volume: number(row.a ?? row.count ?? row.reports), logPRR: Math.log2(number(row.prr)), significance: finite(row.p_value ?? row.p) ? -Math.log10(Math.max(Number.MIN_VALUE, number(row.p_value ?? row.p))) : logPFromChiSquare(row.chi2) }));
  if (!rows.length) return <EmptyChart message="No disproportionality results are available yet." />;
  const W = Math.max(320, tooltip.width), H = 365, L = 66, R = 25, T = 20, B = 58;
  const volumeMax = Math.max(3, ...rows.map((row) => row.volume)) * 1.1;
  const prrMax = Math.max(3, ...rows.map((row) => number(row.prr))) * 1.1;
  const logMin = Math.min(-1, ...rows.map((row) => row.logPRR)) - .3;
  const logMax = Math.max(2, ...rows.map((row) => row.logPRR)) + .3;
  const sigMax = Math.max(3, ...rows.map((row) => row.significance)) * 1.12;
  const xMin = mode === 'volume' ? 0 : logMin, xMax = mode === 'volume' ? volumeMax : logMax;
  const yMax = mode === 'volume' ? prrMax : sigMax;
  const x = (value) => L + (value - xMin) / (xMax - xMin) * (W - L - R);
  const y = (value) => H - B - value / yMax * (H - T - B);
  const xTicks = Array.from({ length: 6 }, (_, index) => ({ value: xMin + (xMax - xMin) * index / 5, label: fmt(xMin + (xMax - xMin) * index / 5, mode === 'volume' && volumeMax >= 10 ? 0 : 1) }));
  const yTicks = Array.from({ length: 5 }, (_, index) => ({ value: yMax * index / 4, label: fmt(yMax * index / 4, 1) }));
  const xThreshold = mode === 'volume' ? 3 : 1, yThreshold = mode === 'volume' ? 2 : logPFromChiSquare(4);
  const projected = (vx, vy, vz) => {
    const scale = Math.min(1, (W - 55) / 550);
    const ax = (vx - .5) * 400 * scale, ay = (vy - .5) * 260, az = (vz - .5) * 260 * scale;
    return [W / 2 + Math.cos(angle) * ax + Math.sin(angle) * az, H / 2 + ay * -.78 + (Math.sin(angle) * ax - Math.cos(angle) * az) * .38];
  };
  const cubeCorners = Array.from({ length: 8 }, (_, index) => projected(index & 1 ? 1 : 0, index & 2 ? 1 : 0, index & 4 ? 1 : 0));
  const cubeEdges = [[0,1],[0,2],[0,4],[1,3],[1,5],[2,3],[2,6],[3,7],[4,5],[4,6],[5,7],[6,7]];
  const zMax = Math.max(1, ...rows.map((row) => Math.log10(row.volume + 1)));
  return <div ref={tooltip.ref} className="chart-shell signal-chart">
    <div className="chart-controls"><div className="chart-segmented" aria-label="Signal visualization">{[['volume', 'Co-occurrences'], ['volcano', 'Volcano'], ['cube', '3D signals']].map(([value, text]) => <button key={value} className={mode === value ? 'is-active' : ''} aria-pressed={mode === value} onClick={() => { setMode(value); tooltip.hide(); }}>{text}</button>)}</div>{mode === 'cube' && <button className="chart-text-button" onClick={() => setAngle((value) => value + Math.PI / 6)} aria-label="Rotate 3D signals by 30 degrees">Rotate ↻</button>}</div>
    <svg className={`chart-svg ${mode === 'cube' ? 'chart-svg-rotatable' : ''}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={mode === 'volume' ? `Scatter plot of ${recordLabel.toLowerCase()} with drug–reaction co-occurrences against proportional reporting ratios` : mode === 'volcano' ? 'Volcano plot of log base 2 proportional reporting ratios against negative log base 10 p-values' : `Rotatable three dimensional projection of reporting ratio, significance, and ${recordLabel.toLowerCase()} volume`} onPointerDown={(event) => { if (mode === 'cube' && !(onSelect && event.target.closest('.chart-point'))) { drag.current = { x: event.clientX, angle }; event.currentTarget.setPointerCapture(event.pointerId); } }} onPointerMove={(event) => { if (drag.current && mode === 'cube') setAngle(drag.current.angle + (event.clientX - drag.current.x) * .008); }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <title>{mode === 'cube' ? 'Drag horizontally or use Rotate to turn the projected cube.' : 'Focus a reaction point to inspect its signal statistics.'}</title>
      {mode !== 'cube' ? <>
        <rect x={x(xThreshold)} y={T} width={Math.max(0, W - R - x(xThreshold))} height={Math.max(0, y(yThreshold) - T)} fill={PALETTE[1]} opacity=".035" />
        <Grid width={W} height={H} left={L} right={R} top={T} bottom={B} xTicks={xTicks} yTicks={yTicks} x={x} y={y} xLabel={mode === 'volume' ? `${recordLabel} with drug + reaction (a)` : 'log₂ proportional reporting ratio (PRR)'} yLabel={mode === 'volume' ? 'Proportional reporting ratio' : '−log₁₀ p-value'} />
        <line x1={x(xThreshold)} x2={x(xThreshold)} y1={T} y2={H - B} stroke={PALETTE[1]} strokeOpacity=".4" strokeDasharray="5 5" />
        <line x1={L} x2={W - R} y1={y(yThreshold)} y2={y(yThreshold)} stroke={PALETTE[1]} strokeOpacity=".4" strokeDasharray="5 5" />
        {rows.map((row, index) => <circle key={`${row.reaction}-${index}`} cx={x(mode === 'volume' ? row.volume : row.logPRR)} cy={y(mode === 'volume' ? number(row.prr) : row.significance)} r={flagged(row) ? 5.5 : 4} fill={flagged(row) ? PALETTE[1] : PALETTE[0]} fillOpacity={flagged(row) ? '.85' : '.55'} stroke={flagged(row) ? '#8773a5' : '#477f79'} strokeWidth=".8" className="chart-point" tabIndex={0} role="graphics-symbol" {...reactionInteraction(onSelect,row.reaction,selectedReaction)} aria-label={`${row.reaction}, ${fmt(row.volume)} ${recordLabel.toLowerCase()}, PRR ${fmt(row.prr, 2)}${flagged(row) ? ', meets screening rule' : ''}`} {...tooltip.bind(label(row.reaction), chartRows(row, recordLabel), flagged(row) ? PALETTE[1] : PALETTE[0])} />)}
      </> : <>
        {cubeEdges.map(([a, b], index) => <line key={index} x1={cubeCorners[a][0]} y1={cubeCorners[a][1]} x2={cubeCorners[b][0]} y2={cubeCorners[b][1]} stroke="#8ea7bf" strokeOpacity=".22" strokeDasharray={index < 3 ? undefined : '3 5'} />)}
        {[0,.25,.5,.75,1].map((level) => { const p1 = projected(0,0,level), p2 = projected(1,0,level), p3 = projected(1,1,level); return <path key={level} d={`M${p1}L${p2}L${p3}`} fill="none" stroke="#6d87a2" strokeOpacity=".12" />; })}
        {rows.map((row, index) => { const p = projected((row.logPRR - logMin) / (logMax - logMin), row.significance / sigMax, Math.log10(row.volume + 1) / zMax); return <circle key={`${row.reaction}-${index}`} cx={p[0]} cy={p[1]} r={3.5 + Math.log10(row.volume + 1)} fill={flagged(row) ? PALETTE[1] : PALETTE[0]} fillOpacity=".8" stroke={flagged(row) ? '#8773a5' : '#477f79'} strokeWidth=".7" className="chart-point" tabIndex={0} role="graphics-symbol" {...reactionInteraction(onSelect,row.reaction,selectedReaction)} aria-label={`${row.reaction}, ${fmt(row.volume)} ${recordLabel.toLowerCase()}, PRR ${fmt(row.prr, 2)}, chi-square ${fmt(row.chi2, 2)}`} {...tooltip.bind(label(row.reaction), chartRows(row, recordLabel), flagged(row) ? PALETTE[1] : PALETTE[0])} />; })}
        <text x={W / 2} y={H - 10} textAnchor="middle" className="chart-cube-label">{W < 500 ? 'X · log₂(PRR)  Y · −log₁₀(p)  Z · log₁₀(a+1)' : `X · log₂(PRR)　 Y · −log₁₀(p)　 Z · log₁₀(${recordLabel.toLowerCase()} + 1)`}</text>
      </>}
    </svg>
    <Legend items={[{ label: 'Meets screening rule', color: PALETTE[1] }, { label: 'Other reactions', color: PALETTE[0] }]} note={mode === 'cube' ? 'Drag to rotate · focus points for detail' : 'PRR ≥ 2 · χ² ≥ 4 · a ≥ 3'} />
    {mode !== 'volume' && <p className="chart-method-note">P-values use a chi-square distribution with 1 degree of freedom. Screening statistics are exploratory.</p>}
    {tooltip.tooltip}
  </div>;
}

export function DonutChart({ data, labelKey = 'label', valueKey = 'count' }) {
  const tooltip = useTooltip();
  const donutId = useId().replaceAll(':', '');
  const [active, setActive] = useState(null);
  const rows = list(data).map((row) => ({ ...row, name: label(row[labelKey] ?? row.name ?? row.outcome ?? row.seriousness ?? row.category), value: number(row[valueKey] ?? row.reports ?? row.value) })).filter((row) => row.value > 0);
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  if (!total) return <EmptyChart message="No outcome breakdown is available for this selection." />;
  const radius = 77, circumference = 2 * Math.PI * radius;
  let offset = 0;
  return <div className="chart-shell donut-chart" ref={tooltip.ref}>
    <div className="donut-graphic"><svg viewBox="0 0 220 220" role="img" aria-label={`Distribution across ${rows.length} categories, ${fmt(total)} total`}>
      <title>Category distribution. Focus a segment or its legend for counts and percentages.</title>
      <defs>{PALETTE.map((color, index) => <linearGradient key={color} id={`${donutId}-${index}`} x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor={color} /><stop offset="48%" stopColor={color} /><stop offset="75%" stopColor={`color-mix(in srgb, ${color} 70%, white)`} /><stop offset="100%" stopColor={color} /></linearGradient>)}</defs>
      <circle cx="110" cy="110" r="93" fill="none" stroke="#94c5ff" strokeOpacity=".11" strokeWidth=".7" />
      <circle cx="110" cy="110" r="60" fill="none" stroke="#9cbcff" strokeOpacity=".1" strokeWidth=".7" />
      <circle cx="110" cy="110" r={radius} fill="none" stroke="#e5e9de" strokeWidth="23" />
      {rows.map((row, index) => { const start = offset; offset += row.value / total * circumference; const color = PALETTE[index % PALETTE.length]; const slice = row.value / total * circumference; const interactions = tooltip.bind(row.name, [['Count', fmt(row.value)], ['Share', `${fmt(row.value / total * 100, 1)}%`]], color); return <circle key={`${row.name}-${index}`} cx="110" cy="110" r={radius} fill="none" stroke={color} strokeWidth={active === index ? 28 : 23} strokeDasharray={`${Math.max(.5, slice - (rows.length > 1 ? 3 : 0))} ${circumference}`} strokeDashoffset={-start} transform="rotate(-90 110 110)" className="donut-segment" tabIndex={0} role="graphics-symbol" aria-label={`${row.name}, ${fmt(row.value)}, ${fmt(row.value / total * 100, 1)} percent`} {...interactions} onPointerEnter={(event) => { setActive(index); interactions.onPointerEnter(event); }} onPointerLeave={() => { setActive(null); tooltip.hide(); }} onFocus={(event) => { setActive(index); interactions.onFocus(event); }} onBlur={() => { setActive(null); tooltip.hide(); }} />; })}
      <text x="110" y="106" textAnchor="middle" className="donut-total">{active == null ? fmt(total) : `${fmt(rows[active]?.value / total * 100, 1)}%`}</text>
      <text x="110" y="130" textAnchor="middle" className="donut-center-label">{active == null ? 'TOTAL' : 'OF TOTAL'}</text>
    </svg></div>
    <div className="donut-legend">{rows.map((row, index) => { const interactions = tooltip.bind(row.name, [['Count', fmt(row.value)], ['Share', `${fmt(row.value / total * 100, 1)}%`]], PALETTE[index % PALETTE.length]); return <div key={`${row.name}-${index}`} tabIndex={0} className={`donut-legend-row ${active === index ? 'is-active' : ''}`} {...interactions} onPointerEnter={(event) => { setActive(index); interactions.onPointerEnter(event); }} onPointerLeave={() => { setActive(null); tooltip.hide(); }} onFocus={(event) => { setActive(index); interactions.onFocus(event); }} onBlur={() => { setActive(null); tooltip.hide(); }}><i style={{ background: PALETTE[index % PALETTE.length] }} /><span>{row.name}</span><b>{fmt(row.value)}</b><small>{fmt(row.value / total * 100, 1)}%</small></div>; })}</div>
    {tooltip.tooltip}
  </div>;
}

function splitTreemap(rows, x, y, width, height) {
  if (!rows.length) return [];
  if (rows.length === 1) return [{ ...rows[0], x, y, width, height }];
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  let running = 0, split = 1;
  for (let index = 0; index < rows.length - 1; index += 1) {
    running += rows[index].value;
    split = index + 1;
    if (running >= total / 2) break;
  }
  const fraction = running / total;
  return width > height
    ? [...splitTreemap(rows.slice(0, split), x, y, width * fraction, height), ...splitTreemap(rows.slice(split), x + width * fraction, y, width * (1 - fraction), height)]
    : [...splitTreemap(rows.slice(0, split), x, y, width, height * fraction), ...splitTreemap(rows.slice(split), x, y + height * fraction, width, height * (1 - fraction))];
}

export function TreemapChart({ onSelect, selectedReaction='', data, labelKey = 'reaction', valueKey = 'count', recordLabel = 'Reports' }) {
  const tooltip = useTooltip();
  const treemapId = useId().replaceAll(':', '');
  const rows = list(data).map((row, index) => ({ ...row, name: label(row[labelKey] ?? row.label ?? row.name), value: number(row[valueKey] ?? row.reports ?? row.a), color: PALETTE[index % PALETTE.length] })).filter((row) => row.value > 0).sort((a, b) => b.value - a.value);
  if (!rows.length) return <EmptyChart message="No reaction volumes are available for a treemap." />;
  const W = Math.max(320, tooltip.width), H = W < 550 ? 390 : 350;
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  const cells = splitTreemap(rows, 0, 0, W, H);
  return <div className="chart-shell treemap-chart" ref={tooltip.ref}>
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Treemap of reaction counts from ${recordLabel.toLowerCase()}. Each reaction's area reflects its share of displayed mentions.`}><title>Reaction volume treemap. Focus a tile to inspect its full reaction name and count.</title><defs>{PALETTE.map((color, index) => <linearGradient key={color} id={`${treemapId}-${index}`} x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".23" /><stop offset="100%" stopColor={color} stopOpacity=".045" /></linearGradient>)}</defs>{cells.map((cell, index) => {
      const showLabel = cell.width > 75 && cell.height > 48;
      const available = Math.max(6, Math.floor((cell.width - 24) / 6.2));
      return <g key={`${cell.name}-${index}`} className="treemap-cell" tabIndex={0} role="graphics-symbol" {...reactionInteraction(onSelect,cell[labelKey]??cell.name,selectedReaction)} aria-label={`${cell.name}, ${fmt(cell.value)} ${recordLabel.toLowerCase()}, ${fmt(cell.value / total * 100, 1)} percent of displayed reactions`} {...tooltip.bind(cell.name, [[recordLabel, fmt(cell.value)], ['Share of displayed reactions', `${fmt(cell.value / total * 100, 1)}%`]], cell.color)}>
        <rect x={cell.x + 2} y={cell.y + 2} width={Math.max(0, cell.width - 4)} height={Math.max(0, cell.height - 4)} rx="2" fill={`url(#${treemapId}-${PALETTE.indexOf(cell.color)})`} stroke={cell.color} strokeOpacity=".33" />
        {showLabel && <><rect x={cell.x + 13} y={cell.y + 14} width="14" height="2" rx="1" fill={cell.color} /><text x={cell.x + 13} y={cell.y + 35} className="treemap-label">{short(cell.name, available)}</text>{cell.height > 69 && <text x={cell.x + 13} y={cell.y + 57} className="treemap-value">{fmt(cell.value)}<tspan className="treemap-share">　{fmt(cell.value / total * 100, 1)}%</tspan></text>}</>}
      </g>;
    })}</svg>
    <Legend items={[{ label: `${fmt(rows.length)} reactions displayed`, color: PALETTE[0] }]} note={`Tile area = ${recordLabel.toLowerCase()} count · focus tiles for detail`} />
    {tooltip.tooltip}
  </div>;
}

export function NetworkGraph(props) { return <ReactionNetwork {...props}/>; }

function normalizeCurves(input, kind) {
  const getPoints = (curve) => Array.isArray(curve) ? curve : curve?.points ?? curve?.data ?? curve?.[kind === 'roc' ? 'roc_curve' : 'pr_curve'] ?? [];
  let series;
  if (Array.isArray(input)) {
    if (input.some((item) => Array.isArray(item?.points) || Array.isArray(item?.data) || Array.isArray(item?.roc_curve) || Array.isArray(item?.pr_curve))) series = input.map((curve, index) => ({ name: curve.name ?? curve.label ?? curve.series ?? `Model ${index + 1}`, points: getPoints(curve) }));
    else { const groups = new Map(); input.forEach((point) => { const name = point.series ?? point.model ?? point.name ?? 'Model'; if (!groups.has(name)) groups.set(name, []); groups.get(name).push(point); }); series = [...groups].map(([name, points]) => ({ name, points })); }
  } else series = Object.entries(input ?? {}).map(([name, curve]) => ({ name: curve?.name ?? name, points: getPoints(curve) }));
  return series.map((curve) => ({ ...curve, points: curve.points.map((point) => ({ x: number(kind === 'roc' ? point.fpr ?? point.false_positive_rate ?? point.x : point.recall ?? point.x, NaN), y: number(kind === 'roc' ? point.tpr ?? point.true_positive_rate ?? point.y : point.precision ?? point.y, NaN) })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y) && point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1).sort((a, b) => a.x - b.x) })).filter((curve) => curve.points.length);
}

export function ModelCurves({ curves, kind = 'roc' }) {
  const tooltip = useTooltip();
  const normalizedKind = String(kind ?? 'roc').toLowerCase().startsWith('roc') ? 'roc' : 'pr';
  const series = normalizeCurves(curves, normalizedKind);
  const [hidden, setHidden] = useState([]);
  if (!series.length) return <EmptyChart message="Run a model evaluation to inspect holdout curves." />;
  const W = Math.max(320, tooltip.width), H = 330, L = 61, R = 20, T = 20, B = 57;
  const x = (value) => L + value * (W - L - R), y = (value) => H - B - value * (H - T - B);
  const ticks = [0, .25, .5, .75, 1].map((value) => ({ value, label: value.toFixed(2) }));
  return <div className="chart-shell model-curves" ref={tooltip.ref}>
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={normalizedKind === 'roc' ? 'Holdout receiver operating characteristic curves' : 'Holdout precision and recall curves'}><title>{normalizedKind === 'roc' ? 'False positive rate against true positive rate.' : 'Recall against precision.'} Focus points to inspect values.</title>
      <Grid width={W} height={H} left={L} right={R} top={T} bottom={B} xTicks={ticks} yTicks={ticks} x={x} y={y} xLabel={normalizedKind === 'roc' ? 'False positive rate' : 'Recall'} yLabel={normalizedKind === 'roc' ? 'True positive rate' : 'Precision'} />
      {normalizedKind === 'roc' && <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="#8095ac" strokeOpacity=".35" strokeDasharray="4 5" />}
      {series.map((curve, index) => !hidden.includes(curve.name) && <g key={`${curve.name}-${index}`}><path d={curve.points.map((point, pointIndex) => `${pointIndex ? 'L' : 'M'}${x(point.x)},${y(point.y)}`).join(' ')} fill="none" stroke={PALETTE[index % PALETTE.length]} strokeWidth="2.5" strokeLinejoin="round" />{curve.points.filter((_, pointIndex) => pointIndex % Math.max(1, Math.floor(curve.points.length / 45)) === 0).map((point, pointIndex) => <circle key={pointIndex} cx={x(point.x)} cy={y(point.y)} r={curve.points.length === 1 ? 4 : 7} fill={curve.points.length === 1 ? PALETTE[index % PALETTE.length] : 'transparent'} tabIndex={0} className="chart-focus-point" role="graphics-symbol" aria-label={`${curve.name}, ${normalizedKind === 'roc' ? 'false positive rate' : 'recall'} ${point.x.toFixed(3)}, ${normalizedKind === 'roc' ? 'true positive rate' : 'precision'} ${point.y.toFixed(3)}`} {...tooltip.bind(curve.name, [[normalizedKind === 'roc' ? 'False positive rate' : 'Recall', point.x.toFixed(3)], [normalizedKind === 'roc' ? 'True positive rate' : 'Precision', point.y.toFixed(3)]], PALETTE[index % PALETTE.length])} />)}</g>)}
    </svg>
    <div className="chart-legend model-curve-legend">{series.map((curve, index) => <button key={`${curve.name}-${index}`} className={`chart-legend-item ${hidden.includes(curve.name) ? 'is-hidden' : ''}`} aria-pressed={!hidden.includes(curve.name)} onClick={() => setHidden((previous) => previous.includes(curve.name) ? previous.filter((name) => name !== curve.name) : [...previous, curve.name])}><i style={{ background: PALETTE[index % PALETTE.length] }} />{curve.name}</button>)}<small>Click a model to toggle</small></div>
    {tooltip.tooltip}
  </div>;
}

const ratioText = (value) => !finite(value) ? 'Unavailable' : number(value) > 0 && (number(value) < .01 || number(value) >= 10000) ? Number(value).toExponential(1) : fmt(value, number(value) < .1 ? 3 : 2);
const proportionText = (value) => finite(value) && number(value) >= 0 && number(value) <= 1 ? `${fmt(number(value) * 100, 1)}%` : 'Unavailable';

export function SeverityPlot({ data }) {
  const tooltip = useTooltip();
  const [mode, setMode] = useState('forest');
  const [topN, setTopN] = useState(10);
  const rows = list(data).map((row) => {
    const rr = finite(row.RR ?? row.rr) && number(row.RR ?? row.rr) >= 0 ? number(row.RR ?? row.rr) : null;
    const low = finite(row.RR_low ?? row.rr_low) ? number(row.RR_low ?? row.rr_low) : null;
    const high = finite(row.RR_high ?? row.rr_high) ? number(row.RR_high ?? row.rr_high) : null;
    const validCI = rr !== null && low !== null && high !== null && low >= 0 && high >= low && rr >= low && rr <= high;
    return { ...row, name: label(row.reaction ?? row.label), rr, low, high, validCI };
  });
  const ratios = rows.filter((row) => row.rr !== null).sort((a, b) => b.rr - a.rr);
  const scatterRows = rows.filter((row) => finite(row.rate_drug) && finite(row.rate_bg) && number(row.rate_drug) >= 0 && number(row.rate_drug) <= 1 && number(row.rate_bg) >= 0 && number(row.rate_bg) <= 1);
  if (!ratios.length && !scatterRows.length) return <EmptyChart message="No seriousness reporting proportions are available for this cohort." />;
  const visible = ratios.slice(0, topN);
  const W = Math.max(320, tooltip.width);
  const L = W < 500 ? 111 : Math.min(225, W * .25), R = W < 500 ? 88 : 150;
  const T = 44, rowHeight = 47, H = T + visible.length * rowHeight + 59;
  const positive = visible.flatMap((row) => [row.rr, ...(row.validCI ? [row.low, row.high] : [])]).filter((value) => value > 0);
  const logMin = Math.floor(Math.log2(Math.min(.5, ...positive))) - .15;
  const logMax = Math.ceil(Math.log2(Math.max(2, ...positive))) + .15;
  const x = (value) => value <= 0 ? L + 2 : L + (Math.log2(value) - logMin) / (logMax - logMin) * (W - L - R);
  const firstPower = Math.ceil(logMin), lastPower = Math.floor(logMax);
  const stride = Math.max(1, Math.ceil((lastPower - firstPower) / 6));
  const powers = [...new Set([...Array.from({ length: Math.floor((lastPower - firstPower) / stride) + 1 }, (_, index) => firstPower + index * stride), 0])].sort((a, b) => a - b);
  const details = (row) => [
    ['Reports mentioning reaction', finite(row.reports) ? fmt(row.reports) : 'Unavailable'],
    ['Recorded serious', finite(row.serious) ? fmt(row.serious) : 'Unavailable'],
    ['Drug reports · serious proportion', proportionText(row.rate_drug)],
    ['Background · serious proportion', proportionText(row.rate_bg)],
    ['Relative reporting proportion', ratioText(row.rr)],
    ['95% confidence interval', row.validCI ? `${ratioText(row.low)} – ${ratioText(row.high)}` : 'Unavailable / inconsistent'],
  ];
  const intervalColor = (row) => row.validCI && row.low > 1 ? PALETTE[1] : row.validCI && row.high < 1 ? PALETTE[2] : PALETTE[0];
  const zeroBoundary = visible.some((row) => row.rr === 0 || (row.validCI && row.low === 0));
  const unavailableCI = visible.filter((row) => !row.validCI).length;
  const S = 355, SL = 67, SR = 25, ST = 22, SB = 59;
  const sx = (value) => SL + number(value) * (W - SL - SR), sy = (value) => S - SB - number(value) * (S - ST - SB);
  const ticks = [0, .25, .5, .75, 1].map((value) => ({ value, label: `${value * 100}%` }));
  const maxReports = Math.max(1, ...scatterRows.map((row) => number(row.reports)));
  return <div ref={tooltip.ref} className="chart-shell severity-plot">
    <div className="chart-controls"><div className="chart-segmented" aria-label="Seriousness reporting visualization">{[['forest', 'Relative proportion + CI'], ['scatter', 'Proportion comparison']].map(([value, text]) => <button key={value} className={mode === value ? 'is-active' : ''} aria-pressed={mode === value} onClick={() => { setMode(value); tooltip.hide(); }}>{text}</button>)}</div>{mode === 'forest' && <label className="chart-density-label severity-top-label">Reactions<select aria-label="Number of seriousness reporting proportions" value={topN} onChange={(event) => { setTopN(Number(event.target.value)); tooltip.hide(); }}><option value="10">Top 10</option><option value="20">Top 20</option><option value={Math.max(21, ratios.length)}>All · {ratios.length}</option></select></label>}</div>
    {mode === 'forest' ? visible.length ? <>
      <svg className="chart-svg severity-forest" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Relative seriousness reporting proportion forest plot with 95 percent confidence intervals for ${visible.length} reactions, sorted by decreasing ratio. A ratio of 1 indicates equal recorded proportions.`}>
        <title>Relative seriousness reporting proportion on a logarithmic axis. Focus a reaction row to inspect the estimate, interval and underlying counts.</title>
        <text x="0" y="15" className="severity-column-label">REACTION</text><text x={W - R + 12} y="15" className="severity-column-label">RATIO · 95% CI</text>
        {powers.map((power) => <g key={power} className="chart-grid"><line x1={x(2 ** power)} x2={x(2 ** power)} y1="27" y2={H - 53} strokeDasharray={power === 0 ? '4 4' : undefined} style={{ strokeOpacity: power === 0 ? .5 : .1, stroke: power === 0 ? '#becfe1' : undefined }} /><text x={x(2 ** power)} y={H - 32} textAnchor="middle">{ratioText(2 ** power)}</text></g>)}
        {visible.map((row, index) => { const cy = T + index * rowHeight + 5; const color = intervalColor(row); const labelLength = Math.max(8, Math.floor((L - 14) / 6)); return <g key={`${row.name}-${index}`} className="severity-forest-row" tabIndex={0} role="graphics-symbol" aria-label={`${row.name}, relative seriousness reporting proportion ${ratioText(row.rr)}, ${row.validCI ? `95 percent confidence interval ${ratioText(row.low)} to ${ratioText(row.high)}` : 'confidence interval unavailable'}`} {...tooltip.bind(row.name, details(row), color)}>
          <rect className="severity-row-hit" x="0" y={cy - 20} width={W} height={rowHeight - 1} fill="transparent" rx="5" />
          <line x1="0" x2={W} y1={cy + 26} y2={cy + 26} stroke="#98b6ce" strokeOpacity=".06" />
          <text x="0" y={cy + 3} className="severity-reaction-label">{short(row.name, labelLength)}</text>
          {row.validCI && <g stroke={color} strokeWidth="1.7"><line x1={x(row.low)} x2={x(row.high)} y1={cy} y2={cy} strokeOpacity=".8" />{row.low > 0 ? <line x1={x(row.low)} x2={x(row.low)} y1={cy - 4} y2={cy + 4} /> : <path d={`M${L + 7},${cy - 4}L${L + 2},${cy}L${L + 7},${cy + 4}`} fill="none" />}<line x1={x(row.high)} x2={x(row.high)} y1={cy - 4} y2={cy + 4} /></g>}
          {row.rr > 0 ? <rect x={x(row.rr) - 4} y={cy - 4} width="8" height="8" rx="1.6" fill={color} stroke="#dff4fc" strokeOpacity=".5" /> : <path d={`M${L + 2},${cy - 5}l5,5 -5,5 -5,-5z`} fill="#f7f8f2" stroke={color} strokeWidth="1.5" />}
          <text x={W - R + 12} y={cy - 2} className="severity-estimate">{ratioText(row.rr)}{row.rr === 0 ? '*' : ''}</text><text x={W - R + 12} y={cy + 13} className="severity-interval">{row.validCI ? `${ratioText(row.low)}–${ratioText(row.high)}` : 'CI unavailable'}</text>
        </g>; })}
        <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" className="severity-axis-label">{W < 500 ? 'Relative proportion · log scale' : 'Relative seriousness reporting proportion · log scale'}</text>
      </svg>
      <Legend items={[{ label: 'CI above 1', color: PALETTE[1] }, { label: 'CI below 1', color: PALETTE[2] }, { label: 'CI includes 1 / unavailable', color: PALETTE[0] }]} note={`Top ${visible.length} of ${ratios.length} finite ratios`} />
      {(zeroBoundary || unavailableCI > 0 || rows.length > ratios.length) && <p className="chart-method-note">{zeroBoundary && 'Zero estimates and zero lower bounds appear at the left boundary; zero has no logarithmic position. '}{unavailableCI > 0 && `${unavailableCI} displayed ${unavailableCI === 1 ? 'interval is' : 'intervals are'} unavailable or inconsistent; only the estimate is shown. `}{rows.length > ratios.length && `${rows.length - ratios.length} reactions have no finite ratio; inspect their available counts in the table.`}</p>}
    </> : <EmptyChart message="No finite relative seriousness reporting proportions are available. Try the proportion comparison view." /> : scatterRows.length ? <>
      <svg className="chart-svg" viewBox={`0 0 ${W} ${S}`} role="img" aria-label="Recorded serious proportion among selected drug reports compared with the corresponding background reports. The diagonal marks equal proportions."><title>Proportion comparison. Each point is a reaction; point size reflects its report count. Focus points for counts and uncertainty.</title>
        <Grid width={W} height={S} left={SL} right={SR} top={ST} bottom={SB} xTicks={ticks} yTicks={ticks} x={sx} y={sy} xLabel="Background reports · serious proportion" yLabel="Drug reports · serious proportion" />
        <line x1={sx(0)} x2={sx(1)} y1={sy(0)} y2={sy(1)} stroke="#b3c5d6" strokeOpacity=".4" strokeDasharray="5 5" />
        {scatterRows.map((row, index) => { const color = number(row.rate_drug) > number(row.rate_bg) ? PALETTE[1] : PALETTE[0]; return <circle key={`${row.name}-${index}`} cx={sx(row.rate_bg)} cy={sy(row.rate_drug)} r={4 + Math.sqrt(number(row.reports) / maxReports) * 7} fill={color} fillOpacity=".5" stroke={color} strokeWidth="1" className="chart-point" tabIndex={0} role="graphics-symbol" aria-label={`${row.name}, drug reports ${proportionText(row.rate_drug)} serious, background reports ${proportionText(row.rate_bg)} serious, ${fmt(row.reports)} reports`} {...tooltip.bind(row.name, details(row), color)} />; })}
      </svg>
      <Legend items={[{ label: 'Drug proportion above background', color: PALETTE[1] }, { label: 'Drug proportion at / below background', color: PALETTE[0] }]} note={`${scatterRows.length} reactions · point size = reports`} />
      {rows.length > scatterRows.length && <p className="chart-method-note">{rows.length - scatterRows.length} reactions lack valid proportions for one or both groups and are omitted from this view.</p>}
    </> : <EmptyChart message="Drug and background seriousness proportions are unavailable for this selection." />}
  </div>;
}
