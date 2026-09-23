import base64
import hashlib
import json
import pytest
from railreview.schema import AssetFinding, parse_prediction
from railreview.summary import asset_findings
from railreview.review import review_assets
from railreview.backends import DemoBackend
from railreview.video import run_video

def finding(asset='road_vehicle',status='visible_damage'):
    return dict(asset=asset,component='body',damage_status=status,damage_type='deformation',severity='moderate',confidence=.6,evidence='Visible crushed body panel.')

def test_multiasset_status_and_references():
    truck=finding()
    barrier=finding('level_crossing_barrier')
    loco=dict(finding('locomotive'),damage_status='involved_no_visible_damage',damage_type='none',severity='none',evidence='Locomotive present; front damage not visible.')
    p=json.loads(DemoBackend().analyze(b'',''));p['findings']=[truck,barrier,loco]
    parse_prediction(json.dumps(p),require_findings=True)
    record={'frames':[dict(prediction=p,timestamp_seconds=1),dict(prediction=p,timestamp_seconds=2)]}
    groups=asset_findings(record)
    assert len(groups)==3 and len(groups[0]['sources'])==2
    assert groups[2]['damage_status']=='involved_no_visible_damage'
    rows=[dict(truck,samples='1,2')]
    verified=review_assets(record,rows,'reviewer')
    assert verified['findings'][0]['samples']==[1,2]
    assert len(record['frames'][0]['prediction']['findings'])==3
    with pytest.raises(ValueError):review_assets(record,[dict(truck,samples='3')],'reviewer')
    with pytest.raises(ValueError):AssetFinding.model_validate(dict(loco,damage_type='collision_damage'))

def test_requires_multiasset_output():
    p=json.loads(DemoBackend().analyze(b'',''));p.pop('findings')
    with pytest.raises(ValueError):parse_prediction(json.dumps(p),require_findings=True)

def test_exact_analyzed_images_retained(monkeypatch):
    import io
    from PIL import Image
    out=io.BytesIO();Image.new('RGB',(40,40),'gray').save(out,format='PNG')
    monkeypatch.setattr('railreview.video.sample_frames',lambda data,count:([dict(image=out.getvalue(),frame_index=0,timestamp_seconds=0,error=None)],1))
    result=run_video(b'fixture',DemoBackend())
    frame=result['frames'][0]
    assert hashlib.sha256(base64.b64decode(frame['analyzed_image_jpeg_base64'])).hexdigest()==frame['processed_sha256']

def test_empty_editor_cells_have_useful_errors():
    record={'frames':[{}]}
    with pytest.raises(ValueError, match='Asset row 1: please fill in confidence, evidence'):
        review_assets(record,[dict(finding(),confidence=float('nan'),evidence=None)],'reviewer')
    empty={k:None for k in finding()}
    assert review_assets(record,[empty,dict(finding(),samples=None)],'reviewer')['findings'][0]['samples']==[]
    with pytest.raises(ValueError, match='confidence must be a number'):
        review_assets(record,[dict(finding(),confidence=float('inf'))],'reviewer')
    with pytest.raises(ValueError, match='sample numbers'):
        review_assets(record,[dict(finding(),samples='abc')],'reviewer')
