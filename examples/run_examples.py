"""Run the three licensed examples with local Qwen2.5-VL 7B.

Run from the repository root: python examples/run_examples.py
Every response is retained, including validation failures. Existing results are
never overwritten; the default output directory is a new timestamped run.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from railreview.backends import VLMBackend
from railreview.pipeline import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = args.output_dir or ROOT / 'runs' / ('examples-' + stamp)
    output.mkdir(parents=True, exist_ok=True)
    cases = json.loads((ROOT / 'examples/sources.json').read_text())
    targets = [output / (case['case_id'] + '.json') for case in cases]
    if any(path.exists() for path in targets + [output / 'run_metadata.json']):
        parser.error('Output files already exist. Choose a new output directory.')

    # Explicit model and native local endpoint prevent an accidental demo/API run.
    os.environ['VLM_BASE_URL'] = 'http://127.0.0.1:11434'
    os.environ['VLM_API_STYLE'] = 'ollama'
    backend = VLMBackend(model='qwen2.5vl:7b')
    with urlopen('http://127.0.0.1:11434/api/tags', timeout=10) as response:
        models = json.load(response)['models']
    model = next(m for m in models if m['name'] == backend.model)
    with urlopen('http://127.0.0.1:11434/api/version', timeout=10) as response:
        version = json.load(response)['version']
    hardware = {'os': platform.system(), 'os_release': platform.release(),
                'architecture': platform.machine(), 'python': platform.python_version()}
    if platform.system() == 'Darwin':
        for name, key in [('cpu', 'machdep.cpu.brand_string'), ('memory_bytes', 'hw.memsize')]:
            result = subprocess.run(['sysctl', '-n', key], capture_output=True, text=True)
            if result.returncode == 0:
                hardware[name] = result.stdout.strip()
    metadata = {
        'purpose': 'Unlabelled smoke examples; not an accuracy benchmark',
        'started_at': datetime.now(timezone.utc).isoformat(),
        'model': backend.model, 'ollama_version': version,
        'model_digest': model['digest'], 'model_details': model['details'],
        'hardware': hardware,
        'libraries': {name: importlib.metadata.version(name) for name in ['pydantic', 'Pillow']},
        'case_order': [case['case_id'] for case in cases],
        'human_verification': 'Pending for all cases; no reference labels',
        'retry_policy': 'At most one validation-repair request per image; all attempts saved',
        'latency_note': 'End-to-end seconds; includes preprocessing, model calls and any repair. First case may include model loading.',
    }
    (output / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    for case, target in zip(cases, targets):
        record = run((ROOT / 'examples' / case['image_path']).read_bytes(), backend)
        record['case_id'] = case['case_id']
        record['image_path'] = 'examples/' + case['image_path']
        record['example_role'] = 'unlabelled_smoke_example'
        target.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
        print(json.dumps({'case_id': case['case_id'], 'error': record['error'],
                          'latency_seconds': record['latency_seconds'],
                          'classification': (record['prediction'] or {}).get('incident'),
                          'attempts': len(record['attempts'])}), flush=True)


if __name__ == '__main__':
    main()
