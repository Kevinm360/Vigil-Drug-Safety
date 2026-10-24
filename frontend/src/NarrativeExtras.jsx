import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ArrowDownToLine, Database, Info, LoaderCircle, Search, ShieldCheck } from 'lucide-react';
import './NarrativeExtras.css';

const list = value => Array.isArray(value) ? value : [];
const format = value => new Intl.NumberFormat('en-US').format(value);

export function DeviceNarrativeFetch({ start, end, onResult }) {
  const id = useId();
  const [term, setTerm] = useState('');
  const [limit, setLimit] = useState(100);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const controller = useRef(null);
  const requestId = useRef(0);

  useEffect(() => {
    requestId.current += 1;
    controller.current?.abort();
    setBusy(false);
    setError('');
    setStatus('');
    return () => {
      requestId.current += 1;
      controller.current?.abort();
    };
  }, [start, end]);

  async function fetchNarratives(event) {
    event.preventDefault();
    if (busy) return;
    if (!start || !end || start > end) {
      setError('Apply a valid start and end date in the cohort filters first.');
      return;
    }
    const currentRequest = ++requestId.current;
    controller.current?.abort();
    const requestController = new AbortController();
    controller.current = requestController;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; requestController.abort(); }, 120000);
    setBusy(true);
    setError('');
    setStatus('');
    try {
      const response = await fetch('/api/narratives/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ term: term.trim(), start, end, limit: Number(limit) }),
        signal: requestController.signal,
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(result?.error?.message || result?.error || result?.message || `FDA narratives could not be fetched (${response.status}). Try again.`);
      }
      if (!result || typeof result !== 'object') throw new Error('The narrative service returned an unreadable response. Try again.');
      if (currentRequest !== requestId.current) return;
      const count = Number(result.total ?? list(result.records).length);
      setStatus(count ? `${format(count)} device narratives analyzed. The results below now show this FDA MAUDE sample.` : 'No device narratives matched this search. Try a broader device name or date range.');
      onResult?.(result);
    } catch (failure) {
      if (currentRequest === requestId.current) {
        if (timedOut) setError('The FDA narrative request timed out. Try a smaller sample or a shorter date range.');
        else if (failure.name !== 'AbortError') setError(failure.message || 'The FDA narrative service is unavailable. Try again.');
      }
    } finally {
      clearTimeout(timeout);
      if (currentRequest === requestId.current) setBusy(false);
    }
  }

  return <section className="panel device-narrative-panel" aria-labelledby={`${id}-title`}>
    <div className="panel-heading">
      <div><span className="eyebrow">ANOTHER SOURCE, MORE CONTEXT</span><h2 id={`${id}-title`}>Explore FDA device narratives</h2><p>Fetch and analyze real medical-device event text from MAUDE.</p></div>
      <Database size={19} className="mint" aria-hidden="true"/>
    </div>
    <div className="callout device-source-note"><Info size={17} aria-hidden="true"/><p><strong>Device reports are a separate source.</strong> FAERS drug case narratives are not available through openFDA. These results describe medical devices and do not belong to your selected drug cohort.</p></div>
    <form onSubmit={fetchNarratives} aria-busy={busy}>
      <div className="device-fetch-fields">
        <label className="form-field" htmlFor={`${id}-term`}>Device name <span className="device-optional">optional</span><div className="device-term-input"><Search size={15} aria-hidden="true"/><input id={`${id}-term`} value={term} onChange={event => setTerm(event.target.value)} maxLength={120} placeholder="e.g. insulin pump or pacemaker" disabled={busy}/></div></label>
        <label className="form-field" htmlFor={`${id}-limit`}>Sample size<select id={`${id}-limit`} value={limit} onChange={event => setLimit(Number(event.target.value))} disabled={busy}>{[25, 50, 100, 250, 500].map(size => <option key={size} value={size}>Up to {size} reports</option>)}</select></label>
        <button className="btn primary device-fetch-submit" type="submit" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin" aria-hidden="true"/> : <ArrowDownToLine size={16} aria-hidden="true"/>}{busy ? 'Fetching narratives…' : 'Fetch FDA sample'}</button>
      </div>
      <p className="device-fetch-dates">Receipt dates <strong>{start || 'Set start date'} <span aria-hidden="true">→</span> {end || 'Set end date'}</strong><span>Uses the date window in your cohort filters. An empty device name searches all devices.</span></p>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="device-fetch-status" role="status" aria-live="polite">{busy ? 'Contacting openFDA and analyzing returned text. This can take a moment.' : status}</div>
    </form>
  </section>;
}

function probabilityPairs(selected) {
  const probabilities = list(selected?.held_out_probabilities ?? selected?.y_prob ?? selected?.probabilities ?? selected?.y_proba);
  const labels = list(selected?.held_out_labels ?? selected?.y_true);
  if (probabilities.length && probabilities.length === labels.length) {
    return probabilities.map((probability, index) => ({ probability, label: labels[index] }));
  }
  return list(selected?.probability_distribution).map(row => ({
    probability: row.predicted_probability,
    label: row.actual_class === 'Serious' ? 1 : row.actual_class === 'Non-serious' ? 0 : null,
  }));
}

