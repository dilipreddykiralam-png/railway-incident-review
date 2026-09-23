"""Portable evidence report; embeds selected stored samples and escapes descriptions."""
import html,json
from .before_after import usable_samples
from .metrics import display_metrics

def render_case_report(record):
    esc=lambda value:html.escape(str(value))
    parts=['<!doctype html><html><meta charset="utf-8"><title>Railway case review</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px}section{display:flex;gap:24px}figure{flex:1;margin:0}img{width:100%}pre{white-space:pre-wrap}small{color:#555}</style><h1>Railway case review</h1>', '<p>Record: '+esc(record['id'])+'</p>']
    pair=record.get('before_after')
    if pair:
        samples={s['sample_number']:s for s in usable_samples(record)}
        parts.append('<section>')
        for key in ['earlier','later']:
            item=pair[key];sample=samples.get(item['sample_number'])
            if sample:
                parts.append('<figure><h2>'+esc(item['label'])+'</h2><img src="data:image/jpeg;base64,'+sample['analyzed_image_jpeg_base64']+'"><figcaption>Sample '+esc(item['sample_number'])+' · '+esc(item['timestamp_seconds'])+' s</figcaption></figure>')
        parts.append('</section><p>'+esc(pair['limitations'])+'</p>')
    parts.append('<h2>Displayed assessment</h2><pre>'+esc(json.dumps(display_metrics(record),indent=2))+'</pre>')
    parts.append('<h2>Model result (requires human verification)</h2><pre>'+esc(json.dumps(record.get('prediction'),indent=2))+'</pre>')
    if record.get('asset_verification'):
        parts.append('<h2>Human-reviewed assets</h2><pre>'+esc(json.dumps(record['asset_verification'],indent=2))+'</pre>')
    parts.append('<small>Sampled evidence is not full-video coverage. Model confidence is uncalibrated. Source record preserves raw model responses, image hashes and review history.</small></html>')
    return ''.join(parts)
