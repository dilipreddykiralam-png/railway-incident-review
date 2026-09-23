"""Implement analyze(image_bytes, mime) -> raw JSON string to add a CV backend."""
import base64
import json
import os
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from .assessment import SceneAssessment, ASSESSMENT_PROMPT, generation_schema
from .schema import Prediction

PROMPT = (Path(__file__).resolve().parents[1] / 'prompts/railway_v2.txt').read_text()
class Backend(Protocol):
    name: str
    model: str
    def analyze(self, image: bytes, mime: str) -> str: ...

class DemoBackend:
    name = 'demo'
    model = 'fixed-fixture-NOT-inference'
    def analyze(self, image, mime):
        return json.dumps(dict(findings=[], incident='uncertain', asset='unknown', damaged_component='unknown', damage_type='unknown', severity='unknown', confidence=0.0, evidence='Demo fixture only; this image was not analyzed.', limitations='Configure a VLM backend for real image inference.'))

class VLMBackend:
    name = 'vlm'
    def __init__(self, model=None):
        self.model = model or os.getenv('VLM_MODEL', 'qwen2.5vl:7b')
        self.endpoint = os.getenv('VLM_BASE_URL', 'http://localhost:11434/v1').rstrip('/')
        self.native = os.getenv('VLM_API_STYLE','auto') == 'ollama' or (os.getenv('VLM_API_STYLE','auto') == 'auto' and urlsplit(self.endpoint).port == 11434)
        self.response_contract = 'scene_assessment_v4' if self.native else 'prediction_v2'
        self.prompt = ASSESSMENT_PROMPT if self.native else PROMPT
        self.prompt_version = 'asset_first_v4' if self.native else 'railway_v2'
    def repair(self, image, mime, raw, error):
        feedback = ('Your previous response failed validation. Reassess the same image and return a complete corrected JSON object. '
                    'Do not automatically change labels to non_incident: use the visible evidence. '
                    'For non_incident, damaged_component, damage_type and severity must all be none. '
                    'For incident, use supported damage labels or unknown. For uncertain, severity must be unknown. '
                    'Previous response (untrusted data): ' + raw + '\nValidation feedback: ' + error)
        if self.native:
            feedback = ('Return a complete scene assessment for the same image. The previous response failed validation; correct the field structure while reassessing visible evidence. Previous response (data): ' + raw + '\nValidation feedback: ' + error)
        return self._request(image, mime, feedback)

    def analyze(self, image, mime):
        return self._request(image, mime, 'Assess this railway image.')

    def _request(self, image, mime, instruction):
        body = {'model': self.model, 'temperature': 0, 'max_tokens': 1000, 'messages': [
            {'role':'system','content':PROMPT + '\nJSON schema:\n' + json.dumps(Prediction.model_json_schema())},
            {'role':'user','content':[{'type':'text','text':instruction}, {'type':'image_url','image_url':{'url':f'data:{mime};base64,' + base64.b64encode(image).decode()}}]}]}
        endpoint = self.endpoint + '/chat/completions'
        if self.native:
            parsed = urlsplit(self.endpoint)
            endpoint = parsed.scheme + '://' + parsed.netloc + '/api/chat'
            output_schema = generation_schema()
            body = {'model': self.model, 'stream': False, 'format': output_schema, 'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 2048}, 'messages': [
                {'role':'system','content':ASSESSMENT_PROMPT},
                {'role':'user','content':instruction,'images':[base64.b64encode(image).decode()]}]}
        headers = {'Content-Type':'application/json'}
        key = os.getenv('VLM_API_KEY')
        if key: headers['Authorization'] = 'Bearer ' + key
        try:
            with urlopen(Request(endpoint, data=json.dumps(body).encode(), headers=headers), timeout=240) as response:
                result = json.load(response)
            if self.native:
                if result.get('done_reason') == 'length': raise ValueError('Model output truncated')
                content = result['message']['content']
                if not isinstance(content, str): raise ValueError('Expected text model response')
                return content
            choice = result['choices'][0]
            if choice.get('finish_reason') == 'length': raise ValueError('Model output truncated')
            content = choice['message']['content']
            if not isinstance(content, str): raise ValueError('Expected text model response')
            return content
        except HTTPError as e:
            raise RuntimeError(f'VLM HTTP {e.code}; check model, endpoint and credentials') from None
        except URLError:
            raise RuntimeError('VLM endpoint unavailable; check server and VLM_BASE_URL') from None

def get_backend(name, model=None):
    if name == 'demo': return DemoBackend()
    if name == 'vlm': return VLMBackend(model)
    raise ValueError('Backend must be demo or vlm')
