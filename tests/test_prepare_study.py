import csv
import json

import pytest

from railreview.prepare_study import export_study


def dataset(root, rows=None, annotations=True):
    root.mkdir()
    (root / 'images').mkdir()
    (root / 'annotations').mkdir()
    sources = rows or [dict(image_id='one', image_path='images/one.jpg', event_id='event-one')]
    for row in sources:
        path = root / row['image_path']
        if not path.exists():
            path.write_bytes(row['image_id'].encode())
        if annotations:
            label = dict(image_id=row['image_id'], event_id=row['event_id'], reviewer='reviewer-a',
                         annotation_status='verified', incident='non_incident', findings=[], split='unassigned')
            (root / 'annotations' / (row['image_id'] + '.json')).write_text(json.dumps(label))
    (root / 'sources.json').write_text(json.dumps(sources))
    return root


def change_label(root, record_id='one', **updates):
    path = root / 'annotations' / (record_id + '.json')
    data = json.loads(path.read_text())
    data.update(updates)
    path.write_text(json.dumps(data))


def test_export_preserves_sources_and_annotations_and_relative_paths(tmp_path):
    root = dataset(tmp_path / 'dataset')
    source_before = (root / 'sources.json').read_bytes()
    label_before = (root / 'annotations/one.json').read_bytes()
    out = tmp_path / 'export'
    result = export_study(root, out, 'development')
    assert result['images'] == 1 and result['events'] == 1
    with (out / 'manifest.csv').open() as file:
        row = list(csv.DictReader(file))[0]
    assert (out / row['image_path']).resolve() == (root / 'images/one.jpg').resolve()
    assert row['split'] == 'development'
    truth = json.loads((out / 'truth.jsonl').read_text())
    assert truth['findings'] == [] and truth['incident'] == 'non_incident'
    assert truth['split'] == 'development'
    assert truth['sha256'] == row['sha256']
    assert truth['annotation_confidence_scope'].startswith('reviewer')
    assert (root / 'sources.json').read_bytes() == source_before
    assert (root / 'annotations/one.json').read_bytes() == label_before


@pytest.mark.parametrize('updates', [
    {'annotation_status': 'draft'}, {'reviewer': ' '}, {'event_id': ''},
    {'image_id': 'different'}, {'incident': 'probably'}, {'findings': None},
])
def test_invalid_reference_blocks_all_output(tmp_path, updates):
    root = dataset(tmp_path / 'dataset')
    change_label(root, **updates)
    out = tmp_path / 'export'
    with pytest.raises(ValueError):
        export_study(root, out, 'test')
    assert not out.exists()


def test_missing_annotation_does_not_silently_drop_candidate(tmp_path):
    root = dataset(tmp_path / 'dataset', annotations=False)
    with pytest.raises(ValueError, match='missing independent annotation'):
        export_study(root, tmp_path / 'export', 'test')
    assert not (tmp_path / 'export').exists()


@pytest.mark.parametrize('sources', [[], {}, [{'image_id': '../outside', 'image_path': 'x'}]])
def test_bad_source_inventory(tmp_path, sources):
    root = tmp_path / 'dataset'
    root.mkdir()
    (root / 'sources.json').write_text(json.dumps(sources))
    with pytest.raises(ValueError):
        export_study(root, tmp_path / 'export', 'development')


def test_duplicate_source_ids(tmp_path):
    root = dataset(tmp_path / 'dataset')
    sources = json.loads((root / 'sources.json').read_text())
    (root / 'sources.json').write_text(json.dumps(sources * 2))
    with pytest.raises(ValueError, match='Duplicate source image_id'):
        export_study(root, tmp_path / 'export', 'test')


@pytest.mark.parametrize('external_path', ['../outside.jpg', 'absolute', 'symlink'])
def test_image_must_be_contained(tmp_path, external_path):
    root = dataset(tmp_path / 'dataset')
    outside = tmp_path / 'outside.jpg'
    outside.write_bytes(b'outside')
    if external_path == 'absolute':
        external_path = str(outside)
    elif external_path == 'symlink':
        (root / 'images/outside.jpg').symlink_to(outside)
        external_path = 'images/outside.jpg'
    sources = json.loads((root / 'sources.json').read_text())
    sources[0]['image_path'] = external_path
    (root / 'sources.json').write_text(json.dumps(sources))
    with pytest.raises(ValueError, match='inside|relative'):
        export_study(root, tmp_path / 'export', 'test')


def test_asset_schema_validated_without_legacy_primary_projection(tmp_path):
    root = dataset(tmp_path / 'dataset')
    finding = dict(asset='road_vehicle', component='trailer', damage_status='suspected_damage',
                   damage_type='unknown', severity='unknown', confidence=0.5, evidence='View is partly obscured')
    change_label(root, incident='uncertain', findings=[finding])
    out = tmp_path / 'valid'
    export_study(root, out, 'test')
    assert json.loads((out / 'truth.jsonl').read_text())['findings'][0]['confidence'] == 0.5
    finding['asset'] = 'truck'
    change_label(root, findings=[finding])
    with pytest.raises(ValueError):
        export_study(root, tmp_path / 'invalid', 'test')


def test_exact_duplicates_inside_dataset_fail(tmp_path):
    rows = [dict(image_id=i, image_path=f'images/{i}.jpg', event_id=f'event-{i}') for i in ('one', 'two')]
    root = dataset(tmp_path / 'dataset', rows)
    (root / 'images/two.jpg').write_bytes((root / 'images/one.jpg').read_bytes())
    with pytest.raises(ValueError, match='Exact duplicate'):
        export_study(root, tmp_path / 'export', 'test')


@pytest.mark.parametrize('overlap', ['hash', 'source_event', 'annotation_event'])
def test_exclusion_checks_unverified_candidates_and_annotation_overrides(tmp_path, overlap):
    excluded = dataset(tmp_path / 'excluded', annotations=False)
    root = dataset(tmp_path / 'dataset', [dict(image_id='new', image_path='images/new.jpg', event_id='new-event')])
    if overlap == 'hash':
        (root / 'images/new.jpg').write_bytes(b'one')
    elif overlap == 'source_event':
        change_label(root, record_id='new', event_id='event-one')
    else:
        (excluded / 'annotations/one.json').write_text(json.dumps(
            dict(image_id='one', event_id='new-event', annotation_status='draft')))
    with pytest.raises(ValueError, match='overlaps'):
        export_study(root, tmp_path / 'export', 'test', excluded)
    assert not (tmp_path / 'export').exists()


def test_exclusion_does_not_lose_original_source_event_when_annotation_overrides_it(tmp_path):
    excluded = dataset(tmp_path / 'excluded')
    change_label(excluded, event_id='renamed')
    root = dataset(tmp_path / 'dataset', [dict(image_id='new', image_path='images/new.jpg', event_id='event-one')])
    with pytest.raises(ValueError, match='event_id overlaps'):
        export_study(root, tmp_path / 'export', 'test', excluded)


def test_disjoint_export_and_no_overwrite(tmp_path):
    excluded = dataset(tmp_path / 'excluded')
    root = dataset(tmp_path / 'dataset', [dict(image_id='new', image_path='images/new.jpg', event_id='new-event')])
    out = tmp_path / 'export'
    export_study(root, out, 'test', excluded)
    before = (out / 'truth.jsonl').read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        export_study(root, out, 'test', excluded)
    assert (out / 'truth.jsonl').read_bytes() == before
