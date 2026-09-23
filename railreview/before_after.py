"""Reviewer-selected temporal evidence, never an inferred accident boundary.

Only images already stored in the analysis record may be selected. The default
pair is labelled Earlier/Later because a video may start after an incident, end
before one, or include a title card. Calling code must show both images to the
reviewer before offering the explicit Before/After confirmation.
"""
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import io
import math

from PIL import Image


LIMITATIONS = (
    'Earlier and later sampled images do not establish the accident time or '
    'prove causation. Before/after labels, when present, are reviewer assertions. '
    'Only stored samples are shown; intervening events may be missed. '
    'Check for title cards and scene changes before confirming a pair.'
)


def usable_samples(record):
    """Return displayable JPEG samples in timestamp order with original numbers.

    A model failure does not discard a stored image: it can still be inspected.
    No attempt is made to decide whether a sample shows an accident or railway.
    """
    if record.get('media_type') != 'video':
        return []
    result = []
    for sample_number, frame in enumerate(record.get('frames', []), 1):
        timestamp = frame.get('timestamp_seconds')
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp) or timestamp < 0):
            continue
        encoded = frame.get('analyzed_image_jpeg_base64')
        if not isinstance(encoded, str) or not encoded or len(encoded) > 14_000_000:
            continue
        try:
            jpeg = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(jpeg)) as image:
                if image.format != 'JPEG' or image.width * image.height > 25_000_000:
                    continue
                image.verify()
        except (ValueError, OSError, binascii.Error, Image.DecompressionBombError):
            continue
        result.append({
            'sample_number': sample_number,
            'timestamp_seconds': timestamp,
            'frame_index': frame.get('frame_index'),
            'analyzed_image_jpeg_base64': encoded,
            'analyzed_image_sha256': hashlib.sha256(jpeg).hexdigest(),
        })
    return sorted(result, key=lambda sample: (sample['timestamp_seconds'], sample['sample_number']))


def _metadata(record, earlier, later, confirmed, reviewer, notes, selection_method):
    def evidence(sample, label):
        return {key: value for key, value in dict(sample, label=label).items()
                if key != 'analyzed_image_jpeg_base64'}

    return {
        'policy': 'reviewer_selected_temporal_pair_v1',
        'selection_method': selection_method,
        'source': {
            'record_id': record.get('id'),
            'media_type': 'video',
            'video_sha256': record.get('video_sha256'),
            'timestamp_basis': record.get('timestamp_basis', 'recorded sample timestamp'),
        },
        'earlier': evidence(earlier, 'Before accident' if confirmed else 'Earlier sample'),
        'later': evidence(later, 'After accident' if confirmed else 'Later sample'),
        'confirmation': {
            'confirmed_before_after': confirmed,
            'reviewer': reviewer.strip() if confirmed else None,
            'notes': notes.strip(),
            'confirmed_at': datetime.now(timezone.utc).isoformat() if confirmed else None,
        },
        'limitations': LIMITATIONS,
    }


def candidate_pair(record):
    """Suggest earliest/latest usable samples, without making an accident claim.

    Return None if fewer than two distinct timestamps have usable images. The
    pair carries compact export metadata; use usable_samples for image bytes.
    """
    samples = usable_samples(record)
    if len(samples) < 2 or samples[0]['timestamp_seconds'] >= samples[-1]['timestamp_seconds']:
        return None
    return _metadata(record, samples[0], samples[-1], False, '', '',
                     'earliest_latest_usable_samples')


def select_pair(record, earlier_sample, later_sample, *, confirmed_before_after=False,
                reviewer='', notes=''):
    """Validate 1-based sample choices and return evidence/export metadata.

    Confirming Before/After requires the reviewer to assert that the images
    bracket the same accident. This assertion is recorded separately from model
    predictions and does not change any model finding or evaluation target.
    """
    if not isinstance(confirmed_before_after, bool):
        raise ValueError('Before/after confirmation must be a checkbox value.')
    if not isinstance(reviewer, str) or not isinstance(notes, str):
        raise ValueError('Reviewer name and notes must be text.')
    if confirmed_before_after and not reviewer.strip():
        raise ValueError('Enter your reviewer name before confirming before/after images.')
    for sample_number in (earlier_sample, later_sample):
        if isinstance(sample_number, bool) or not isinstance(sample_number, int):
            raise ValueError('Select valid sample numbers from this video.')
    samples = {sample['sample_number']: sample for sample in usable_samples(record)}
    if earlier_sample not in samples or later_sample not in samples:
        raise ValueError('Select two samples with available images and valid timestamps.')
    earlier, later = samples[earlier_sample], samples[later_sample]
    if earlier['timestamp_seconds'] >= later['timestamp_seconds']:
        raise ValueError('The later image must have a timestamp after the earlier image.')
    return _metadata(record, earlier, later, confirmed_before_after, reviewer, notes,
                     'reviewer_selected_samples')
