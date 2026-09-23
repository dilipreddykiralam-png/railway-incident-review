import argparse
import csv
import json
from pathlib import Path
from .backends import get_backend
from .pipeline import run

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',required=True); p.add_argument('--output',required=True)
    p.add_argument('--backend',choices=['demo','vlm'],default='vlm')
    args=p.parse_args()
    manifest=Path(args.manifest)
    with manifest.open(newline='') as f: rows=list(csv.DictReader(f))
    ids=[r['image_id'] for r in rows]
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate image_id in manifest')
    backend=get_backend(args.backend)
    # Exclusive creation avoids silently overwriting an experiment.
    with open(args.output,'x') as out:
        for row in rows:
            try: record=run((manifest.parent/row['image_path']).read_bytes(),backend)
            except Exception as exc:
                record=dict(prediction=None,error=str(exc),backend=backend.name,model=backend.model,human_verification={'status':'pending'})
            record['image_id']=row['image_id']
            out.write(json.dumps(record)+'\n'); out.flush()
            print(row['image_id'], 'failed' if record.get('error') else 'ok')
if __name__=='__main__': main()
