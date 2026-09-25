from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
import io
from PIL import Image

def make_image():
    out = io.BytesIO()
    Image.new("RGB", (32, 32), "gray").save(out, format="PNG")
    return out.getvalue()

def test_upload_analyze_confirm_and_reset(tmp_path, monkeypatch):
    from pathlib import Path
    app_path=Path(__file__).resolve().parents[1]/'app.py'
    monkeypatch.chdir(tmp_path)
    uploaded=UploadedFile(UploadedFileRec('one','test.png','image/png',make_image()),None)
    with patch('streamlit.file_uploader',return_value=uploaded):
        app=AppTest.from_file(str(app_path), default_timeout=60).run()
        assert not app.exception
        next(item for item in app.selectbox if item.label == 'Analysis backend').set_value('demo').run()
        app.button[0].click().run()
        assert app.session_state['record']['prediction']['incident']=='uncertain'
        app.text_input[0].set_value('reviewer-test')
        app.button[1].click().run()
        assert not app.exception
        assert app.session_state['record']['human_verification']['status']=='confirmed'
        assert len(list((tmp_path/'runs').glob('*.json')))==1
    with patch('streamlit.file_uploader',return_value=None):
        app.run()
        assert 'record' not in app.session_state

def test_video_upload_analyze_and_verify(tmp_path, monkeypatch):
    from pathlib import Path
    from railreview.video import aggregate
    from railreview.backends import DemoBackend
    import json
    app_path=Path(__file__).resolve().parents[1]/'app.py'
    monkeypatch.chdir(tmp_path)
    prediction=json.loads(DemoBackend().analyze(b'',''))
    result=aggregate([dict(prediction=prediction,timestamp_seconds=0)],DemoBackend(),'test',1,.7,0)
    uploaded=UploadedFile(UploadedFileRec('video','test.mp4','video/mp4',b'fixture'),None)
    with patch('streamlit.file_uploader',return_value=None):
        app=AppTest.from_file(str(app_path), default_timeout=60).run()
        app.radio[0].set_value('Video').run()
    with patch('streamlit.file_uploader',return_value=uploaded), patch('railreview.video.run_video',return_value=result):
        app.run()
        app.button[0].click().run()
        assert not app.exception
        assert app.session_state['record']['media_type']=='video'
        app.text_input[0].set_value('video-reviewer')
        app.button[1].click().run()
        assert not app.exception
        assert app.session_state['record']['human_verification']['status']=='confirmed'

def make_video_record(states):
    """Distinct source evidence detects accidental renumbering or lost raw frames."""
    import base64
    from railreview.backends import DemoBackend
    from railreview.pipeline import prepare_image
    from railreview.schema import Prediction
    from railreview.video import aggregate

    encoded = base64.b64encode(prepare_image(make_image())).decode()
    frames = []
    for sample, state in enumerate(states, 1):
        frame = dict(id=f'frame-{sample}', frame_index=(sample - 1) * 30,
                     timestamp_seconds=float(sample - 1),
                     analyzed_image_jpeg_base64=encoded,
                     raw_response=f'Original response for sample {sample}', error=None)
        if state == 'failed':
            frame.update(prediction=None, error=f'Inference failed for sample {sample}')
        else:
            incident = {'normal': 'non_incident', 'suspected': 'non_incident',
                        'incident': 'incident', 'uncertain': 'uncertain'}[state]
            damage_status = {'normal': 'no_visible_damage', 'suspected': 'suspected_damage',
                             'incident': 'visible_damage', 'uncertain': 'suspected_damage'}[state]
            finding = dict(asset='wagon', component='body', damage_status=damage_status,
                           damage_type='deformation' if state == 'incident' else
                           'none' if state == 'normal' else 'unknown',
                           severity='moderate' if state == 'incident' else
                           'none' if state == 'normal' else 'unknown',
                           confidence=.82, evidence=f'{state} finding {sample}')
            prediction = dict(incident=incident, asset='wagon',
                              damaged_component='body' if incident == 'incident' else
                              'none' if incident == 'non_incident' else 'unknown',
                              damage_type='deformation' if incident == 'incident' else
                              'none' if incident == 'non_incident' else 'unknown',
                              severity='moderate' if incident == 'incident' else
                              'none' if incident == 'non_incident' else 'unknown',
                              confidence=.82, evidence=f'{state} scene {sample}',
                              limitations='Only this sampled frame was assessed.', findings=[finding])
            frame['prediction'] = Prediction.model_validate(prediction).model_dump()
        frames.append(frame)
    return aggregate(frames, DemoBackend(), 'fixture-video-hash', len(states), .7, .1)


