# Evaluation and reproducibility

## What has been tested

**109 automated software tests passed** for this repository's publication check. The tests exercise output validation, missing values, review preservation, frame presentation, dataset export and metric behavior. They can run without an active model:

```bash
python -m pytest -q
```

The [saved local test report](software-test-results.json) records the macOS/Python 3.9.6 publication run. [GitHub Actions](https://github.com/dilipreddykiralam-png/railway-incident-review/actions/workflows/tests.yml) independently installs the declared dependencies and runs the same checks on Linux with Python 3.11 for each push. Use the workflow result for the current commit's status.

The [saved sample runs](SAMPLE_RESULTS.md) demonstrate Qwen2.5-VL 7B inference and document observed outputs. They are a small demonstration, not an independently labelled benchmark. This project does not claim a measured overall damage-recognition accuracy, a proven time saving or improved safety.

## Prepare independent reference labels

Use images with documented reuse rights and varied scenes, including normal railway scenes. Define what counts as an incident and visible damage before evaluating. Keep all views of one accident and near-duplicate frames in the same dataset group. Do not reuse development images as unseen test examples.

Create a dataset directory with this structure:

```text
data/my-dataset/
  sources.json
  images/
    image-001.jpg
  annotations/          Created by the labelling app
```

`sources.json` is a list of records. Replace the illustrative values below with real attribution and event-group information:

```json
[
  {
    "image_id": "image-001",
    "image_path": "images/image-001.jpg",
    "event_id": "event-001",
    "source": "https://example.org/replace-with-the-actual-source-page",
    "license": "Replace with the verified reuse terms and attribution"
  }
]
```

Start the label interface from the repository root in an activated environment:

```bash
export RAILREVIEW_LABEL_DATASET=data/my-dataset
python -m streamlit run label_app.py --server.address 127.0.0.1 --server.port 8504
```

For PowerShell use `$env:RAILREVIEW_LABEL_DATASET = "data/my-dataset"` in place of the `export` line.

Open [http://127.0.0.1:8504](http://127.0.0.1:8504). Label the image **without viewing its model answer**. Record the reviewer, event group, scene classification and relevant asset findings. Enter evidence for each finding. Use `visible_damage` only for damage supported by the image. The labelling app deliberately hides model predictions; ideally, a second knowledgeable reviewer checks the labels and resolves disagreements.

The “independently checked” checkbox records a review declaration. Software cannot establish that a reviewer actually worked independently.

## Export a frozen test set

After every selected source image has a verified annotation:

```bash
python -m railreview.prepare_study \
  --dataset-dir data/my-dataset \
  --output-dir data/test-export \
  --split test
```

If you also have a development dataset, add `--exclude-dataset-dir data/development` to reject exact-image and event-ID overlap. The export includes `manifest.csv`, `truth.jsonl` and study metadata. It rejects duplicate image IDs, exact duplicate images, draft/missing labels and invalid annotations. Human review is still needed to catch visually similar images and inconsistently named event groups.

The export directory must be new. Images remain in their source dataset; do not move that dataset after exporting the relative-path manifest.

## Run Qwen2.5-VL 7B

Start Ollama with the model installed, then run:

```bash
mkdir -p runs/evaluation
export VLM_MODEL=qwen2.5vl:7b
export VLM_BASE_URL=http://localhost:11434/v1
export VLM_API_STYLE=ollama
python -m railreview.batch \
  --manifest data/test-export/manifest.csv \
  --backend vlm \
  --output runs/evaluation/qwen7b-predictions.jsonl
```

On PowerShell, create `runs/evaluation` and set the same three variables using `$env:NAME = "value"`. The Python invocation and arguments are the same; enter them on one line or use PowerShell continuation syntax.

Batch inference does not read the reference answers. Each line contains the original model record or an error. Existing output files are not overwritten; use a new filename for each experiment. Keep the model tag, Ollama version, prompt version, schema, environment and hardware recorded with the run. The default `num_ctx` is 8192, `num_predict` is 2048 and temperature is 0; these settings do not guarantee identical outputs across environments.

## Score classification and damage separately

The default scene scorer uses the application's consistency-checked `prediction.incident` field:

```bash
python -m railreview.evaluate_scene \
  --truth data/test-export/truth.jsonl \
  --predictions runs/evaluation/qwen7b-predictions.jsonl \
  --classification-source projected \
  --output runs/evaluation/scene-metrics.json
```

To evaluate the model's original `model_assessment.event` instead, run the same command with `--classification-source model` and a different output filename. Report which source you used; the scorer does not silently fall back between them.

Then score visible-damage findings:

```bash
python -m railreview.evaluate_assets \
  --truth data/test-export/truth.jsonl \
  --predictions runs/evaluation/qwen7b-predictions.jsonl \
  --output runs/evaluation/asset-metrics.json
```

| Result | What it measures |
|---|---|
| Scene accuracy and macro-F1 | Incident versus non-incident classification on definite reference labels |
| Normal-scene false-positive rate | Normal reference scenes incorrectly labelled as incidents |
| Abstention and failure rates | Uncertain decisions and missing/failed inference |
| Asset precision/recall/F1 | Correct, extra and missed visible-damage asset findings |
| Asset + damage matching | Whether the asset and its damage type are correct together |
| Full finding matching | Exact asset, component, damage type and severity agreement |

The scene denominator includes all definite incident/non-incident reference images, including failures and abstentions. Uncertain reference labels are reported separately. Asset scoring uses exact multiset matching within each image and only findings marked `visible_damage`. It is not object localisation or unique physical asset tracking. Consistent reference component terminology matters for exact matching.

Human corrections are not substituted into these model scores. Per-asset or per-frame confidence must not be interpreted as calibrated incident probability; no such calibration claim is made here.

## Evaluate the review workflow

Use a predefined subset for review. Record what the reviewer adds, removes or changes and, if relevant, measure review time. Compare the final reviewed report with the independent reference labels. More findings are not automatically better: additions must also be correct.

To claim time savings, include a fair manual-reporting baseline and document the timing protocol. Otherwise report review observations without a time-saving claim. Reviewer-confirmed corrections are not equivalent to independent ground truth.

Videos should be reported as separate sampled-frame case studies unless a video-level evaluation protocol is defined. Include failed and uncertain frames, sample count and timestamps. Do not count neighbouring frames of one event as independent unseen cases or infer complete-video absence of incidents from normal sampled frames.

## Publishing results

Report dataset size, event groups, source selection, labels, model/settings, failures, abstentions and representative mistakes alongside successful examples. State whether the media may have been present in the pretrained model's unknown training data. Keep source rights and attribution with any reproduced image.

Do not report software test counts as visual accuracy. Do not replace missing experiments with illustrative numbers. Save the original predictions before human review so results remain auditable.
