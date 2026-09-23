"""Video report presentation; original frame analyses remain unchanged."""
import base64
import streamlit as st

from .metrics import display_metrics, SEVERITIES
from .summary import ASSETS


def _image(frame, sample):
    encoded = frame.get('analyzed_image_jpeg_base64')
    if encoded:
        try:
            st.image(base64.b64decode(encoded, validate=True), use_container_width=True)
            return
        except (ValueError, TypeError):
            pass
    st.caption(f'Sample {sample}: image unavailable. Analyze again to include the sampled image.')


def _frame_response(frame, state, review_reason):
    if state == 'failed':
        st.warning('This sample could not be assessed. It is not counted as non-incident.')
        with st.expander('Sample error details'):
            st.write(frame.get('error') or 'No valid model response was returned.')
        return
    prediction = frame['prediction']
    metrics = display_metrics(frame)
    label = {'incident': 'Incident', 'non_incident': 'No visible incident',
             'needs_review': 'Needs review'}[state]
    st.write('Classification: ' + label)
    if state == 'needs_review':
        st.caption('Original model classification: ' + metrics['classification'])
        st.caption(review_reason)
    if state == 'non_incident':
        return
    st.caption('Visual damage severity: ' + metrics['severity'])
    confidence = 'Not reported' if metrics['confidence'] is None else f"{metrics['confidence']:.0%}"
    st.caption(metrics['confidence_label'] + ': ' + confidence + ' (model estimate)')
    if prediction.get('evidence'):
        st.write('Reason: ' + prediction['evidence'])
    for finding in prediction.get('findings', []):
        st.markdown('**' + ASSETS.get(finding['asset'], finding['asset']) + ' — '
                    + finding['damage_status'].replace('_', ' ') + '**')
        st.caption('Component: ' + finding['component'] + ' · Damage: '
                   + finding['damage_type'].replace('_', ' ') + ' · Severity: '
                   + SEVERITIES.get(finding['severity'], finding['severity']))
        st.caption(f"Asset confidence: {finding['confidence']:.0%} (model estimate)")
        st.write('• ' + finding['evidence'])
    if frame.get('derivation_notes'):
        st.caption('Review flags: ' + ', '.join(frame['derivation_notes']).replace('_', ' '))


def render_video_samples(record, presentation):
    st.subheader('Analysed video samples')
    if presentation['mode'] == 'all_non_incident':
        st.caption('All sampled images are shown below. Their findings are combined into one brief summary.')
    else:
        hidden = presentation['hidden_normal_count']
        if hidden:
            st.caption(f'One representative non-incident sample is shown; {hidden} additional '
                       'non-incident sample(s) are omitted from this view. All original samples '
                       'and responses remain in the result download.')
        st.caption('Incident samples and samples needing review keep their individual responses. '
                   'Sample numbers refer to the original video sampling order.')
    entries = {item['sample']: item for item in presentation['samples']}
    for index, sample in enumerate(presentation['selected_sample_numbers']):
        if index % 2 == 0:
            columns = st.columns(2)
        frame = record['frames'][sample - 1]
        timestamp = frame.get('timestamp_seconds')
        when = f'approximately {timestamp:.2f}s' if isinstance(timestamp, (int, float)) else 'time unavailable'
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f'**Sample {sample} · {when}**')
                _image(frame, sample)
                if presentation['mode'] != 'all_non_incident' and sample == presentation['representative_normal_sample']:
                    st.caption('Representative non-incident sample')
                if presentation['mode'] != 'all_non_incident':
                    _frame_response(frame, entries[sample]['state'], entries[sample]['reason'])


def render_video_summary(record, presentation):
    st.subheader('Overall event summary')
    st.write(presentation['summary'])
    if record.get('prediction'):
        metrics = display_metrics(record)
        a, b, c = st.columns(3)
        # Review flags take precedence in this display; original aggregate and
        # frame labels stay intact in the exported record.
        classification = metrics['classification']
        if presentation['counts']['incident'] == 0 and (
                presentation['counts']['needs_review'] or presentation['counts']['failed']):
            classification = 'Needs review'
        record['display_metrics'] = dict(metrics, classification=classification,
                                        aggregate_classification=metrics['classification'])
        a.metric('Sampled-video classification', classification)
        b.metric('Visual damage severity', metrics['severity'])
        c.metric(metrics['confidence_label'], 'Not reported' if metrics['confidence'] is None
                 else f"{metrics['confidence']:.0%}")
        st.caption(metrics['confidence_note'])
    if presentation['mode'] != 'all_non_incident':
        for point in presentation['description_points']:
            st.write('• ' + point)
    st.caption('This summary describes the sampled images, not every moment of the video. '
               'Findings remain model claims until human verification.')
