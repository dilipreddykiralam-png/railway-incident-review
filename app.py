import hashlib
import base64
import json
from pathlib import Path
import streamlit as st
from railreview.backends import get_backend
from railreview.pipeline import run, verify, prepare_image
from railreview.schema import LABELS
from railreview.video import run_video
from railreview.summary import asset_findings, ASSETS
from railreview.review import review_assets
from railreview.schema import AssetFinding
from railreview.video_presentation import video_presentation
from railreview.ui_results import render_video_samples, render_video_summary
from railreview.metrics import display_metrics

st.set_page_config(page_title='Railway Incident Review', layout='wide')
st.title('Railway image and video review')
st.caption('Qwen2.5-VL 7B · Evidence-linked findings · Human verification')
backend = st.sidebar.selectbox('Analysis backend', ['vlm','demo'])
chosen_model = st.sidebar.selectbox('Local vision model', ['qwen2.5vl:7b'])
st.sidebar.markdown('[Label images independently](http://127.0.0.1:8504/)')
threshold = st.sidebar.slider('Priority review threshold', 0.0, 1.0, 0.7, 0.05)
st.sidebar.caption('Classification confidence and asset confidence are separate model estimates. Neither is measured accuracy. Unknown damage is shown as Not assessable; missing confidence is shown as Not reported.')
if backend == 'demo': st.warning('DEMO: fixed uncertain output. No image understanding is performed.')
else:
    st.info('Images are sent to the configured VLM endpoint when you click Analyze.')
    st.caption('Qwen2.5-VL 7B provides provisional findings. Inspect the evidence and confirm or correct each result.')
media = st.radio('Upload type', ['Image', 'Video'], horizontal=True)
count = 6
if media == 'Video':
    count = st.slider('Frames to analyze', 2, 12, 6)
    st.caption('Up to 100 MB / 10 minutes. Frames are sampled across the clip; brief incidents may be missed. More frames take longer. Audio is not analyzed.')
