import hashlib
import json
import io
import time
import uuid
from datetime import datetime, timezone
from PIL import Image, ImageOps
from .backends import PROMPT
from .schema import parse_prediction, review_reasons, Prediction
from .assessment import SceneAssessment, project_assessment, generation_schema

Image.MAX_IMAGE_PIXELS = 25_000_000

def now(): return datetime.now(timezone.utc).isoformat()

def prepare_image(data):
    if not data or len(data) > 10 * 1024 * 1024: raise ValueError('Use a nonempty image under 10 MB')
    with Image.open(io.BytesIO(data)) as source:
        if source.format not in ['JPEG', 'PNG', 'WEBP']: raise ValueError('Use JPEG, PNG or WebP')
        if source.width * source.height > 25_000_000: raise ValueError('Image exceeds 25 megapixels')
        image = ImageOps.exif_transpose(source).convert('RGB')
        image.thumbnail((1536,1536))
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=90)
    return output.getvalue()

def run(data, backend, threshold=0.7):
    if not 0 <= threshold <= 1: raise ValueError('Threshold must be 0..1')
    started = time.perf_counter()
    image = prepare_image(data)
    record = dict(id=str(uuid.uuid4()), created_at=now(), image_sha256=hashlib.sha256(data).hexdigest(), processed_sha256=hashlib.sha256(image).hexdigest(), backend=backend.name, model=backend.model, schema_sha256=hashlib.sha256(json.dumps(Prediction.model_json_schema(), sort_keys=True).encode()).hexdigest(), prompt_version='railway_v2', prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(), preprocessing='EXIF transpose; RGB; max 1536px; JPEG quality 90', temperature=0, review_threshold=threshold, prediction=None, raw_response=None, error=None, human_verification={'status':'pending'})
    prompt = getattr(backend, 'prompt', PROMPT)
    record['prompt_version'] = getattr(backend, 'prompt_version', 'railway_v2')
    record['prompt_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
    record['response_contract'] = getattr(backend, 'response_contract', 'prediction_v2')
    if record['response_contract'] in ['scene_assessment_v3','scene_assessment_v4']:
        output_schema=generation_schema()
        record['schema_sha256'] = hashlib.sha256(json.dumps(output_schema,sort_keys=True).encode()).hexdigest()
        record['generation_settings'] = {'temperature':0,'num_ctx':8192,'num_predict':2048,'structured_format':True}
    record['attempts'] = []
    record['repair_policy'] = 'one_validation_retry_v1'
    def parse(raw):
        if record['response_contract'] in ['scene_assessment_v3','scene_assessment_v4']:
            prediction, assessment, notes = project_assessment(raw)
            record['model_assessment'] = assessment
            record['derivation_notes'] = notes
            record['projection_policy'] = 'asset_first_primary_v2'
            record['confidence_basis'] = 'Selected asset self-assessment; event confidence is separate in model_assessment; missing estimate is not displayed'
            record['confidence_scope'] = 'selected_asset'
            record['confidence_available'] = bool(prediction.findings)
            return prediction
        return parse_prediction(raw, require_findings=backend.name == 'vlm')
    try:
        record['raw_response'] = backend.analyze(image, 'image/jpeg')
        record['attempts'].append({'raw_response': record['raw_response']})
        try:
            p = parse(record['raw_response'])
        except ValueError as first_error:
            record['attempts'][0]['validation_error'] = str(first_error)
            if not hasattr(backend, 'repair'):
                raise
            record['raw_response'] = backend.repair(image, 'image/jpeg', record['raw_response'], str(first_error))
            record['attempts'].append({'raw_response': record['raw_response']})
            p = parse(record['raw_response'])
        record['prediction'] = p.model_dump()
        record['review_reasons'] = review_reasons(p, threshold) + record.get('derivation_notes', [])
    except Exception as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
        if record['attempts']:
            record['attempts'][-1]['error'] = record['error']
        record['review_reasons'] = ['inference_or_validation_failure']
    record['latency_seconds'] = round(time.perf_counter()-started,4)
    return record

def verify(record, corrected, reviewer, notes=''):
    if not reviewer.strip(): raise ValueError('Reviewer ID is required')
    if record['prediction'] is None: raise ValueError('Cannot verify failed inference; rerun first')
    validated = Prediction.model_validate(corrected).model_dump()
    import copy
    result = copy.deepcopy(record)
    result['human_verification'] = dict(status='confirmed' if validated == record['prediction'] else 'corrected', reviewer=reviewer.strip(), notes=notes, verified_at=now(), final_prediction=validated)
    return result
