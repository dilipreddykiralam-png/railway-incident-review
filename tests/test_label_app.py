from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_label_app_loads_without_model_predictions(tmp_path, monkeypatch):
    import json
    from PIL import Image
    Image.new('RGB',(32,32),'gray').save(tmp_path/'sample.png')
    (tmp_path/'sources.json').write_text(json.dumps([dict(image_id='sample',image_path='sample.png',
        event_id='sample-event',source='https://example.com/synthetic-test-fixture',license='Synthetic test fixture')]))
    monkeypatch.setenv('RAILREVIEW_LABEL_DATASET', str(tmp_path))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'label_app.py'),default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value=='Label the railway pilot images'
    assert app.selectbox[0].value==0
    assert not any('Model prediction' in item.value for item in app.subheader)

def test_empty_custom_dataset_has_clear_message(tmp_path, monkeypatch):
    (tmp_path/'sources.json').write_text('[]')
    monkeypatch.setenv('RAILREVIEW_LABEL_DATASET', str(tmp_path))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'label_app.py'),default_timeout=60).run()
    assert not app.exception
    assert 'no images yet' in app.info[0].value
    assert not app.selectbox
