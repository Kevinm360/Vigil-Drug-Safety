export const DEFAULT_COHORT = Object.freeze({
  mode: 'live', drug: 'METFORMIN', compare: '',
  start: '2024-01-02', end: '2025-09-15', age: 'All', sex: '', reporters: '',
});

const STORAGE_KEY = 'vigil.applied-cohort.v2';
const LEGACY_STORAGE_KEY = 'vigil.applied-cohort.v1';
const SEXES = ['Male', 'Female', 'Unknown'];
const REPORTERS = ['Physician', 'Pharmacist', 'Other HCP', 'Lawyer', 'Consumer'];
const AGES = ['All', '0–11', '12–17', '18–44', '45–64', '65+'];
const rows = value => Array.isArray(value) ? value : [];
const validDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
const validDrug = value => typeof value === 'string' && value.length <= 120 && /^[\w\s.+'(),/\-]*$/.test(value);
const validSelection = (value, choices) => typeof value === 'string'
  && (value === '' || value.split(',').every(item => choices.includes(item)));

// Persist only the applied cohort, never report rows, narratives, or model outputs.
export function loadCohort(storage) {
  try {
    const current = storage.getItem(STORAGE_KEY);
    const migrating = current == null;
    const value = JSON.parse(current ?? storage.getItem(LEGACY_STORAGE_KEY));
    if (!value || !['reference', 'live'].includes(value.mode)
      || !validDrug(value.drug) || !value.drug.trim() || !validDrug(value.compare)
      || !validDate(value.start) || !validDate(value.end) || value.start > value.end
      || !AGES.includes(value.age) || !validSelection(value.sex, SEXES)
      || !validSelection(value.reporters, REPORTERS)) return { ...DEFAULT_COHORT };
    return { ...Object.fromEntries(Object.keys(DEFAULT_COHORT).map(key => [key, value[key]])),
      mode: migrating ? 'live' : value.mode };
  } catch {
    return { ...DEFAULT_COHORT };
  }
}

export function saveCohort(storage, cohort) {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(
      Object.keys(DEFAULT_COHORT).map(key => [key, cohort[key]]),
    )));
  } catch { /* The app still works when browser storage is unavailable. */ }
}

export function exportForView(view, data, { reference = false, narratives, model, signals } = {}) {
  if (!data) return { name: view, label: 'Export data', rows: [] };
  const graph = data.graph || {};
  const nodeById = new Map(rows(graph.nodes).map(node => [String(node.id), node]));
  const choices = {
    overview: ['weekly-volume', 'Export weekly data', rows(data.timeseries)],
    reactions: ['reactions', 'Export reactions', rows(data.reactions)],
    reports: ['records', 'Export records', rows(reference ? data.narratives?.records : data.reports)],
    signals: ['signals', 'Export signals', rows(signals ?? data.signals)],
    severity: ['severity', 'Export severity', rows(data.severity?.reactions)],
    narratives: ['annotated-narratives', 'Export narratives', rows((narratives ?? data.narratives)?.records)],
    models: model
      ? ['model-comparison', 'Export model results', rows((model.evaluation || model).comparison)]
      : ['feature-audit', 'Export feature audit', rows(data.model?.audit)],
    network: ['network-connections', 'Export connections', rows(graph.links).map(link => {
      const source = nodeById.get(String(link.source?.id ?? link.source));
      const target = nodeById.get(String(link.target?.id ?? link.target));
      return {
        drug: source?.label ?? link.source, reaction: target?.label ?? link.target,
        co_occurrences: link.value, primary_drug_count: target?.a ?? null,
        primary_drug_prr: target?.prr ?? null, primary_drug_ror: target?.ror ?? null,
      };
    })],
  };
  const [name, label, values] = choices[view] || [view, 'Export data', []];
  return { name, label, rows: values };
}