def analyzed_video(result):
    """Context manager keeps inference and upload mocks active through reruns."""
    from contextlib import contextmanager
    from pathlib import Path

    @contextmanager
    def run_app():
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        uploaded = UploadedFile(UploadedFileRec('video', 'test.mp4', 'video/mp4', b'fixture'), None)
        with patch('streamlit.file_uploader', return_value=None):
            app = AppTest.from_file(str(app_path), default_timeout=60).run()
            app.radio[0].set_value('Video').run()
        with patch('streamlit.file_uploader', return_value=uploaded), patch('railreview.video.run_video', return_value=result):
            app.run()
            next(button for button in app.button if button.label == 'Analyze video').click().run()
            assert not app.exception
            yield app
    return run_app()


def displayed_sample_numbers(app):
    import re
    numbers = []
    for element in app.markdown:
        match = re.match(r'\*\*Sample (\d+) ·', element.value)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def displayed_response_text(app):
    return '\n'.join(element.value for element in [*app.markdown, *app.caption])


def displayed_image_count(app):
    # Streamlit 1.64 exposes typed "image" nodes; 1.50 uses legacy "imgs"
    # nodes. Both wrap ImageList, so count actual images, not just containers.
    elements = app.get('image') or app.get('imgs')
    return sum(len(element.proto.imgs) for element in elements)


def test_mixed_video_shows_one_normal_then_incident_responses_and_saves_all_frames(tmp_path, monkeypatch):
    import copy
    import json

    monkeypatch.chdir(tmp_path)
    result = make_video_record(['normal', 'normal', 'incident', 'normal', 'incident'])
    original_frames = copy.deepcopy(result['frames'])
    with analyzed_video(result) as app:
        assert displayed_sample_numbers(app) == [1, 3, 5]
        assert displayed_image_count(app) == 3
        text = displayed_response_text(app)
        assert 'incident finding 3' in text and 'incident finding 5' in text
        assert 'normal finding 2' not in text and 'normal finding 4' not in text
        sections = [element.value for element in app.subheader]
        assert sections.index('Analysed video samples') < sections.index('Overall event summary') < sections.index('Human verification')
        assert 'Before / after evidence' not in sections
        assert not any(button.label == 'Save image comparison' for button in app.button)
        assert app.session_state['record']['frames'] == original_frames
        assert app.session_state['record']['video_presentation']['selected_sample_numbers'] == [1, 3, 5]

        next(field for field in app.text_input if field.label == 'Reviewer ID').set_value('video-reviewer')
        next(button for button in app.button if button.label == 'Save verification').click().run()
        assert not app.exception
        assert app.session_state['record']['human_verification']['status'] == 'confirmed'
        saved_paths = list((tmp_path / 'runs').glob('*.json'))
        assert len(saved_paths) == 1
        saved = json.loads(saved_paths[0].read_text())
        assert saved['frames'] == original_frames
        assert saved['video_presentation']['selected_sample_numbers'] == [1, 3, 5]
        assert saved['asset_verification']['reviewer'] == 'video-reviewer'


def test_all_normal_video_keeps_every_image_and_one_brief_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = make_video_record(['normal', 'normal', 'normal', 'normal'])
    with analyzed_video(result) as app:
        assert displayed_sample_numbers(app) == [1, 2, 3, 4]
        assert displayed_image_count(app) == 4
        sections = [element.value for element in app.subheader]
        assert sections.count('Overall event summary') == 1
        assert sections.index('Overall event summary') < sections.index('Human verification')
        assert 'No visible incident' in [metric.value for metric in app.metric]
        text = displayed_response_text(app)
        for sample in range(1, 5):
            assert f'normal finding {sample}' not in text
            assert f'normal scene {sample}' not in text
        assert len(app.session_state['record']['frames']) == 4