upload = st.file_uploader('Upload one railway ' + media.lower(), type=['jpg','jpeg','png','webp'] if media == 'Image' else ['mp4','mov','avi','mkv','webm'])
if upload:
    data = upload.getvalue()
    fingerprint = ('multi-asset-v4', hashlib.sha256(data).hexdigest(), backend, chosen_model, threshold, media, count)
    if st.session_state.get('fingerprint') != fingerprint:
        st.session_state.pop('record', None)
        st.session_state.fingerprint = fingerprint
    try:
        if media == 'Image':
            preview = prepare_image(data)
            st.image(preview, width=600)
        else:
            if len(data) > 100*1024*1024: raise ValueError('Video must be under 100 MB.')
            st.video(data)
    except Exception as exc:
        st.error('Invalid upload: ' + str(exc))
        st.stop()
    if st.button('Analyze ' + media.lower(), type='primary'):
        st.session_state.pop('record', None)
        try:
            with st.spinner('Analyzing ' + media.lower() + '…'):
                if media == 'Video':
                    progress = st.progress(0, text='Sampling video…')
                    st.session_state.record = run_video(data, get_backend(backend, chosen_model), threshold, count, lambda n,total: progress.progress(n/total, text=f'Analyzed frame {n} of {total}'))
                else:
                    st.session_state.record = run(data, get_backend(backend, chosen_model), threshold)
        except Exception as e: st.error(str(e))
    record = st.session_state.get('record')
    if record:
        record.setdefault('source_filename', Path(upload.name).name)
        is_video = record.get('media_type') == 'video'
        if is_video:
            presentation = video_presentation(record)
            record['video_presentation'] = presentation
            render_video_samples(record, presentation)
            render_video_summary(record, presentation)
        if record['error']:
            st.error('This analysis failed validation. The original response is preserved in the download; no valid prediction was saved. Check Technical details or rerun the analysis.')
            with st.expander('Technical details'):
                st.write(record['error'])
        else:
            p = record['prediction']
            if record.get('derivation_notes'):
                st.warning('The scene and asset claims need review: ' + ', '.join(record['derivation_notes']).replace('_',' '))
            if len(record.get('attempts', [])) > 1:
                st.info('The model corrected an invalid first response. Both attempts are included in the download.')
            findings = asset_findings(record)
            if not is_video:
                st.subheader('Railway findings')
                a,b,c = st.columns(3)
                metrics = display_metrics(record)
                record['display_metrics'] = metrics
                a.metric('Model classification', metrics['classification'])
                b.metric('Visual damage severity', metrics['severity'])
                c.metric(metrics['confidence_label'], 'Not reported' if metrics['confidence'] is None else f"{metrics['confidence']:.0%}")
                st.caption(metrics['confidence_note'])
                if metrics['classification'] != metrics['review_classification']:
                    st.warning('Review classification: ' + metrics['review_classification'] + '. The model classification above is its original answer; conflicting evidence still needs human review.')
                if metrics['severity'] == 'Not assessable':
                    st.caption('The model did not establish a visible damage severity. An incident or obstruction can be present without visible asset damage.')
                st.subheader('Assets with visible damage — model claims, awaiting verification')
                damaged = [f for f in findings if f['damage_status'] == 'visible_damage']
                if not damaged:
                    st.write('No asset has a validated visible-damage finding. This does not prove absence of damage.')
                for finding in damaged + [f for f in findings if f not in damaged]:
                    st.markdown('**' + ASSETS[finding['asset']] + ' — ' + finding['damage_status'].replace('_',' ') + '**')
                    st.write('• Component: ' + finding['component'] + '; damage: ' + finding['damage_type'].replace('_',' ') + '; severity: ' + finding['severity'])
                    st.caption(f"Asset confidence: {finding['confidence']:.0%} (model estimate; minimum across grouped samples).")
                    descriptions = list(dict.fromkeys(source['evidence'] for source in finding['sources']))
                    for description in descriptions[:3]:
                        st.write('• ' + description)
                    st.caption('Supporting samples: ' + ', '.join(str(source['sample']) for source in finding['sources']))
                    with st.expander('View images supporting this finding'):
                        columns = st.columns(3)
                        for index, source in enumerate(finding['sources']):
                            frame = record.get('frames', [record])[source['sample']-1]
                            image = frame.get('analyzed_image_jpeg_base64')
                            with columns[index % 3]:
                                if image:
                                    st.image(base64.b64decode(image), caption='Sample ' + str(source['sample']), use_container_width=True)
                                elif media == 'Image':
                                    st.image(preview, caption='Uploaded image', use_container_width=True)
                                st.caption(source['evidence'])
                st.caption('Collision involvement is not proof of visible damage. Findings are model claims until reviewed. Multiple findings do not imply multiple distinct physical vehicles.')
                st.caption(p['limitations'])
                st.caption('Review reasons: ' + ', '.join(record['review_reasons']))
            st.subheader('Human verification')
            st.caption('Edit, add or delete asset rows below. Keep uncertain damage separate. Use sample numbers to link your observations to images. Original model findings are preserved.')
            with st.form('review_' + record['id']):
                reviewer = st.text_input('Reviewer ID')
                corrected = dict(p)
                for field, options in LABELS.items():
                    corrected[field] = st.selectbox(field.replace('_',' ').title(), options, index=options.index(p[field]), format_func=(lambda value: ASSETS[value]) if field == 'asset' else (lambda value: value.replace('_', ' ').capitalize()))
                review_rows = [{**{k: f[k] for k in AssetFinding.model_fields}, 'samples': ','.join(str(source['sample']) for source in f['sources'])} for f in findings]
                import pandas as pd
                st.caption('For each added row, enter confidence from 0 to 1 and a short evidence description. Scroll the table horizontally to see every field. Completely empty rows are ignored.')
                edited_assets = st.data_editor(pd.DataFrame(review_rows, columns=list(AssetFinding.model_fields) + ['samples']), num_rows='dynamic', hide_index=True,
                    column_config={
                        'asset': st.column_config.SelectboxColumn('Asset', options=list(ASSETS), required=True),
                        'damage_status': st.column_config.SelectboxColumn('Damage status', options=['visible_damage','suspected_damage','involved_no_visible_damage','no_visible_damage'], required=True),
                        'damage_type': st.column_config.SelectboxColumn('Damage type', options=LABELS['damage_type'], required=True),
                        'severity': st.column_config.SelectboxColumn('Severity', options=LABELS['severity'], required=True),
                        'component': st.column_config.TextColumn('Component', required=True),
                        'evidence': st.column_config.TextColumn('Evidence — what you see', required=True, width='large'),
                        'confidence': st.column_config.NumberColumn('Reviewer confidence (0–1)', min_value=0.0, max_value=1.0, required=True),
                        'samples': st.column_config.TextColumn('Supporting sample numbers (e.g. 2,3)')})
                notes = st.text_area('Review notes')
                if st.form_submit_button('Save verification'):
                    try:
                        reviewed = verify(record, corrected, reviewer, notes)
                        reviewed['asset_verification'] = review_assets(record, edited_assets.to_dict('records'), reviewer)
                        folder = Path('runs'); folder.mkdir(exist_ok=True)
                        # Unique event file: repeated reviews never overwrite previous reviews.
                        import uuid
                        path = folder / f"{record['id']}-review-{uuid.uuid4().hex}.json"
                        path.write_text(json.dumps(reviewed, indent=2))
                        st.session_state.record = record = reviewed
                        st.success('Verification saved: ' + str(path))
                    except Exception as e: st.error(str(e))
            if record.get('asset_verification'):
                st.subheader('Human-reviewed asset list')
                for finding in record['asset_verification']['findings']:
                    st.write('• ' + ASSETS[finding['asset']] + ' — ' + finding['damage_status'].replace('_',' ') + ': ' + finding['evidence'])
            st.write('Review status:', record['human_verification']['status'])
        st.download_button('Download result JSON', json.dumps(record, indent=2), file_name=record['id']+'.json', mime='application/json')
else:
    st.session_state.pop('record', None)
