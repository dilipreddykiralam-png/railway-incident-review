import json
import cv2
import numpy as np
import pytest
from railreview.video import sample_frames, run_video, aggregate
from railreview.backends import DemoBackend

def test_decode_video_and_pipeline(tmp_path):
    path=tmp_path/'sample.avi'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,48))
    assert writer.isOpened()
    for i in range(20): writer.write(np.full((48,64,3),i*10,dtype=np.uint8))
    writer.release()
    data=path.read_bytes()
    frames,duration=sample_frames(data,4)
    assert len(frames)==4 and all(f['image'] for f in frames)
    assert frames[0]['frame_index']==0 and frames[-1]['frame_index']==19
    assert duration==pytest.approx(2)
    result=run_video(data,DemoBackend(),count=4)
    assert result['media_type']=='video' and result['sample_count']==4
    assert result['prediction']['incident']=='uncertain'
    assert result['human_verification']['status']=='pending'

def record(label='non_incident'):
    p=json.loads(DemoBackend().analyze(b'',''))
    if label=='non_incident': p.update(incident=label,asset='track',damaged_component='none',damage_type='none',severity='none')
    if label=='incident': p.update(incident=label,asset='wagon',damaged_component='bogie',damage_type='derailment',severity='severe')
    return dict(prediction=p,timestamp_seconds=1)

def summarize(records): return aggregate(records,DemoBackend(),'hash',3,.7,1)

def test_partial_failure_abstains_and_incident_wins():
    failed=dict(prediction=None,error='decode failed',timestamp_seconds=2)
    assert summarize([record(),failed])['prediction']['incident']=='uncertain'
    assert summarize([record(),record('incident'),failed])['prediction']['incident']=='incident'
    assert summarize([failed])['prediction'] is None
    assert summarize([record(),record()])['prediction']['incident']=='non_incident'

def test_invalid_video():
    with pytest.raises(ValueError): sample_frames(b'not a video')

def test_grouped_railway_summary():
    from railreview.summary import combined_findings
    a=record('incident')
    b=record('incident'); b['timestamp_seconds']=2
    c=record('incident'); c['prediction']['asset']='locomotive'; c['prediction']['damage_type']='collision_damage'
    groups=combined_findings({'frames':[a,b,c,dict(prediction=None)]})
    assert len(groups)==2
    assert groups[0]['asset']=='Freight wagon'
    assert groups[0]['timestamps']==[1,2]
    assert len(groups[0]['evidence'])==1
    assert groups[1]['asset']=='Locomotive' and groups[1]['damage']=='Collision damage'
