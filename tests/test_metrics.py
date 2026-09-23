import copy
import pytest
from railreview.metrics import display_metrics


def finding(status='suspected_damage', severity='unknown', confidence=.7):
    return dict(asset='road_vehicle', component='body', damage_status=status,
                damage_type='unknown' if status == 'suspected_damage' else 'deformation',
                severity=severity, confidence=confidence, evidence='Truck on the tracks.')


def native(event='no_visible_incident', incident='uncertain', findings=None, event_confidence=None):
    findings = [finding()] if findings is None else findings
    assessment = dict(scene_context='railway', event=event, findings=findings)
    if event_confidence is not None:
        assessment['event_confidence'] = event_confidence
    return dict(backend='vlm', model_assessment=assessment,
                prediction=dict(incident=incident, severity='unknown', confidence=0., findings=findings))


def test_suspected_damage_preserves_real_asset_confidence_without_claiming_event_score():
    record = native()
    original = copy.deepcopy(record)
    metrics = display_metrics(record)
    assert metrics['classification'] == 'No visible incident'
    assert metrics['review_classification'] == 'Uncertain'
    assert metrics['severity'] == 'Not assessable'
    assert metrics['confidence_label'] == 'Selected-asset confidence'
    assert metrics['confidence'] == .7
    assert 'not the event classification' in metrics['confidence_note']
    assert record == original


def test_explicit_event_confidence_is_independent_of_asset_confidence():
    record = native(event_confidence=.85)
    metrics = display_metrics(record)
    assert metrics['confidence_label'] == 'Classification confidence'
    assert metrics['confidence'] == .85
    assert record['model_assessment']['findings'][0]['confidence'] == .7


def test_conflicting_event_keeps_visible_severity_and_review_classification():
    metrics = display_metrics(native(findings=[finding('visible_damage', 'severe')]))
    assert metrics['classification'] == 'No visible incident'
    assert metrics['review_classification'] == 'Uncertain'
    assert metrics['severity'] == 'Severe'


def test_incident_involvement_does_not_invent_visible_damage():
    asset = finding('involved_no_visible_damage', 'none')
    asset['damage_type'] = 'none'
    metrics = display_metrics(native(event='visible_incident', incident='incident', findings=[asset]))
    assert metrics['classification'] == 'Incident'
    assert metrics['severity'] == 'No visible damage'


def test_visible_severity_precedes_suspected_severity():
    record = native(findings=[finding('suspected_damage', 'critical'), finding('visible_damage', 'minor'),
                              finding('visible_damage', 'severe')])
    assert display_metrics(record)['severity'] == 'Severe'


def test_missing_scores_and_nonrail_findings_are_not_zero_or_valid_damage():
    empty = native(findings=[])
    assert display_metrics(empty)['confidence'] is None
    assert display_metrics(empty)['severity'] == 'Not assessable'
    unsuitable = native(findings=[finding('visible_damage', 'severe')])
    unsuitable['model_assessment']['scene_context'] = 'non_railway'
    metrics = display_metrics(unsuitable)
    assert metrics['confidence'] is None
    assert metrics['severity'] == 'Not assessable'


@pytest.mark.parametrize('score', [None, float('nan'), float('inf'), -.1, 1.1, True])
def test_unavailable_invalid_scores_do_not_render_percentages(score):
    record = native(findings=[])
    record['model_assessment']['event_confidence'] = score
    assert display_metrics(record)['confidence'] is None


def test_video_uses_aggregate_classification_and_selected_frame_confidence():
    selected = native(event='visible_incident', incident='incident',
                      findings=[finding('visible_damage', 'moderate', .6)], event_confidence=.8)
    selected['timestamp_seconds'] = 2.
    other = native(findings=[finding('visible_damage', 'severe', .95)])
    other['timestamp_seconds'] = 3.
    video = dict(media_type='video', prediction=dict(incident='incident', severity='moderate', confidence=.6),
                 selected_timestamp_seconds=2., frames=[selected, other])
    metrics = display_metrics(video)
    assert metrics['classification'] == 'Incident'
    assert metrics['severity'] == 'Severe'
    assert metrics['confidence'] == .8
    assert metrics['confidence_label'] == 'Selected-frame classification confidence'
    assert 'not a whole-video probability' in metrics['confidence_note']
    assert '2.00s' in metrics['confidence_note']


def test_partial_video_failure_retains_uncertain_classification_and_actual_selected_score():
    selected = native(incident='non_incident', event_confidence=.75)
    selected['timestamp_seconds'] = 0.
    video = dict(media_type='video', prediction=dict(incident='uncertain', severity='unknown', confidence=0.),
                 selected_timestamp_seconds=0., frames=[selected, dict(prediction=None, timestamp_seconds=1.)])
    metrics = display_metrics(video)
    assert metrics['classification'] == 'Uncertain'
    assert metrics['confidence'] == .75
    video.pop('selected_timestamp_seconds')
    assert display_metrics(video)['confidence'] is None


def test_video_old_frame_uses_explicit_asset_confidence_label():
    frame = native()
    frame['timestamp_seconds'] = 1.
    video = dict(media_type='video', prediction=frame['prediction'], selected_timestamp_seconds=1., frames=[frame])
    metrics = display_metrics(video)
    assert metrics['confidence'] == .7
    assert metrics['confidence_label'] == 'Selected-frame asset confidence'


def test_legacy_and_demo_keep_original_scores_with_scope_labels():
    record = dict(backend='vlm', prediction=dict(incident='incident', severity='moderate', confidence=.8))
    metrics = display_metrics(record)
    assert metrics['confidence_label'] == 'Legacy model confidence'
    assert metrics['confidence'] == .8
    record.update(backend='demo', prediction=dict(incident='uncertain', severity='unknown', confidence=0.))
    assert display_metrics(record)['confidence_label'] == 'Demo fixture confidence'
    assert display_metrics(record)['confidence'] == 0.
