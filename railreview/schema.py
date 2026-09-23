import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

LABELS = {
    'incident': ['incident', 'non_incident', 'uncertain'],
    'asset': ['locomotive', 'wagon', 'passenger_coach', 'track', 'signal', 'catenary', 'level_crossing_barrier', 'road_vehicle', 'other', 'unknown'],
    'damaged_component': ['coupler', 'bogie', 'wheel', 'axle', 'body', 'rail', 'sleeper', 'ballast', 'signal', 'wire', 'pole', 'barrier_arm', 'cab', 'buffer_beam', 'front_end', 'trailer', 'other', 'none', 'unknown'],
    'damage_type': ['deformation', 'crack', 'breakage', 'fire', 'derailment', 'collision_damage', 'displacement', 'other', 'none', 'unknown'],
    'severity': ['none', 'minor', 'moderate', 'severe', 'critical', 'unknown'],
}
class AssetFinding(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    asset: Literal['locomotive', 'wagon', 'passenger_coach', 'track', 'signal', 'catenary', 'level_crossing_barrier', 'road_vehicle', 'other', 'unknown']
    component: str = Field(min_length=1, max_length=100)
    damage_status: Literal['visible_damage', 'suspected_damage', 'involved_no_visible_damage', 'no_visible_damage']
    damage_type: Literal['deformation', 'crack', 'breakage', 'fire', 'derailment', 'collision_damage', 'displacement', 'other', 'none', 'unknown']
    severity: Literal['none', 'minor', 'moderate', 'severe', 'critical', 'unknown']
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def consistent_damage(self):
        if self.damage_status in ['involved_no_visible_damage', 'no_visible_damage']:
            if self.damage_type != 'none' or self.severity != 'none':
                raise ValueError('No visible damage requires damage_type and severity none')
        if self.damage_status == 'visible_damage' and self.damage_type in ['none','unknown']:
            raise ValueError('Visible damage requires a specific visible damage type')
        if self.damage_status in ['visible_damage','suspected_damage'] and self.severity == 'none':
            raise ValueError('Damage severity must be a severity level or unknown')
        return self

class Prediction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    incident: Literal['incident', 'non_incident', 'uncertain']
    asset: Literal['locomotive', 'wagon', 'passenger_coach', 'track', 'signal', 'catenary', 'level_crossing_barrier', 'road_vehicle', 'other', 'unknown']
    damaged_component: Literal['coupler', 'bogie', 'wheel', 'axle', 'body', 'rail', 'sleeper', 'ballast', 'signal', 'wire', 'pole', 'barrier_arm', 'cab', 'buffer_beam', 'front_end', 'trailer', 'other', 'none', 'unknown']
    damage_type: Literal['deformation', 'crack', 'breakage', 'fire', 'derailment', 'collision_damage', 'displacement', 'other', 'none', 'unknown']
    severity: Literal['none', 'minor', 'moderate', 'severe', 'critical', 'unknown']
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence: str = Field(min_length=1, max_length=1500)
    limitations: str = Field(min_length=1, max_length=1500)

    findings: list[AssetFinding] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def consistent(self):
        if self.incident == 'non_incident' and any(getattr(self, k) != 'none' for k in ['damaged_component','damage_type','severity']):
            raise ValueError('Non-incident requires component, damage and severity = none')
        if self.incident == 'incident' and any(getattr(self, k) == 'none' for k in ['damaged_component','damage_type','severity']):
            raise ValueError('Incident cannot have none component, damage or severity; use unknown if unclear')
        if self.incident == 'uncertain' and self.severity != 'unknown':
            raise ValueError('Uncertain classification requires unknown severity')
        return self

def parse_prediction(raw, require_findings=False):
    text = raw.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    payload = json.loads(text)
    if require_findings and 'findings' not in payload:
        raise ValueError('Return the required findings array with independent asset assessments')
    result = Prediction.model_validate(payload)
    if require_findings and result.incident != 'uncertain' and not result.findings:
        raise ValueError('An assessed railway scene requires at least one asset finding')
    return result

def review_reasons(p, threshold=0.7):
    reasons = []
    if p.confidence < threshold: reasons.append('low_confidence')
    if p.incident == 'uncertain': reasons.append('abstention')
    if any(getattr(p, k) == 'unknown' for k in LABELS): reasons.append('unknown_field')
    if p.severity in ['severe','critical']: reasons.append('high_severity')
    return reasons or ['routine_verification']
