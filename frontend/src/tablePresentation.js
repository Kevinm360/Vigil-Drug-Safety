const LABELS={prr:'PRR',ror:'ROR',chi2:'χ²',roc_auc:'ROC AUC',pr_auc:'PR AUC',auc:'AUC',f1:'F1',macro_f1:'Macro F1',micro_f1:'Micro F1',tfidf:'TF-IDF',safetyreportid:'Report ID'};
export function columnLabel(key){
  return LABELS[key]||String(key).replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
}
export function tableValue(value,key=''){
  if(value==null||value===''||typeof value==='number'&&!Number.isFinite(value))return '—';
  if(typeof value!=='number')return Array.isArray(value)?value.join(', '):String(value);
  if(/(^|_)(id|year)$/.test(key))return String(value);
  const metric=/(auc|accuracy|precision|recall|f1|coefficient|importance|delta|share|proportion)/i.test(key);
  const ratio=/^(prr|ror|chi2|z)(_|$)/i.test(key);
  const digits=metric?3:ratio?2:Number.isInteger(value)?0:4;
  return new Intl.NumberFormat('en-US',{minimumFractionDigits:metric||ratio?digits:0,maximumFractionDigits:digits}).format(value);
}
