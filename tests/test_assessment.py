import json
import pytest
from railreview.assessment import project_assessment

def example(event='no_visible_incident', status='no_visible_damage'):
 return dict(scene_context='railway',event=event,evidence='A truck is at a level crossing.',limitations='Damage detail may be obscured.',findings=[dict(asset='road_vehicle',component='body',damage_status=status,damage_type='none' if status=='no_visible_damage' else 'deformation',severity='none' if status=='no_visible_damage' else 'moderate',confidence=.7,evidence='Truck body visible.')])

def test_normal_scene_projects_to_valid_none_fields():
 p,raw,notes=project_assessment(json.dumps(example()))
 assert p.incident=='non_incident' and p.damaged_component=='none' and p.severity=='none'
 assert raw['findings'][0]['component']=='body' and not notes

def test_conflicting_claims_abstain_without_erasing_asset():
 p,raw,notes=project_assessment(json.dumps(example(status='visible_damage')))
 assert p.incident=='uncertain' and p.confidence==.7 and p.findings[0].damage_type=='deformation'
 assert notes==['conflicting_event_and_asset_claims']

def test_visible_damage_maps_primary_and_nonrail_abstains():
 p,_,_=project_assessment(json.dumps(example(event='visible_incident',status='visible_damage')))
 assert p.incident=='incident' and p.damage_type=='deformation' and p.asset=='road_vehicle'
 data=example();data['scene_context']='non_railway';data['findings']=[]
 assert project_assessment(json.dumps(data))[0].incident=='uncertain'

def test_bad_finding_remains_validation_failure():
 data=example();data['findings'][0]['confidence']=float('nan')
 with pytest.raises(ValueError):project_assessment(json.dumps(data))

def test_native_adapter_and_pipeline_keep_raw_contract(monkeypatch):
 import io,threading
 from http.server import HTTPServer,BaseHTTPRequestHandler
 from PIL import Image
 from railreview.backends import VLMBackend
 from railreview.pipeline import run
 captured=[]
 class Handler(BaseHTTPRequestHandler):
  def do_POST(self):
   captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
   self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'message':{'content':json.dumps(example())},'done_reason':'stop'}).encode())
  def log_message(self,*args):pass
 server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  monkeypatch.setenv('VLM_API_STYLE','ollama');monkeypatch.setenv('VLM_BASE_URL',f'http://127.0.0.1:{server.server_port}/v1')
  out=io.BytesIO();Image.new('RGB',(32,32)).save(out,format='PNG')
  record=run(out.getvalue(),VLMBackend('qwen2.5vl:7b'))
  assert not record['error'] and record['prediction']['incident']=='non_incident'
  assert record['model_assessment']['findings'][0]['component']=='body'
  assert record['response_contract']=='scene_assessment_v4'
  assert captured[0]['format']['required']==['scene_context','event','evidence','limitations','findings','event_confidence']
  assert captured[0]['messages'][1]['images']
 finally:server.shutdown();server.server_close();thread.join()


def test_suspected_damage_is_not_confirmed_event_conflict():
    data=example(status='suspected_damage')
    data['event_confidence']=.65
    data['findings'][0].update(damage_type='unknown',severity='unknown')
    p,raw,notes=project_assessment(json.dumps(data))
    assert p.incident=='non_incident' and p.confidence==.7
    assert raw['event_confidence']==.65 and notes==['suspected_damage_requires_review']
    assert p.findings[0].severity=='unknown'

def test_generation_schema_prevents_inconsistent_no_damage_fields():
    from jsonschema import validate, ValidationError as SchemaError
    from railreview.assessment import generation_schema
    data=example();data['event_confidence']=.8
    validate(data,generation_schema())
    data['findings'][0]['severity']='unknown'
    with pytest.raises(SchemaError):validate(data,generation_schema())
    data['findings'][0].update(damage_status='suspected_damage',damage_type='unknown')
    validate(data,generation_schema())
