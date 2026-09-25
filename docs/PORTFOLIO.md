# Portfolio notes

Use these descriptions to explain the implemented work. The software test count is a code-verification result, not model accuracy. Update these notes when independent evaluation results are available.

## Repository About description

Railway image and video review with Qwen2.5-VL 7B: structured damage findings, supporting frames, human verification and evaluation tools. 120 automated software tests passed.

## Short project bio

Built a railway incident review application using Qwen2.5-VL 7B and Ollama. The application analyses images and sampled video frames, produces structured asset and damage findings, and lets a human reviewer confirm or correct the results. Original predictions and corrections remain separate for evaluation. Includes attributed examples, saved model outputs and 120 passing automated software tests; recognition accuracy requires independent dataset evaluation.

## Resume bullets

- Built a Python/Streamlit application integrating Qwen2.5-VL 7B through local Ollama for railway image and sampled-video assessment.
- Implemented constrained JSON output, Pydantic validation, one validation retry, multi-asset reporting and timestamped visual evidence.
- Designed human verification that preserves model predictions separately from corrected reports, with independent labelling and repeatable batch evaluation tools.
- Verified the software with 120 automated tests covering validation, video presentation, human corrections, dataset integrity and evaluation calculations.

## Interview walkthrough

1. Explain the task: turning railway incident media into a structured draft report that an expert can check.
2. Show one supplied image, its actual saved model output and the evidence for each finding.
3. Demonstrate removing an unsupported claim or adding a missed asset through human verification.
4. Explain how the original prediction is retained and how independent reference labels are used for evaluation.
5. Discuss failure modes: invented damage, unclear images, missed brief video events and confidence that is not calibrated accuracy.
6. Describe the next engineering step: improve frame selection or evaluate a detector adapter using the existing validation and review pipeline.

The implemented contribution is the application and its assessment/review workflow. Qwen is a pretrained external model; this project does not claim to have developed or fine-tuned it. No validated production-safety, accuracy or time-saving claim is included.
