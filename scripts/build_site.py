"""Build a static showcase from only the three licensed public examples."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / '_site'
out.mkdir(exist_ok=True)
shutil.copy(ROOT / 'site/index.html', out / 'index.html')
shutil.copytree(ROOT / 'examples/images', out / 'images', dirs_exist_ok=True)
cases = []
for source in json.loads((ROOT / 'examples/sources.json').read_text()):
    record = json.loads((ROOT / 'examples/outputs' / (source['case_id'] + '.json')).read_text())
    cases.append({'source': source, 'record': record})
(out / 'cases.json').write_text(json.dumps(cases))
