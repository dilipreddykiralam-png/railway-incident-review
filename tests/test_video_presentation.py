import copy
import json

from railreview.video_presentation import video_presentation


def frame(label='non_incident', *, status='no_visible_damage', timestamp=0):
    finding = dict(asset='wagon', component='body', damage_status=status,
                   damage_type='none', severity='none', confidence=.8,
                   evidence='The vehicle body is visible.')
    if status == 'visible_damage':
        finding.update(damage_type='deformation', severity='severe', evidence='The body is deformed.')
    if status == 'suspected_damage':
        finding.update(damage_type='unknown', severity='unknown')
    prediction = dict(incident=label, asset='wagon', damaged_component='none',
                      damage_type='none', severity='none', confidence=.8,
                      evidence='A railway vehicle is visible.', limitations='Sampled frame only.',
                      findings=[finding])
    if label == 'incident':
        prediction.update(damaged_component='body', damage_type='deformation', severity='severe')
    if label == 'uncertain':
        prediction.update(damaged_component='unknown', damage_type='unknown', severity='unknown')
    return dict(prediction=prediction, error=None, timestamp_seconds=timestamp,
                analyzed_image_jpeg_base64='unchanged image bytes')


def test_mixed_video_keeps_one_normal_first_and_incident_source_numbers():
    record = {'frames': [frame('incident', status='visible_damage', timestamp=1),
                         frame(timestamp=2), frame(timestamp=3),
                         frame('incident', status='visible_damage', timestamp=4)]}
    original = copy.deepcopy(record)
    display = video_presentation(record)
    assert display['mode'] == 'mixed_or_review'
    assert display['selected_sample_numbers'] == [2, 1, 4]
    assert display['representative_normal_sample'] == 2
    assert display['hidden_normal_count'] == 1
    assert display['counts'] == dict(incident=2, non_incident=2, needs_review=0, failed=0)
    assert 'Supporting samples: 1, 4.' in display['description_points'][0]
    assert display['description_points'][0].startswith('Model claim: Freight wagon')
    assert record == original
    json.dumps(display, allow_nan=False)


def test_all_normal_retains_all_images_with_one_shared_summary():
    display = video_presentation({'frames': [frame(timestamp=0), frame(timestamp=10), frame(timestamp=20)]})
    assert display['mode'] == 'all_non_incident'
    assert display['selected_sample_numbers'] == [1, 2, 3]
    assert display['hidden_normal_count'] == 0
    assert display['description_points'] == []
    assert 'all 3 sampled frames' in display['summary']
    assert 'does not rule out an incident between samples' in display['summary']


def test_suspected_uncertain_and_failed_samples_are_never_collapsed_as_normal():
    record = {'frames': [frame(), frame(status='suspected_damage'),
                         frame('uncertain'), dict(prediction=None, error='decode failed'), frame()]}
    display = video_presentation(record)
    assert display['selected_sample_numbers'] == [1, 2, 3, 4]
    assert display['counts'] == dict(incident=0, non_incident=2, needs_review=2, failed=1)
    assert 'prevent a reliable no-incident conclusion' in display['summary']
    assert 'Supporting samples: 2.' in display['description_points'][0]


def test_conflicting_normal_claims_remain_visible_including_saved_review_flags():
    flags = frame()
    flags['derivation_notes'] = ['conflicting_event_and_asset_claims']
    raw_conflict = frame()
    raw_conflict['model_assessment'] = dict(event='visible_incident', scene_context='railway')
    display = video_presentation({'frames': [frame(), frame(status='visible_damage'),
                                           flags, raw_conflict, frame(status='involved_no_visible_damage')]})
    assert display['selected_sample_numbers'] == [1, 2, 3, 4, 5]
    assert display['counts']['needs_review'] == 4


def test_all_failures_are_visible_and_no_cached_summary_is_used():
    display = video_presentation(dict(frames=[dict(prediction=None, error='Failed'),
                                             dict(prediction={'incident': 'non_incident'})],
                                      prediction={'incident': 'non_incident'},
                                      summary='The entire video is normal.', asset_findings=['stale']))
    assert display['mode'] == 'all_failed'
    assert display['selected_sample_numbers'] == [1, 2]
    assert display['counts']['failed'] == 2
    assert display['representative_normal_sample'] is None
    assert 'cannot be assessed' in display['summary']
    assert display['description_points'] == []


def test_empty_video_has_no_supported_conclusion():
    display = video_presentation({'frames': []})
    assert display['mode'] == 'all_failed'
    assert display['selected_sample_numbers'] == []
    assert 'cannot be assessed' in display['summary']


def test_failed_frame_with_stale_prediction_does_not_supply_claims():
    failed = frame('incident', status='visible_damage')
    failed['error'] = 'Failed'
    display = video_presentation({'frames': [frame(), failed]})
    assert display['counts'] == dict(incident=0, non_incident=1, needs_review=0, failed=1)
    assert display['description_points'] == []