export function ModelSupplement({ evaluation, selected }) {
  const id = useId().replaceAll(':', '');
  const [active, setActive] = useState(null);
  const distribution = useMemo(() => {
    const bins = Array.from({ length: 10 }, (_, index) => ({ low: index / 10, high: (index + 1) / 10, counts: [0, 0] }));
    const totals = [0, 0];
    for (const pair of probabilityPairs(selected)) {
      if (pair.probability == null || pair.label == null) continue;
      const probability = Number(pair.probability), label = Number(pair.label);
      if (!Number.isFinite(probability) || probability < 0 || probability > 1 || ![0, 1].includes(label)) continue;
      bins[Math.min(9, Math.floor(probability * 10))].counts[label] += 1;
      totals[label] += 1;
    }
    return { bins, totals, count: totals[0] + totals[1] };
  }, [selected]);
  useEffect(() => setActive(null), [selected]);
  const colors = ['#477f79', '#8773a5'];
  const classes = ['Non-serious', 'Serious'];
  const plot = { x: 60, y: 18, width: 670, height: 204 };
  const maximum = Math.max(1, ...distribution.bins.flatMap(bin => bin.counts));
  const step = Math.max(1, Math.ceil(maximum / 4));
  const top = step * 4;
  const band = plot.width / 10;
  const split = evaluation?.split_description || '';
  const chronological = /chronological|older reports.*newer/i.test(split);
  const activeBin = active == null ? null : distribution.bins[active];

  return <section className="panel model-distribution-panel" aria-labelledby={`${id}-title`}>
    <div className="panel-heading"><div><span className="eyebrow">INSPECT THE SEPARATION</span><h2 id={`${id}-title`}>Held-out probability distribution</h2><p>How the selected model scores reports with each actual seriousness label.</p></div><span className="tag">{chronological ? 'Chronological holdout' : 'Held-out sample'}</span></div>
    {distribution.count ? <>
      <div className="model-distribution-legend">{classes.map((label, index) => <span key={label}><i style={{ background: colors[index] }}/><strong>Actual {label.toLowerCase()}</strong><small>{format(distribution.totals[index])} reports</small></span>)}</div>
      <div className="model-distribution-chart">
        <svg viewBox="0 0 760 280" role="img" aria-labelledby={`${id}-title ${id}-description`}>
          <desc id={`${id}-description`}>{format(distribution.count)} held-out reports in ten probability bins. Teal shows reports labeled non-serious; lavender shows reports labeled serious. Horizontal axis is the model's probability of the serious label, from zero to one. Vertical axis is the number of reports.</desc>
          {[0, 1, 2, 3, 4].map(index => { const y = plot.y + plot.height - index / 4 * plot.height; return <g key={index}><line x1={plot.x} x2={plot.x + plot.width} y1={y} y2={y} stroke="#afcbe3" strokeOpacity={index ? '.09' : '.2'}/><text x={plot.x - 12} y={y + 3} textAnchor="end" className="distribution-axis">{format(step * index)}</text></g>; })}
          <text transform={`translate(14 ${plot.y + plot.height / 2}) rotate(-90)`} textAnchor="middle" className="distribution-axis-title">Reports</text>
          {distribution.bins.map((bin, index) => <g key={index} tabIndex={0} role="img" aria-label={`Probability ${bin.low.toFixed(1)} to ${bin.high.toFixed(1)}: ${bin.counts[0]} non-serious reports, ${bin.counts[1]} serious reports.`} onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(index)} onBlur={() => setActive(null)} className="distribution-bin">
            <rect x={plot.x + index * band} y={plot.y} width={band} height={plot.height} fill={active === index ? '#d1e8f506' : 'transparent'}/>
            {bin.counts.map((count, label) => { const height = count / top * plot.height; return <rect key={label} x={plot.x + index * band + 7 + label * 25} y={plot.y + plot.height - height} width={22} height={height} rx={3} fill={colors[label]} fillOpacity={active == null || active === index ? '.78' : '.35'}/>; })}
          </g>)}
          {[0, 2, 4, 6, 8, 10].map(index => <text key={index} x={plot.x + index * band} y={244} textAnchor="middle" className="distribution-axis">{(index / 10).toFixed(1)}</text>)}
          <text x={plot.x + plot.width / 2} y={270} textAnchor="middle" className="distribution-axis-title">Model probability of a serious report</text>
        </svg>
      </div>
      <div className="distribution-inspection" role="status" aria-live="polite">{activeBin ? <><strong>{activeBin.low.toFixed(1)}–{activeBin.high.toFixed(1)}</strong><span>{format(activeBin.counts[0])} non-serious</span><span>{format(activeBin.counts[1])} serious</span></> : <span>Hover or focus a bin to inspect report counts.</span>}</div>
      {split && <p className="distribution-split"><ShieldCheck size={14} aria-hidden="true"/><span>{split}</span></p>}
      <p className="field-hint">Distributions use actual held-out labels and predictions for the selected model and feature set. Overlap reveals uncertainty; these scores describe submitted reports, not individual patient risk.</p>
    </> : <div className="distribution-empty"><Info size={20} aria-hidden="true"/><p>Held-out probabilities are unavailable for this selection. Run model evaluation to inspect the distribution.</p></div>}
  </section>;
}
