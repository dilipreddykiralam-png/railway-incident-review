"""Read-only presentation policy for sampled videos.

``video_presentation(record)`` returns only JSON-serializable display metadata.
Sample numbers always refer to the original, unfiltered ``record['frames']``.
The full frame records, images, predictions and export data are never changed.
"""
from pydantic import ValidationError

from .schema import Prediction
from .summary import ASSETS, COMPONENTS, DAMAGE, asset_findings, term


def _state(frame):
    """Classify display eligibility, retaining all doubtful results for review."""
    if frame.get('error') or not frame.get('prediction'):
        return 'failed', 'No valid model result.', None
    try:
        prediction = Prediction.model_validate(frame['prediction']).model_dump()
    except (ValidationError, TypeError, ValueError):
        return 'failed', 'The saved prediction is invalid.', None

    label = prediction['incident']
    if label == 'uncertain':
        return 'needs_review', 'The model could not determine the event classification.', prediction
    if label == 'incident':
        return 'incident', 'The model reported an incident; human verification is required.', prediction

    # A nominally normal frame can contain contrary asset claims. It must not be
    # silently hidden with ordinary no-incident frames.
    if any(f['damage_status'] != 'no_visible_damage' for f in prediction['findings']):
        return 'needs_review', 'No-incident classification includes damage or incident-involvement claims.', prediction
    if frame.get('derivation_notes'):
        return 'needs_review', 'The model result contains review flags.', prediction
    assessment = frame.get('model_assessment') or {}
    if assessment and (
        assessment.get('event') != 'no_visible_incident'
        or assessment.get('scene_context') != 'railway'
    ):
        return 'needs_review', 'Scene assessment does not support a clear no-incident result.', prediction
    return 'non_incident', 'The model reported no visible incident.', prediction


def _description_points(frames):
    """Summarize existing grouped claims; do not infer causes, motion or damage."""
    points = []
    statuses = {
        'visible_damage': 'visible damage claimed',
        'suspected_damage': 'suspected damage; requires review',
        'involved_no_visible_damage': 'involvement claimed; no visible damage reported',
    }
    for finding in asset_findings({'frames': frames}):
        status = finding['damage_status']
        if status not in statuses:
            continue
        sources = ', '.join(str(source['sample']) for source in finding['sources'])
        description = (
            f"Model claim: {term(finding['asset'], ASSETS)} — {statuses[status]}; "
            f"component: {term(finding['component'], COMPONENTS)}; "
            f"damage: {term(finding['damage_type'], DAMAGE)}; "
            f"visual severity: {finding['severity']}. Supporting samples: {sources}."
        )
        evidence = ' '.join(finding['sources'][0]['evidence'].split())
        if len(evidence) > 240:
            evidence = evidence[:237].rstrip() + '…'
        description += ' Evidence: ' + evidence
        points.append(description)
    return points


def video_presentation(record):
    """Return frame selection and a cautious combined event summary.

    Result keys:
      mode: all_non_incident, mixed_or_review, or all_failed.
      selected_sample_numbers: original one-based sample numbers, in display order.
      representative_normal_sample: first clean normal sample, or None.
      hidden_normal_count: other normal images omitted from the default display.
      counts: mutually exclusive incident/non_incident/needs_review/failed counts.
      samples: one entry per original sample (sample/state/timestamp_seconds/reason).
      title, summary, description_points: model-claim text for the combined report.

    All-normal videos keep every sampled image and use one shared summary. Other
    videos show one clean normal reference first and all remaining non-normal
    samples in their original order. Uncertain/conflicting/failed results stay
    visible. No record-level cached summary or confidence is used.
    """
    frames = record.get('frames') or []
    counts = dict(incident=0, non_incident=0, needs_review=0, failed=0)
    samples = []
    validated_frames = []
    for number, frame in enumerate(frames, 1):
        state, reason, prediction = _state(frame)
        counts[state] += 1
        samples.append(dict(sample=number, state=state,
                            timestamp_seconds=frame.get('timestamp_seconds'), reason=reason))
        # Preserve original positions, including failures, for source references.
        validated_frames.append(dict(prediction=prediction,
                                     timestamp_seconds=frame.get('timestamp_seconds')))

    total = len(samples)
    normals = [sample['sample'] for sample in samples if sample['state'] == 'non_incident']
    representative = normals[0] if normals else None
    if total and counts['non_incident'] == total:
        mode = 'all_non_incident'
        selected = list(range(1, total + 1))
        hidden = 0
        summary = (
            f'The model reported no visible incident in all {total} sampled frames. '
            'This does not rule out an incident between samples. Human verification is required.'
        )
    elif counts['failed'] == total:
        mode = 'all_failed'
        selected = list(range(1, total + 1))
        hidden = 0
        summary = (
            f'None of the {total} sampled frames produced a valid model result. '
            'The event cannot be assessed from these results. Review the sampled images or analyze again.'
        )
    else:
        mode = 'mixed_or_review'
        selected = ([representative] if representative is not None else []) + [
            sample['sample'] for sample in samples if sample['state'] != 'non_incident'
        ]
        hidden = max(0, len(normals) - 1)
        summary = (
            f"Across {total} sampled frames, the model reported {counts['incident']} incident "
            f"and {counts['non_incident']} clear no-incident results; "
            f"{counts['needs_review']} results need review and {counts['failed']} analyses failed. "
        )
        if not counts['incident']:
            summary += 'The unresolved samples prevent a reliable no-incident conclusion. '
        summary += (
            'These findings describe sampled frames only; events between samples may be missed. '
            'Human verification is required.'
        )

    return dict(
        mode=mode, selected_sample_numbers=selected,
        representative_normal_sample=representative, hidden_normal_count=hidden,
        counts=counts, samples=samples, title='Event summary from sampled frames',
        summary=summary,
        description_points=_description_points(validated_frames) if mode == 'mixed_or_review' else [],
    )
