"""Display independent model estimates without modifying research predictions."""
import math


CLASSIFICATIONS = {
    'visible_incident': 'Incident',
    'incident': 'Incident',
    'no_visible_incident': 'No visible incident',
    'non_incident': 'No visible incident',
    'uncertain': 'Uncertain',
}
SEVERITIES = {
    'none': 'No visible damage',
    'unknown': 'Not assessable',
    'minor': 'Minor',
    'moderate': 'Moderate',
    'severe': 'Severe',
    'critical': 'Critical',
}
SEVERITY_ORDER = ['none', 'unknown', 'minor', 'moderate', 'severe', 'critical']


def _score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else None


def _findings(record):
    prediction = record.get('prediction') or {}
    assessment = record.get('model_assessment') or {}
    # Respect exclusions made by validation, including unsuitable scenes.
    if assessment and assessment.get('scene_context') != 'railway':
        return []
    return prediction.get('findings', assessment.get('findings', [])) or []


def _selected_asset(findings):
    visible = [f for f in findings if f.get('damage_status') == 'visible_damage']
    suspected = [f for f in findings if f.get('damage_status') == 'suspected_damage']
    candidates = visible or suspected or findings
    return max(candidates, key=lambda f: SEVERITY_ORDER.index(f.get('severity', 'unknown'))
               if f.get('severity', 'unknown') in SEVERITY_ORDER else 1) if candidates else None


def _image_confidence(record):
    assessment = record.get('model_assessment')
    prediction = record.get('prediction') or {}
    if assessment:
        event_score = _score(assessment.get('event_confidence'))
        if event_score is not None:
            return ('Classification confidence', event_score,
                    'Model self-assessment of its event classification; not calibrated accuracy.')
        asset = _selected_asset(_findings(record))
        asset_score = _score(asset.get('confidence')) if asset else None
        if asset_score is not None:
            return ('Selected-asset confidence', asset_score,
                    'Confidence in the selected asset finding, not the event classification. '
                    'The model did not report event confidence; reanalyse to request it.')
        return ('Classification confidence', None,
                'The model did not report event confidence. No asset confidence is available.')
    if record.get('backend') == 'demo':
        return ('Demo fixture confidence', _score(prediction.get('confidence')),
                'Fixed demo value; no image inference was performed.')
    return ('Legacy model confidence', _score(prediction.get('confidence')),
            'Confidence from the legacy prediction contract; not a separately estimated event score.')


def display_metrics(record):
    """Return presentation fields; raw predictions and their review policy remain intact.

    Video classification uses the sampled-video aggregate. Its confidence always
    belongs to the selected frame, never to the entire video. Severity is selected
    independently from visible damage, then suspected damage, then intact assets.
    """
    prediction = record.get('prediction') or {}
    review_classification = CLASSIFICATIONS.get(prediction.get('incident'), 'Not available')
    video = record.get('media_type') == 'video'
    assessment = record.get('model_assessment') or {}
    classification = (CLASSIFICATIONS.get(assessment.get('event'), review_classification)
                      if assessment and not video else review_classification)

    if video:
        findings = [finding for frame in record.get('frames', [])
                    if frame.get('prediction') for finding in _findings(frame)]
    else:
        findings = _findings(record)
    selected_asset = _selected_asset(findings)
    severity_code = selected_asset.get('severity') if selected_asset else prediction.get('severity')
    severity = SEVERITIES.get(severity_code, 'Not assessable')

    if video:
        timestamp = record.get('selected_timestamp_seconds')
        selected_frame = next((frame for frame in record.get('frames', [])
                               if timestamp is not None and frame.get('prediction')
                               and frame.get('timestamp_seconds') == timestamp), None)
        if selected_frame:
            source_label, confidence, note = _image_confidence(selected_frame)
            scope = {
                'Classification confidence': 'classification',
                'Selected-asset confidence': 'asset',
                'Legacy model confidence': 'legacy',
                'Demo fixture confidence': 'demo',
            }[source_label]
            confidence_label = f'Selected-frame {scope} confidence'
            confidence_note = (f'Selected frame near {timestamp:.2f}s. {note} '
                               'This is not a whole-video probability.')
        else:
            confidence_label, confidence = 'Selected-frame confidence', None
            confidence_note = ('The selected frame confidence is unavailable. '
                               'No whole-video probability was estimated.')
    else:
        confidence_label, confidence, confidence_note = _image_confidence(record)

    if assessment and not video and assessment.get('scene_context') != 'railway':
        confidence_note += ' The scene is unsuitable or unclear; its railway claims remain excluded.'
    if classification != review_classification:
        confidence_note += (' The model event label and the conservative review classification differ; '
                            'review the flagged claims.')
    return dict(classification=classification, review_classification=review_classification,
                severity=severity, confidence_label=confidence_label, confidence=confidence,
                confidence_note=confidence_note)
