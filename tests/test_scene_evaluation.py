import pytest

from railreview.evaluate_scene import score


def gold(image_id, label='incident', **extras):
    return dict(image_id=image_id, incident=label, annotation_status='verified', **extras)


def prediction(image_id, label='incident', **extras):
    return dict(image_id=image_id, prediction={'incident': label}, **extras)


def test_failures_and_abstentions_remain_in_denominators():
    truth = [gold('i1'), gold('i2'), gold('i3'), gold('n1', 'non_incident'),
             gold('n2', 'non_incident'), gold('n3', 'non_incident'), gold('n4', 'non_incident')]
    predictions = [prediction('i1'), prediction('i2', 'uncertain'),
                   prediction('n1'), prediction('n2', 'non_incident'),
                   prediction('n3', 'uncertain'), dict(image_id='n4', prediction=None, error='invalid JSON')]
    result = score(truth, predictions)
    assert result['binary_n'] == 7
    assert result['overall_correct_fraction'] == pytest.approx(2 / 7)
    assert result['coverage'] == pytest.approx(3 / 7)
    assert result['abstention_n'] == 2
    assert result['failures_or_missing'] == 2
    assert result['failure_reasons_binary'] == {'missing_record': 1, 'record_error': 1}
    assert result['per_class']['incident']['f1'] == pytest.approx(2 / 5)
    assert result['per_class']['non_incident']['f1'] == pytest.approx(2 / 5)
    assert result['macro_f1'] == pytest.approx(2 / 5)
    assert result['normal_false_positive_rate'] == .25
    assert result['normal_abstention_n'] == 1
    assert result['normal_failure_n'] == 1


def test_gold_uncertain_is_excluded_from_binary_metrics_but_reported():
    result = score([gold('i'), gold('u', 'uncertain'), gold('u2', 'uncertain')],
                   [prediction('i'), prediction('u', 'non_incident')])
    assert result['n'] == 3 and result['binary_n'] == 1
    assert result['gold_uncertain_n'] == 2
    assert result['overall_correct_fraction'] == 1
    assert result['per_class']['non_incident']['fp'] == 0
    assert result['macro_f1'] == .5  # Fixed two classes, including absent normal class.
    assert result['normal_false_positive_rate'] is None
    assert result['failures_or_missing'] == 0
    assert result['failures_or_missing_all_references'] == 1
    assert result['gold_uncertain_outcomes']['non_incident'] == 1
    assert result['gold_uncertain_outcomes']['failure'] == 1


def test_model_source_uses_only_model_event_and_never_human_corrections():
    record = prediction('a', 'uncertain', model_assessment={'event': 'visible_incident'},
                        human_verification={'final_prediction': {'incident': 'non_incident'}})
    assert score([gold('a')], [record])['abstention_n'] == 1
    model = score([gold('a')], [record], 'model')
    assert model['overall_correct_fraction'] == 1
    assert model['classification_field'] == 'model_assessment.event'
    assert model['source_fallback'] is False
    missing_source = score([gold('a')], [prediction('a')], 'model')
    assert missing_source['failures_or_missing'] == 1
    assert missing_source['failure_reasons_binary'] == {'missing_model_assessment': 1}


def test_failed_and_malformed_outputs_do_not_become_negative():
    truth = [gold(str(i), 'non_incident') for i in range(3)]
    records = [prediction('0', None), prediction('1', 'incident', error='failed'),
               dict(image_id='2', human_verification={'final_prediction': {'incident': 'non_incident'}})]
    result = score(truth, records)
    assert result['normal_failure_n'] == 3
    assert result['coverage'] == 0
    assert result['overall_correct_fraction'] == 0
    assert result['normal_false_positive_rate'] == 0
    assert result['normal_abstention_n'] == 0
    bad_event = score([gold('a')], [prediction('a', model_assessment={'event': 'invalid'})], 'model')
    assert bad_event['failures_or_missing'] == 1


@pytest.mark.parametrize('truth,records,message', [
    ([gold('a'), gold('a')], [], 'Duplicate truth'),
    ([gold('a')], [prediction('a'), prediction('a')], 'Duplicate prediction'),
    ([gold('a')], [prediction('extra')], 'absent from ground truth'),
    ([dict(gold('a'), annotation_status='draft')], [], 'verified'),
    ([gold('a', 'normal')], [], 'Invalid ground-truth'),
    ([gold('a', media_type='video')], [], 'Video'),
    ([gold('a')], [prediction('a', media_type='video')], 'Video'),
    ([dict(incident='incident', annotation_status='verified')], [], 'image_id'),
])
def test_reject_invalid_reference_sets_and_leakage(truth, records, message):
    with pytest.raises(ValueError, match=message):
        score(truth, records)


def test_empty_binary_set_has_no_binary_aggregate_scores():
    result = score([gold('u', 'uncertain')], [prediction('u', 'uncertain')])
    assert result['binary_n'] == 0
    for field in ['macro_f1', 'overall_correct_fraction', 'coverage', 'normal_false_positive_rate']:
        assert result[field] is None
    assert result['gold_uncertain_outcomes']['uncertain'] == 1


def test_wrong_source_rejected():
    with pytest.raises(ValueError, match='classification_source'):
        score([], [], 'human')
