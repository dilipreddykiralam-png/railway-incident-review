"""Uniform frame sampling; no temporal inference or audio analysis."""
import copy
import base64
import hashlib
import math
import tempfile
import time
import uuid
from pathlib import Path
from .pipeline import run, now, prepare_image
from .schema import Prediction, review_reasons


def sample_frames(data, count=6):
    import cv2
    if not data or len(data) > 100*1024*1024:
        raise ValueError('Use a nonempty video under 100 MB.')
    if not 2 <= count <= 12:
        raise ValueError('Choose 2–12 sampled frames.')
    with tempfile.TemporaryDirectory(prefix='railreview-video-') as folder:
        path = Path(folder)/'upload.video'
        path.write_bytes(data)
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened(): raise ValueError('Cannot decode video. Try an MP4 encoded with H.264.')
            fps, total = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if not math.isfinite(fps) or not math.isfinite(total) or fps <= 0 or total < 1:
                raise ValueError('Video has no usable frame count or frame rate.')
            duration = total/fps
            if duration > 600: raise ValueError('Please trim the video to 10 minutes or less.')
            if cap.get(cv2.CAP_PROP_FRAME_WIDTH)*cap.get(cv2.CAP_PROP_FRAME_HEIGHT)>25_000_000:
                raise ValueError('Video resolution exceeds 25 megapixels.')
            indexes = sorted(set(round(i*(int(total)-1)/(count-1)) for i in range(count)))
            frames=[]
            for index in indexes:
                cap.set(cv2.CAP_PROP_POS_FRAMES,index)
                ok, frame = cap.read()
                entry={'frame_index':index,'timestamp_seconds':round(index/fps,3),'image':None,'error':None}
                if ok:
                    height,width=frame.shape[:2]
                    scale=min(1,1536/max(width,height))
                    frame=cv2.resize(frame,(max(1,round(width*scale)),max(1,round(height*scale))))
                    encoded,jpeg=cv2.imencode('.jpg',frame)
                    if encoded: entry['image']=jpeg.tobytes()
                    else: entry['error']='Frame encoding failed'
                else: entry['error']='Frame decoding failed'
                frames.append(entry)
            return frames, round(duration,3)
        finally:
            cap.release()


def aggregate(records, backend, digest, duration, threshold, elapsed):
    valid=[r for r in records if r.get('prediction')]
    incidents=[r for r in valid if r['prediction']['incident']=='incident']
    result=dict(id=str(uuid.uuid4()),created_at=now(),media_type='video',video_sha256=digest,
        backend=backend.name,model=backend.model,duration_seconds=duration,
        sampling_policy='uniform_frame_index_v1',aggregation_policy='highest_severity_incident_else_uncertain_else_non_incident_v1',
        timestamp_basis='approximate frame_index / reported FPS',sample_count=len(records),frames=records,
        prediction=None,error=None,human_verification={'status':'pending'},latency_seconds=elapsed,
        review_threshold=threshold,confidence_scope='selected frame only; not a video-level probability')
    from .summary import combined_findings, asset_findings
    result['asset_findings'] = asset_findings(result)
    result['combined_findings'] = combined_findings(result)
    result['summary_policy'] = 'group_asset_classification_component_damage_v1'
    if not valid:
        result.update(error='No sampled frame produced a valid prediction.',review_reasons=['all_frames_failed'])
        return result
    severity=['none','unknown','minor','moderate','severe','critical']
    if incidents:
        selected=max(incidents,key=lambda r:severity.index(r['prediction']['severity']))
    else:
        selected=next((r for r in valid if r['prediction']['incident']=='uncertain'),valid[0])
    p=copy.deepcopy(selected['prediction'])
    p['findings'] = []
    if not incidents and len(valid)<len(records):
        p.update(incident='uncertain',damaged_component='unknown',damage_type='unknown',severity='unknown')
    p['evidence']=(f"Sampled video summary; selected frame near {selected['timestamp_seconds']:.2f}s. "+p['evidence'])[:1500]
    p['limitations']=('Only sampled frames assessed; brief incidents between frames can be missed. No audio or motion analysis. Confidence belongs to the selected frame, not the whole video. '+p['limitations'])[:1500]
    result['prediction']=Prediction.model_validate(p).model_dump()
    result['frame_contracts']=sorted(set(r.get('response_contract','prediction_v2') for r in records))
    result['frame_review_flags']=[dict(timestamp_seconds=r['timestamp_seconds'],flags=r['derivation_notes']) for r in records if r.get('derivation_notes')]
    result['selected_frame_id']=selected.get('id')
    result['confidence_available']=selected.get('confidence_available', True)
    result['confidence_scope']='selected_frame'
    result['selected_timestamp_seconds']=selected['timestamp_seconds']
    result['review_reasons']=review_reasons(Prediction.model_validate(p),threshold)+['sampled_video_requires_review']
    if len(valid)<len(records): result['review_reasons'].append('some_frames_failed')
    return result


def run_video(data,backend,threshold=0.7,count=6,progress=None):
    started=time.perf_counter()
    frames,duration=sample_frames(data,count)
    records=[]
    for i,frame in enumerate(frames):
        if frame['image'] is None:
            record={'prediction':None,'error':frame['error']}
        else:
            record=run(frame['image'],backend,threshold)
        if frame['image'] is not None:
            record['analyzed_image_jpeg_base64'] = base64.b64encode(prepare_image(frame['image'])).decode('ascii')
        record.update(frame_index=frame['frame_index'],timestamp_seconds=frame['timestamp_seconds'])
        records.append(record)
        if progress: progress(i+1,len(frames))
    return aggregate(records,backend,hashlib.sha256(data).hexdigest(),duration,threshold,round(time.perf_counter()-started,4))
