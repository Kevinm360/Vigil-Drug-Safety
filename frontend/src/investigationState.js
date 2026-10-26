import {previousPeriod} from './periodState.js';
export const normalizeReaction = value => String(value || '').trim().toUpperCase();

export function snapshotKey({cohort, view, reaction, periods}) {
  const baseline=periods?.baseline_start?periods:previousPeriod(cohort);
  return JSON.stringify([['mode','drug','compare','start','end','age','sex','reporters'].map(key => cohort[key]), view, normalizeReaction(reaction),baseline.baseline_start,baseline.baseline_end]);
}

export function reactionChoices(data) {
  return [...new Set([...(data?.reactions || []).map(row => row.reaction), ...(data?.graph?.nodes || []).filter(row => row.type === 'reaction').map(row => row.label)].filter(Boolean).map(normalizeReaction))].sort();
}
