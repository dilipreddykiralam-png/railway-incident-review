"""Deterministic, evidence-linked railway terminology for combined findings."""
ASSETS = {'locomotive':'Locomotive', 'wagon':'Freight wagon', 'passenger_coach':'Passenger coach', 'track':'Permanent way (track)', 'signal':'Railway signalling equipment', 'catenary':'Overhead line equipment', 'level_crossing_barrier':'Level-crossing barrier', 'road_vehicle':'Road vehicle (truck / lorry)', 'other':'Other asset', 'unknown':'Unidentified railway asset'}
COMPONENTS = {'body':'Vehicle body', 'wire':'Contact wire', 'pole':'Overhead line mast', 'none':'No damaged component', 'unknown':'Component unidentified'}
DAMAGE = {'collision_damage':'Collision damage', 'none':'No visible damage', 'unknown':'Damage undetermined'}
def term(value, mapping): return mapping.get(value, value.replace('_',' ').capitalize())

def combined_findings(record):
    frames = record.get('frames', [record])
    groups = {}
    for frame in frames:
        p = frame.get('prediction')
        if not p: continue
        key = tuple(p[k] for k in ['asset','incident','damaged_component','damage_type'])
        if key not in groups:
            groups[key] = dict(asset=ASSETS[p['asset']], classification=p['incident'], component=term(p['damaged_component'],COMPONENTS), damage=term(p['damage_type'],DAMAGE), severities=[], evidence=[], timestamps=[])
        group=groups[key]
        if p['severity'] not in group['severities']: group['severities'].append(p['severity'])
        if p['evidence'] not in group['evidence']: group['evidence'].append(p['evidence'])
        if 'timestamp_seconds' in frame: group['timestamps'].append(frame['timestamp_seconds'])
    return list(groups.values())


def asset_findings(record):
    """Group only compatible asset claims; retain evidence per actual source sample."""
    groups = {}
    for sample, frame in enumerate(record.get('frames', [record]), 1):
        for finding in (frame.get('prediction') or {}).get('findings', []):
            key = tuple(finding[k] for k in ['asset','component','damage_status','damage_type','severity'])
            if key not in groups:
                groups[key] = dict(finding, finding_id=f'finding_{len(groups)+1}', sources=[])
            groups[key]['sources'].append(dict(sample=sample, timestamp_seconds=frame.get('timestamp_seconds'), evidence=finding['evidence'], confidence=finding['confidence']))
            groups[key]['confidence'] = min(groups[key]['confidence'], finding['confidence'])
    return list(groups.values())
