"""Score image scene decisions against independently verified JSONL labels."""
import argparse
from collections import Counter
import json
from pathlib import Path


GOLD_LABELS = ('incident', 'non_incident', 'uncertain')
BINARY_LABELS = ('incident', 'non_incident')
OUTCOMES = GOLD_LABELS + ('failure',)
MODEL_EVENTS = {
    'visible_incident': 'incident',
    'no_visible_incident': 'non_incident',
    'uncertain': 'uncertain',
}


def _indexed(rows, name):
    indexed = {}
    for row in rows:
        if row.get('media_type') == 'video':
            raise ValueError('Video records require separate video-level evaluation')
        image_id = row.get('image_id')
        if not isinstance(image_id, str) or not image_id.strip():
            raise ValueError(f'{name} requires a nonempty image_id')
        if image_id in indexed:
            raise ValueError(f'Duplicate {name} image_id: {image_id}')
        indexed[image_id] = row
    return indexed


def _decision(record, source):
    if record is None:
        return 'failure', 'missing_record'
    if record.get('error'):
        return 'failure', 'record_error'
    if source == 'projected':
        prediction = record.get('prediction')
        if not isinstance(prediction, dict):
            return 'failure', 'missing_projected_prediction'
        value = prediction.get('incident')
        if value not in GOLD_LABELS:
            return 'failure', 'invalid_projected_classification'
        return value, None
    assessment = record.get('model_assessment')
    if not isinstance(assessment, dict):
        return 'failure', 'missing_model_assessment'
    event = assessment.get('event')
    if not isinstance(event, str) or event not in MODEL_EVENTS:
        return 'failure', 'invalid_model_event'
    return MODEL_EVENTS[event], None


def score(truth, predictions, classification_source='projected'):
    """Uncertain gold is reported separately; uncertain output never means normal.

    Binary accuracy and coverage use every incident/non-incident reference image,
    including missing records and failed inferences. Macro-F1 always averages the
    two fixed classes; undefined class precision/recall/F1 use zero, with support
    reported. An empty binary reference set has no aggregate score.
    """
    if classification_source not in ('projected', 'model'):
        raise ValueError('classification_source must be projected or model')
    reference = _indexed(truth, 'truth')
    predicted = _indexed(predictions, 'prediction')
    if set(predicted) - set(reference):
        raise ValueError('Predictions include IDs absent from ground truth')
    for row in reference.values():
        if row.get('annotation_status') != 'verified':
            raise ValueError('Truth must have independently verified annotation status')
        if row.get('incident') not in GOLD_LABELS:
            raise ValueError(f'Invalid ground-truth scene classification: {row.get("incident")}')

    confusion = {label: {outcome: 0 for outcome in OUTCOMES} for label in GOLD_LABELS}
    failures = Counter()
    binary_failures = Counter()
    for image_id, row in reference.items():
        outcome, reason = _decision(predicted.get(image_id), classification_source)
        confusion[row['incident']][outcome] += 1
        if reason:
            failures[reason] += 1
            if row['incident'] in BINARY_LABELS:
                binary_failures[reason] += 1

    supports = {label: sum(confusion[label].values()) for label in GOLD_LABELS}
    binary_n = sum(supports[label] for label in BINARY_LABELS)
    correct = sum(confusion[label][label] for label in BINARY_LABELS)
    abstained = sum(confusion[label]['uncertain'] for label in BINARY_LABELS)
    failed = sum(confusion[label]['failure'] for label in BINARY_LABELS)
    assessed = binary_n - abstained - failed
    per_class = {}
    for label in BINARY_LABELS:
        other = next(value for value in BINARY_LABELS if value != label)
        tp = confusion[label][label]
        fp = confusion[other][label]
        fn = supports[label] - tp
        per_class[label] = {
            'support': supports[label], 'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp / (tp + fp) if tp + fp else 0.0,
            'recall': tp / (tp + fn) if tp + fn else 0.0,
            'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        }
    normal_n = supports['non_incident']
    return {
        'scope': 'image scene classification only; no asset, video or calibration scores',
        'classification_source': classification_source,
        'classification_field': 'prediction.incident' if classification_source == 'projected' else 'model_assessment.event',
        'model_event_mapping': MODEL_EVENTS if classification_source == 'model' else None,
        'source_fallback': False,
        'reference_requirement': 'annotation_status=verified; independence must be established by the study protocol',
        'metric_policy': {
            'binary_denominator': 'all gold incident/non_incident images, including failures and abstentions',
            'gold_uncertain': 'excluded from all binary metrics; retained in confusion and counts',
            'output_uncertain': 'abstention, never converted to non_incident',
            'macro_f1': 'unweighted mean over fixed incident and non_incident classes',
            'zero_division': 0.0,
            'human_corrections': 'ignored; score original saved model outputs',
        },
        'n': len(reference),
        'binary_n': binary_n,
        'gold_uncertain_n': supports['uncertain'],
        'confusion': confusion,
        'per_class': per_class,
        'macro_f1': sum(row['f1'] for row in per_class.values()) / 2 if binary_n else None,
        'overall_correct_fraction': correct / binary_n if binary_n else None,
        'correct_n': correct,
        'coverage': assessed / binary_n if binary_n else None,
        'assessed_n': assessed,
        'abstention_n': abstained,
        'abstention_rate': abstained / binary_n if binary_n else None,
        'failures_or_missing': failed,
        'failure_rate': failed / binary_n if binary_n else None,
        'failure_reasons_binary': dict(binary_failures),
        'failures_or_missing_all_references': sum(failures.values()),
        'failure_reasons_all_references': dict(failures),
        'normal_scene_n': normal_n,
        'normal_false_positive_n': confusion['non_incident']['incident'],
        'normal_false_positive_rate': confusion['non_incident']['incident'] / normal_n if normal_n else None,
        'normal_abstention_n': confusion['non_incident']['uncertain'],
        'normal_failure_n': confusion['non_incident']['failure'],
        'gold_uncertain_outcomes': dict(confusion['uncertain']),
        'demo_present': any(row.get('backend') == 'demo' for row in predicted.values()),
    }


def _read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--truth', required=True, help='Verified image labels in JSONL format')
    parser.add_argument('--predictions', required=True, help='Original image prediction JSONL')
    parser.add_argument('--output', required=True)
    parser.add_argument('--classification-source', choices=['projected', 'model'], default='projected')
    args = parser.parse_args()
    result = score(_read_jsonl(args.truth), _read_jsonl(args.predictions), args.classification_source)
    text = json.dumps(result, indent=2, allow_nan=False)
    Path(args.output).write_text(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
