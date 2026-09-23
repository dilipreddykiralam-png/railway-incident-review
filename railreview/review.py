"""Independent human asset review; never overwrites model findings."""
import math
from pydantic import ValidationError
from .schema import AssetFinding
from .pipeline import now


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, float) and math.isnan(value))


def validate_review_row(row, number):
    values = {k: row.get(k) for k in AssetFinding.model_fields}
    if all(blank(value) for value in values.values()) and blank(row.get('samples')):
        return None
    missing = [k.replace('_', ' ') for k, value in values.items() if blank(value)]
    if missing:
        raise ValueError(f"Asset row {number}: please fill in {', '.join(missing)}. Confidence uses 0–1; evidence is a short description of what you see.")
    try:
        if isinstance(values['confidence'], bool): raise ValueError()
        values['confidence'] = float(values['confidence'])
        if not math.isfinite(values['confidence']) or not 0 <= values['confidence'] <= 1: raise ValueError()
    except (TypeError, ValueError):
        raise ValueError(f'Asset row {number}: confidence must be a number from 0 to 1 (for example, 0.8).') from None
    try:
        return AssetFinding.model_validate(values).model_dump()
    except ValidationError as exc:
        details = '; '.join(error['msg'].removeprefix('Value error, ') for error in exc.errors(include_url=False))
        raise ValueError(f'Asset row {number}: {details}') from None


def review_assets(record, rows, reviewer):
    if not reviewer.strip(): raise ValueError('Reviewer ID is required')
    validated=[]
    for number, row in enumerate(rows, 1):
        finding = validate_review_row(row, number)
        if finding is None: continue
        references = '' if blank(row.get('samples')) else str(row['samples']).strip()
        try:
            ids=[int(s.strip()) for s in references.split(',') if s.strip()]
        except ValueError:
            raise ValueError(f'Asset row {number}: use comma-separated sample numbers, such as 1,2.') from None
        count=len(record.get('frames',[record]))
        if any(n<1 or n>count for n in ids): raise ValueError(f'Asset row {number}: sample numbers must be between 1 and {count}.')
        finding.update(samples=ids,source='human_review')
        validated.append(finding)
    return dict(status='reviewed',reviewer=reviewer.strip(),reviewed_at=now(),findings=validated)
