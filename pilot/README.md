# Independent reference labels

This folder starts empty. Add images you have permission to use under `images/`,
and list them in `sources.json`. Do not include model answers in the label record.

Example source record (replace every placeholder with real metadata):

```json
[
  {
    "image_id": "case_001",
    "image_path": "images/case_001.jpg",
    "event_id": "unique_accident_or_scene_group",
    "source": "https://example.com/replace-with-real-source",
    "license": "Replace with verified licence or permission"
  }
]
```

Start `streamlit run label_app.py --server.port 8504` from the repository root.
Annotations are written locally under `annotations/` and ignored by Git. Use
separate dataset folders for independent annotators; the application stores one
current annotation per image. See `docs/EVALUATION.md` for export and evaluation.

Do not commit private images or identify evaluation labels as ground truth until
they have been independently checked. Images from the same incident belong to
the same event group.
