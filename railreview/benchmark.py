"""Run identical manifest images through named models without exposing labels."""
import argparse,csv,json
from pathlib import Path
from .backends import VLMBackend
from .pipeline import run

def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--models',nargs='+',default=['qwen2.5vl:7b']);args=p.parse_args()
 manifest=Path(args.manifest)
 with manifest.open() as f:rows=list(csv.DictReader(f))
 if len({r['image_id'] for r in rows})!=len(rows):raise ValueError('Duplicate image IDs')
 out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
 for model in args.models:
  backend=VLMBackend(model)
  with (out/(model.replace(':','-').replace('/','-')+'.jsonl')).open('x') as f:
   for row in rows:
    try:record=run((manifest.parent/row['image_path']).read_bytes(),backend)
    except Exception as exc:record=dict(prediction=None,error=str(exc),model=model)
    record['image_id']=row['image_id'];f.write(json.dumps(record)+'\n');f.flush()
    print(model,row['image_id'],'failed' if record.get('error') else 'ok',flush=True)
if __name__=='__main__':main()