def test_uncertain_suspected_and_failed_samples_remain_visible(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = make_video_record(['normal', 'normal', 'uncertain', 'suspected', 'failed'])
    with analyzed_video(result) as app:
        assert displayed_sample_numbers(app) == [1, 3, 4, 5]
        assert displayed_image_count(app) == 4
        text = displayed_response_text(app)
        assert 'uncertain finding 3' in text
        assert 'suspected finding 4' in text
        assert any('could not be assessed' in element.value.lower() for element in app.warning)
        assert [element.value for element in app.subheader].count('Overall event summary') == 1
        assert len(app.session_state['record']['frames']) == 5


def test_partial_failure_does_not_show_whole_video_as_no_incident(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = make_video_record(['normal', 'failed', 'normal'])
    with analyzed_video(result) as app:
        assert displayed_sample_numbers(app) == [1, 2]
        assert 'No visible incident' not in [metric.value for metric in app.metric]
        assert 'Needs review' in [metric.value for metric in app.metric]
        assert 'Overall event summary' in [element.value for element in app.subheader]
        assert any('could not be assessed' in element.value.lower() for element in app.warning)
        assert len(app.session_state['record']['frames']) == 3


def test_all_failed_video_keeps_images_and_explains_missing_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = make_video_record(['failed', 'failed'])
    with analyzed_video(result) as app:
        assert displayed_sample_numbers(app) == [1, 2]
        assert displayed_image_count(app) == 2
        sections = [element.value for element in app.subheader]
        assert sections.count('Overall event summary') == 1
        assert 'The event cannot be assessed' in displayed_response_text(app)
        assert 'Human verification' not in sections
        assert not any(button.label == 'Save verification' for button in app.button)
        assert 'No visible incident' not in [metric.value for metric in app.metric]
        assert app.session_state['record']['prediction'] is None
        assert len(app.session_state['record']['frames']) == 2


def test_event_confidence_and_unknown_damage_render_separately(tmp_path,monkeypatch):
    from pathlib import Path
    import json
    from railreview.assessment import project_assessment
    from railreview.backends import DemoBackend
    from railreview.pipeline import run
    data=dict(scene_context='railway',event='no_visible_incident',event_confidence=.65,evidence='Truck on a crossing; collision cannot be established.',limitations='Damage detail is unclear.',findings=[dict(asset='road_vehicle',component='body',damage_status='suspected_damage',damage_type='unknown',severity='unknown',confidence=.75,evidence='Vehicle present; damage uncertain.')])
    p,raw,notes=project_assessment(json.dumps(data))
    result=run(make_image(),DemoBackend());result.update(prediction=p.model_dump(),model_assessment=raw,derivation_notes=notes)
    app_path=Path(__file__).resolve().parents[1]/'app.py'
    monkeypatch.chdir(tmp_path)
    uploaded=UploadedFile(UploadedFileRec('image','test.png','image/png',make_image()),None)
    with patch('streamlit.file_uploader',return_value=uploaded),patch('railreview.pipeline.run',return_value=result):
        app=AppTest.from_file(str(app_path),default_timeout=60).run()
        app.button[0].click().run()
        assert not app.exception
        assert [m.value for m in app.metric]==['No visible incident','Not assessable','65%']
        assert any('Asset confidence: 75%' in c.value for c in app.caption)


def test_public_review_download_does_not_save_personal_report(tmp_path, monkeypatch):
    from pathlib import Path
    from railreview.backends import DemoBackend
    from railreview.pipeline import run
    from railreview.usage import totals
    app_path = Path(__file__).resolve().parents[1] / 'app.py'
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RAILREVIEW_PUBLIC', '1')
    monkeypatch.setenv('RAILREVIEW_USAGE_DB', str(tmp_path / 'usage.sqlite3'))
    record = run(make_image(), DemoBackend())
    uploaded = UploadedFile(UploadedFileRec('one', 'test.png', 'image/png', make_image()), None)
    with patch('streamlit.file_uploader', return_value=uploaded), patch('railreview.pipeline.run', return_value=record):
        app = AppTest.from_file(str(app_path), default_timeout=60).run()
        app.button[0].click().run()
        assert not app.exception
        assert totals(tmp_path / 'usage.sqlite3')['completed_analyses'] == 1
        app.run()
        assert totals(tmp_path / 'usage.sqlite3')['completed_analyses'] == 1
        app.text_input[0].set_value('test-reviewer')
        app.button[1].click().run()
        assert not app.exception
        assert app.session_state['record']['human_verification']['status'] == 'confirmed'
        assert not (tmp_path / 'runs').exists()
