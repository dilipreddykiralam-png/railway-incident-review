import base64
import copy
import io
import json

from PIL import Image
import pytest

from railreview.before_after import candidate_pair, select_pair, usable_samples


def image_payload(fmt='JPEG'):
    output = io.BytesIO()
    Image.new('RGB', (12, 8), 'blue').save(output, format=fmt)
    return base64.b64encode(output.getvalue()).decode('ascii')


def video():
    # Timestamp order deliberately differs from sample index order.
    return {
        'id': 'analysis-1', 'media_type': 'video', 'video_sha256': 'source-video-hash',
        'timestamp_basis': 'approximate frame_index / reported FPS',
        'frames': [
            {'timestamp_seconds': 5.0, 'frame_index': 50,
             'analyzed_image_jpeg_base64': image_payload(), 'prediction': None},
            {'timestamp_seconds': 0.0, 'frame_index': 0,
             'analyzed_image_jpeg_base64': image_payload()},
            {'timestamp_seconds': 9.0, 'frame_index': 90,
             'analyzed_image_jpeg_base64': image_payload()},
        ],
    }


def test_candidate_uses_chronological_images_without_inventing_accident_labels():
    record = video()
    original = copy.deepcopy(record)
    pair = candidate_pair(record)
    assert pair['earlier']['sample_number'] == 2
    assert pair['later']['sample_number'] == 3
    assert pair['earlier']['label'] == 'Earlier sample'
    assert pair['later']['label'] == 'Later sample'
    assert pair['confirmation']['confirmed_before_after'] is False
    assert pair['confirmation']['confirmed_at'] is None
    assert pair['source']['video_sha256'] == 'source-video-hash'
    assert 'analyzed_image_jpeg_base64' not in json.dumps(pair)
    assert record == original


def test_filter_invalid_images_and_timestamps_but_keep_failed_inference_image():
    record = video()
    payload = image_payload()
    record['frames'].extend([
        {'timestamp_seconds': 1, 'analyzed_image_jpeg_base64': None},
        {'timestamp_seconds': 2, 'analyzed_image_jpeg_base64': 'not-a-jpeg'},
        {'timestamp_seconds': 3, 'analyzed_image_jpeg_base64': image_payload('PNG')},
        {'timestamp_seconds': float('nan'), 'analyzed_image_jpeg_base64': payload},
        {'timestamp_seconds': float('inf'), 'analyzed_image_jpeg_base64': payload},
        {'timestamp_seconds': -1, 'analyzed_image_jpeg_base64': payload},
        {'timestamp_seconds': True, 'analyzed_image_jpeg_base64': payload},
    ])
    samples = usable_samples(record)
    assert [sample['sample_number'] for sample in samples] == [2, 1, 3]
    assert len(samples[1]['analyzed_image_sha256']) == 64


def test_pair_requires_two_distinct_timestamps():
    record = video()
    for frame in record['frames']:
        frame['timestamp_seconds'] = 0
    assert candidate_pair(record) is None
    assert candidate_pair({'media_type': 'video', 'frames': []}) is None
    assert candidate_pair({'media_type': 'image'}) is None


@pytest.mark.parametrize('earlier,later', [(1, 1), (3, 2), (99, 3), (True, 3), ('2', 3)])
def test_invalid_selection_is_rejected(earlier, later):
    with pytest.raises(ValueError):
        select_pair(video(), earlier, later)


def test_confirmation_is_explicit_and_traceable():
    with pytest.raises(ValueError, match='reviewer name'):
        select_pair(video(), 2, 1, confirmed_before_after=True)
    with pytest.raises(ValueError, match='checkbox'):
        select_pair(video(), 2, 1, confirmed_before_after='false')
    pair = select_pair(video(), 2, 1, confirmed_before_after=True,
                       reviewer=' Reviewer 1 ', notes=' Same continuous scene. ')
    assert pair['earlier']['label'] == 'Before accident'
    assert pair['later']['label'] == 'After accident'
    assert pair['confirmation']['reviewer'] == 'Reviewer 1'
    assert pair['confirmation']['notes'] == 'Same continuous scene.'
    assert pair['confirmation']['confirmed_at']
    assert pair['earlier']['timestamp_seconds'] == 0
    assert pair['later']['timestamp_seconds'] == 5
    assert pair['selection_method'] == 'reviewer_selected_samples'


def test_unconfirmed_selection_never_acquires_reviewer_confirmation():
    pair = select_pair(video(), 2, 3, reviewer='Reviewer 1', notes='Checking these frames')
    assert pair['earlier']['label'] == 'Earlier sample'
    assert pair['later']['label'] == 'Later sample'
    assert pair['confirmation']['reviewer'] is None
    assert pair['confirmation']['confirmed_at'] is None
