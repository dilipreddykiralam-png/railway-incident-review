# Architecture

The application separates image preparation, model inference, schema validation, presentation and human review. The default inference path is Qwen2.5-VL 7B served locally through Ollama.

## Processing an image

1. `pipeline.prepare_image` checks the image format, byte size and pixel count, applies EXIF orientation, converts to RGB and creates a JPEG with a maximum side of 1536 pixels.
2. `VLMBackend` sends the prepared image and versioned assessment prompt to Ollama's native `/api/chat` endpoint. Generation uses temperature 0 and a constrained JSON schema.
3. `SceneAssessment` validates the model's scene event, evidence and individual asset findings. Scene classification and visible physical damage are distinct: an incident can involve an asset without showing measurable damage to it.
4. `project_assessment` produces the validated compatibility fields, preserves the full assessment and adds review notes for conflicting claims. A structurally valid response can still be visually wrong.
5. An invalid response gets at most one additional validation attempt. Both attempts are retained. If it still fails, the record contains an error, not a fabricated successful prediction.
6. The interface displays the results and supporting evidence. Human changes are saved separately from the original prediction.

## Processing a video

`video.sample_frames` samples across the clip using OpenCV. The user chooses 2–12 frames; the default is 6. Each frame follows the image pipeline. Its approximate timestamp, frame index and prepared JPEG are retained alongside its result.

`video_presentation` controls the display independently of the saved records:

- Mixed output: one representative non-incident sample, incident samples and samples needing review.
- All valid samples non-incident: sampled images plus one brief combined summary.
- Uncertain and failed samples remain visible for review.

Individual responses and one overall event summary lead into human verification. Hidden repetitive non-incident responses are still present in the saved JSON. The combined report is a rule-based summary of sampled image findings, not a separate model understanding of every moment of the video. It does not track physical objects across frames or prove an event's cause.

## Main modules

| Module | Responsibility |
|---|---|
| `backends.py` | Backend interface, local Ollama requests and fixed demo fixture |
| `assessment.py` | Versioned assessment prompt, constrained schema and projection rules |
| `schema.py` | Labels, findings, prediction validation and review rules |
| `pipeline.py` | Image preparation, attempts, audit metadata and verification |
| `video.py` | Video decoding, sampling, per-frame processing and aggregation |
| `video_presentation.py`, `ui_results.py` | Frame selection for display and combined summaries |
| `summary.py`, `metrics.py` | Finding grouping and correctly scoped display values |
| `review.py` | Editable asset-row validation and human corrections |
| `prepare_study.py` | Verified-label export and basic split-overlap checks |
| `batch.py` | Image manifest to original prediction JSONL |
| `evaluate_scene.py`, `evaluate_assets.py` | Scene and visible-damage finding evaluation |

## Record provenance

Image records preserve original and prepared-image hashes, a record ID, timestamps, model and backend identifiers, prompt/schema hashes, generation settings, raw response attempts, validated predictions, latency and human-review status. Video records add sampled images, per-frame records and video metadata. This makes a finding traceable to the input and configuration used for that run.

The model's scene assessment, the application's consistency-checked projection and the human-reviewed result are different records. Evaluation must explicitly choose the relevant original field; it must not silently substitute human corrections.

## Confidence and severity

Scene-classification confidence estimates the model's certainty about its scene decision. Asset confidence estimates its certainty about a particular asset finding. Neither is calibrated accuracy. A selected-frame estimate in a video must not be reported as a probability for the complete video.

Severity is a visual description. Unknown severity is shown as “Not assessable”; missing confidence is shown as “Not reported.” Human review is required even when a reported confidence is high.

## Adding a detector

The `Backend` protocol exposes `analyze(image_bytes, mime) -> raw JSON string`. A future CV adapter can translate detector results into the supported output contract and declare its model and backend identifiers. This leaves input preparation, record keeping, human review and evaluation reusable. A detector would need to provide compatible semantics or extend the schema; detection boxes alone do not supply damage severity or incident reasoning.

## Boundaries

- No railway-specific model training is included.
- No automatic retraining occurs when a reviewer saves changes.
- No audio interpretation, object tracking or continuous video understanding is implemented.
- Earlier/later comparison utilities are not a current advertised application workflow.
- The default service is local; a different configured endpoint changes where the image is sent.
