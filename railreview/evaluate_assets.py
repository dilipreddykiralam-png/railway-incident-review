"""Strict multiset scoring of independently labeled visible-damage findings."""
import argparse,json
from collections import Counter
from pathlib import Path

def score(truth, predictions):
    ids=[r['image_id'] for r in truth]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate truth IDs')
    lookup={r['image_id']:r for r in predictions}
    if len(lookup)!=len(predictions):raise ValueError('Duplicate prediction IDs')
    if set(lookup)-set(ids):raise ValueError('Unexpected prediction IDs')
    if any(r.get('annotation_status')!='verified' for r in truth):raise ValueError('Truth must be independently verified')
    result={'images':len(truth),'failures_or_missing':sum(not lookup.get(i,{}).get('prediction') for i in ids),'scope':'visible_damage only; exact multiset matching; not localization or tracking'}
    for name,keys in [('asset',['asset']),('asset_damage',['asset','damage_type']),('asset_component_damage_severity',['asset','component','damage_type','severity'])]:
        tp=fp=fn=0
        for row in truth:
            expected=Counter(tuple(f[k] for k in keys) for f in row['findings'] if f['damage_status']=='visible_damage')
            predicted=Counter(tuple(f[k] for k in keys) for f in (lookup.get(row['image_id'],{}).get('prediction') or {}).get('findings',[]) if f['damage_status']=='visible_damage')
            tp+=sum((expected&predicted).values());fp+=sum((predicted-expected).values());fn+=sum((expected-predicted).values())
        result[name]=dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--truth',required=True);p.add_argument('--predictions',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    read=lambda path:[json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]
    result=score(read(a.truth),read(a.predictions));Path(a.output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
