import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from PIL import Image
from railreview.backends import DemoBackend, VLMBackend
from railreview.pipeline import run, verify, prepare_image
from railreview.schema import parse_prediction
from railreview.evaluate import evaluate

def picture():
    out=io.BytesIO(); Image.new('RGB',(32,32),'gray').save(out,format='PNG'); return out.getvalue()
def fixture(): return json.loads(DemoBackend().analyze(b'', ''))

def test_default_backend_uses_local_qwen_7b(monkeypatch):
    for name in ['VLM_MODEL', 'VLM_BASE_URL', 'VLM_API_STYLE']:
        monkeypatch.delenv(name, raising=False)
    backend = VLMBackend()
    assert backend.model == 'qwen2.5vl:7b'
    assert backend.endpoint == 'http://localhost:11434/v1'
    assert backend.native is True
    assert backend.response_contract == 'scene_assessment_v4'

def test_demo_and_review():
    r=run(picture(),DemoBackend()); original=dict(r['prediction'])
    assert r['human_verification']['status']=='pending'
    assert verify(r,original,'tester')['human_verification']['status']=='confirmed'
    corrected=dict(original,incident='non_incident',asset='track',damaged_component='none',damage_type='none',severity='none')
    reviewed=verify(r,corrected,'tester')
    assert reviewed['human_verification']['status']=='corrected'
    assert reviewed['prediction']==original and r['human_verification']['status']=='pending'
    with pytest.raises(ValueError): verify(r,original,' ')

@pytest.mark.parametrize('change',[{'confidence':1.1},{'confidence':float('nan')},{'incident':'non_incident'},{'severity':'minor'},{'surprise':1},{'asset':'train'}])
def test_reject_invalid(change):
    with pytest.raises(ValueError): parse_prediction(json.dumps(dict(fixture(),**change)))

def test_invalid_image_and_model():
    with pytest.raises(Exception): prepare_image(b'not an image')
    class Bad(DemoBackend):
        def analyze(self,*args): return 'not JSON'
    r=run(picture(),Bad())
    assert r['prediction'] is None and r['error']

def test_real_adapter_mock_http(monkeypatch):
    captured=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({'choices':[{'message':{'content':json.dumps(fixture())},'finish_reason':'stop'}]}).encode())
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        monkeypatch.setenv('VLM_BASE_URL',f'http://127.0.0.1:{server.server_port}/v1')
        r=run(picture(),VLMBackend())
        assert not r['error']
        assert captured[0]['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
    finally: server.shutdown(); server.server_close(); thread.join()

def test_metrics_missing_abstention_and_no_review_leakage():
    p=dict(fixture(),incident='non_incident',asset='track',damaged_component='none',damage_type='none',severity='none',confidence=0.8)
    truth=[dict(p,image_id='a'),dict(p,image_id='b')]
    records=[dict(image_id='a',prediction=p,human_verification={'status':'corrected','final_prediction':fixture()})]
    m=evaluate(truth,records)
    assert m['exact_match_all_images']==0.5
    assert m['failures_or_missing']==1
    assert m['whole_tuple_brier']==pytest.approx(.04)
    assert m['selective_coverage']==.5
    with pytest.raises(ValueError): evaluate(truth,records*2)

def test_validation_repair_preserves_first_response():
    class Repair(DemoBackend):
        calls=0
        def analyze(self,*args):
            return json.dumps(dict(fixture(),incident='non_incident'))
        def repair(self,image,mime,raw,error):
            self.calls+=1
            assert 'Non-incident requires' in error
            return json.dumps(fixture())
    backend=Repair()
    result=run(picture(),backend)
    assert result['error'] is None and backend.calls==1
    assert len(result['attempts'])==2
    assert 'validation_error' in result['attempts'][0]
    assert result['prediction']['incident']=='uncertain'

def test_failed_repair_stops_after_one_attempt():
    class Repair(DemoBackend):
        calls=0
        def analyze(self,*args): return 'invalid'
        def repair(self,*args):
            self.calls+=1
            return 'still invalid'
    backend=Repair()
    result=run(picture(),backend)
    assert result['prediction'] is None and result['error']
    assert backend.calls==1 and len(result['attempts'])==2


def test_asset_confidence_excluded_from_whole_tuple_calibration():
    p=dict(fixture(),incident='non_incident',asset='track',damaged_component='none',damage_type='none',severity='none',confidence=.8)
    metrics=evaluate([dict(p,image_id='one')],[dict(image_id='one',prediction=p,response_contract='scene_assessment_v4',confidence_scope='selected_asset')])
    assert metrics['whole_tuple_brier'] is None and metrics['whole_tuple_ece'] is None
    assert metrics['confidence_excluded_wrong_scope']==1
    assert metrics['exact_match_all_images']==1
