"""Evaluate immutable machine predictions, never reviewer-corrected labels."""
import argparse
import csv
import json
from pathlib import Path
from .schema import LABELS

FIELDS = list(LABELS)
def mean(values): return sum(values)/len(values) if values else None

def evaluate(truth, records, threshold=0.7):
    ids = [r['image_id'] for r in truth]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate ground-truth image_id')
    pred = {}
    for r in records:
        if r.get('media_type') == 'video':
            raise ValueError('Video summaries require separate video-level evaluation; score frame records separately.')
        if r['image_id'] in pred: raise ValueError('Duplicate prediction image_id')
        pred[r['image_id']] = r
    if set(pred) - set(ids): raise ValueError('Predictions include IDs absent from ground truth')
    for row in truth:
        for f in FIELDS:
            if row[f] not in LABELS[f]: raise ValueError(f'Invalid ground truth {f}: {row[f]}')
    pairs = [(t,pred.get(t['image_id'],{}).get('prediction')) for t in truth]
    valid = [(t,p) for t,p in pairs if p is not None]
    def tuple_scope(t):
        record=pred[t['image_id']]
        return record.get('confidence_scope','whole_tuple')=='whole_tuple' and not record.get('response_contract','').startswith('scene_assessment')
    confidence_eligible=[(t,p) for t,p in valid if tuple_scope(t)]
    correct = [all(t[f]==p[f] for f in FIELDS) for t,p in confidence_eligible]
    scores = [p['confidence'] for t,p in confidence_eligible]
    confusion = {t:{p:0 for p in LABELS['incident']+['failure']} for t in LABELS['incident']}
    for t,p in pairs: confusion[t['incident']][p['incident'] if p else 'failure'] += 1
    f1s = []
    per_class = {}
    for label in ['incident','non_incident']:
        tp = confusion[label][label]
        fp = sum(confusion[t][label] for t in confusion if t != label)
        fn = sum(v for k,v in confusion[label].items() if k != label)
        precision = tp/(tp+fp) if tp+fp else 0.0
        recall = tp/(tp+fn) if tp+fn else None
        f1 = 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
        per_class[label] = dict(precision=precision, recall=recall, f1=f1, support=tp+fn)
        if f1 is not None: f1s.append(f1)
    bins = []
    for i in range(10):
        indexes = [j for j,s in enumerate(scores) if min(int(s*10),9)==i]
        if indexes:
            bins.append(dict(lower=i/10, upper=(i+1)/10, n=len(indexes), confidence=mean([scores[j] for j in indexes]), accuracy=mean([correct[j] for j in indexes])))
    accepted = [j for j,(t,p) in enumerate(confidence_eligible) if p['confidence']>=threshold and p['incident']!='uncertain' and all(p[f]!='unknown' for f in FIELDS)]
    ordinal = ['none','minor','moderate','severe','critical']
    severity = [(ordinal.index(t['severity']),ordinal.index(p['severity'])) for t,p in valid if t['severity'] in ordinal and p['severity'] in ordinal]
    kappa = None
    if severity:
        obs = mean([(a-b)**2 for a,b in severity])
        expected = mean([(a-b)**2 for a,_ in severity for _,b in severity])
        if expected: kappa = 1-obs/expected
    reviewed = [r for r in records if r.get('human_verification',{}).get('status') in ['confirmed','corrected']]
    return dict(n=len(truth), valid_predictions=len(valid), failures_or_missing=len(truth)-len(valid),
        demo_present=any(r.get('backend')=='demo' for r in records),
        field_accuracy_all_images={f:mean([p is not None and t[f]==p[f] for t,p in pairs]) for f in FIELDS},
        exact_match_all_images=mean([p is not None and all(t[f]==p[f] for f in FIELDS) for t,p in pairs]),
        incident_confusion=confusion, incident_per_class=per_class, incident_macro_f1=mean(f1s),
        abstention_rate=mean([p is not None and p['incident']=='uncertain' for t,p in pairs]),
        severity_ordinal_n=len(severity), severity_quadratic_kappa=kappa,
        whole_tuple_brier=mean([(s-c)**2 for s,c in zip(scores,correct)]),
        whole_tuple_ece=sum(b['n']*abs(b['confidence']-b['accuracy']) for b in bins)/len(confidence_eligible) if confidence_eligible else None,
        whole_tuple_confidence_n=len(confidence_eligible), confidence_excluded_wrong_scope=len(valid)-len(confidence_eligible),
        confidence_bins=bins, selective_threshold=threshold, selective_coverage=len(accepted)/len(truth) if truth else None,
        selective_exact_match=mean([correct[j] for j in accepted]),
        mean_latency_seconds=mean([r['latency_seconds'] for r in records if 'latency_seconds' in r]),
        reviewed_n=len(reviewed), correction_rate_among_reviewed=mean([r['human_verification']['status']=='corrected' for r in reviewed]))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--truth',required=True); parser.add_argument('--predictions',required=True)
    parser.add_argument('--output',default='metrics.json'); parser.add_argument('--threshold',type=float,default=0.7)
    args=parser.parse_args()
    if not 0<=args.threshold<=1: parser.error('threshold must be 0..1')
    with open(args.truth,newline='') as f: truth=list(csv.DictReader(f))
    from .schema import Prediction
    records=[json.loads(line) for line in Path(args.predictions).read_text().splitlines() if line.strip()]
    for r in records:
        if r.get('prediction') is not None: Prediction.model_validate(r['prediction'])
    result=evaluate(truth,records,args.threshold)
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2,allow_nan=False))
if __name__=='__main__': main()
