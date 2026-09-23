"""Export independently verified image labels and check simple split leakage.

Every entry in sources.json is selected. To curate a subset, prepare a separate
dataset directory containing only the retained source entries and annotations.
Event grouping and perceptual duplicate checks still require human review.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re

from .schema import AssetFinding, LABELS


def _read_json(path):
    def invalid_constant(value):
        raise ValueError(f'{path}: non-finite JSON value {value}')
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=invalid_constant)


def _nonempty(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a nonempty string')
    return value.strip()


def _contained_file(root, relative, field):
    relative = _nonempty(relative, field)
    path = Path(relative)
    if path.is_absolute():
        raise ValueError(f'{field} must be relative to the dataset directory')
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f'{field} must remain inside the dataset directory') from None
    if not resolved.is_file():
        raise ValueError(f'{field} does not identify an existing file: {relative}')
    return resolved


def _sources(dataset_dir):
    root = Path(dataset_dir).resolve()
    rows = _read_json(root / 'sources.json')
    if not isinstance(rows, list) or not rows:
        raise ValueError('sources.json must contain a nonempty list of selected source records')
    seen = set()
    checked = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Source {number} must be an object')
        image_id = _nonempty(row.get('image_id'), f'Source {number} image_id')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', image_id):
            raise ValueError(f'Unsafe image_id: {image_id}')
        if image_id != row['image_id']:
            raise ValueError('image_id must not have surrounding whitespace')
        if image_id in seen:
            raise ValueError(f'Duplicate source image_id: {image_id}')
        seen.add(image_id)
        image = _contained_file(root, row.get('image_path'), f'{image_id} image_path')
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        checked.append((row, image, digest))
    return root, checked


def _annotation(root, image_id, required):
    relative = f'annotations/{image_id}.json'
    candidate = root / relative
    if not candidate.exists():
        if required:
            raise ValueError(f'{image_id}: missing independent annotation')
        return None
    path = _contained_file(root, relative, f'{image_id} annotation path')
    record = _read_json(path)
    if not isinstance(record, dict) or record.get('image_id') != image_id:
        raise ValueError(f'{image_id}: annotation image_id does not match its source')
    return record


def _reference(root, source):
    image_id = source['image_id']
    record = _annotation(root, image_id, required=True)
    if record.get('annotation_status') != 'verified':
        raise ValueError(f'{image_id}: labels must be independently verified, not draft')
    _nonempty(record.get('reviewer'), f'{image_id} reviewer')
    event_id = _nonempty(record.get('event_id'), f'{image_id} event_id')
    if record.get('incident') not in LABELS['incident']:
        raise ValueError(f'{image_id}: invalid incident classification')
    findings = record.get('findings')
    if not isinstance(findings, list):
        raise ValueError(f'{image_id}: findings must be a list (an empty list is allowed)')
    # Scene classification and individual asset damage are separate annotations.
    # Do not project these labels into the legacy single-primary Prediction model.
    validated = [AssetFinding.model_validate(f).model_dump() for f in findings]
    for finding in validated:
        _nonempty(finding['component'], f'{image_id} component')
        _nonempty(finding['evidence'], f'{image_id} evidence')
    return dict(record, event_id=event_id, findings=validated)


def _excluded(dataset_dir):
    root, sources = _sources(dataset_dir)
    hashes, events = set(), set()
    for source, _, digest in sources:
        hashes.add(digest)
        row_events = set()
        source_event = source.get('event_id')
        if source_event is not None:
            row_events.add(_nonempty(source_event, f"{source['image_id']} source event_id"))
        annotation = _annotation(root, source['image_id'], required=False)
        if annotation and annotation.get('event_id') is not None:
            row_events.add(_nonempty(annotation['event_id'], f"{source['image_id']} annotation event_id"))
        if not row_events:
            raise ValueError(f"Excluded source {source['image_id']} needs an event_id for leakage checks")
        # Retain provisional source groups as well as reviewer overrides. This
        # conservatively blocks an accidental rename from bypassing the check.
        events.update(row_events)
    return hashes, events


def export_study(dataset_dir, output_dir, split, exclude_dataset_dir=None):
    """Validate the complete selection before creating a fresh export directory."""
    if split not in ('development', 'test'):
        raise ValueError('split must be development or test')
    output = Path(output_dir).absolute()
    if output.exists():
        raise ValueError(f'Output directory already exists; choose a new directory: {output}')
    root, sources = _sources(dataset_dir)
    excluded_hashes, excluded_events = (
        _excluded(exclude_dataset_dir) if exclude_dataset_dir else (set(), set())
    )
    manifests, references = [], []
    seen_hashes = {}
    for source, image, digest in sources:
        image_id = source['image_id']
        reference = _reference(root, source)
        if digest in seen_hashes:
            raise ValueError(f'Exact duplicate images: {seen_hashes[digest]} and {image_id}')
        seen_hashes[digest] = image_id
        if digest in excluded_hashes:
            raise ValueError(f'{image_id}: image hash overlaps the excluded dataset')
        selected_events = {reference['event_id']}
        if source.get('event_id') is not None:
            selected_events.add(_nonempty(source['event_id'], f'{image_id} source event_id'))
        if selected_events & excluded_events:
            raise ValueError(f'{image_id}: event_id overlaps the excluded dataset')
        manifests.append(dict(
            image_id=image_id, image_path=os.path.relpath(image, output),
            event_id=reference['event_id'], split=split, sha256=digest,
        ))
        references.append(dict(
            reference, split=split, sha256=digest, source_metadata=source,
            annotation_confidence_scope='reviewer self-assessment; not a model score',
        ))
    metadata = dict(
        split=split, images=len(manifests),
        events=len({row['event_id'] for row in manifests}),
        dataset_dir=str(root),
        excluded_dataset_dir=str(Path(exclude_dataset_dir).resolve()) if exclude_dataset_dir else None,
        checks=['verified labels', 'schema validation', 'contained image paths', 'unique image IDs',
                'exact image hashes', 'event IDs and exact hashes against excluded sources, when supplied'],
        human_checks_remaining=['Verify semantic event grouping and perceptual near-duplicates.',
                                'Verify media reuse rights and attribution before publication.'],
        confidence_policy='Reviewer confidences are preserved for audit and are not model evaluation scores.',
    )
    # All data validation finishes before the first write. mkdir is exclusive;
    # existing exports are never overwritten, including in a concurrent run.
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'manifest.csv').open('x', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(manifests[0]))
        writer.writeheader()
        writer.writerows(manifests)
    with (output / 'truth.jsonl').open('x', encoding='utf-8') as file:
        for reference in references:
            file.write(json.dumps(reference, allow_nan=False) + '\n')
    with (output / 'study_metadata.json').open('x', encoding='utf-8') as file:
        json.dump(metadata, file, indent=2, allow_nan=False)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir', required=True)
    parser.add_argument('--output-dir', required=True, help='New directory; existing directories are rejected')
    parser.add_argument('--split', required=True, choices=['development', 'test'])
    parser.add_argument('--exclude-dataset-dir', help='Reject overlap with every source candidate in this dataset')
    args = parser.parse_args()
    try:
        result = export_study(args.dataset_dir, args.output_dir, args.split, args.exclude_dataset_dir)
    except (OSError, ValueError) as error:
        parser.exit(2, f'Export blocked: {error}\n')
    print(f"Exported {result['images']} verified images in {result['events']} event groups to {args.output_dir}")
    print('Human review is still required for semantic event grouping and perceptual near-duplicates.')


if __name__ == '__main__':
    main()
