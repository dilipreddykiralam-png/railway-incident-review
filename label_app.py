"""Independent labels: intentionally does not show model outputs."""
import json
import os
from pathlib import Path
import pandas as pd
import streamlit as st
from railreview.schema import AssetFinding,LABELS
from railreview.review import validate_review_row
ROOT=Path(os.getenv('RAILREVIEW_LABEL_DATASET', str(Path(__file__).parent/'pilot'))).expanduser().resolve()
st.set_page_config(page_title='Railway pilot labels',layout='wide')
st.title('Label the railway pilot images')
st.caption('Independent reference labels · Model predictions are hidden')
source=ROOT/'sources.json'
if not source.exists():
    st.info('Candidate image collection is not yet available.');st.stop()
rows=json.loads(source.read_text())
if not rows:
    st.info('This dataset has no images yet. Add the image files and their source records to sources.json, then refresh.');st.stop()
chosen=st.selectbox('Image',range(len(rows)),format_func=lambda i:rows[i]['image_id'])
row=rows[chosen]
st.image(str(ROOT/row['image_path']),width=850)
st.markdown('[Source and attribution]('+row['source']+') · '+row['license'])
folder=ROOT/'annotations';folder.mkdir(exist_ok=True)
path=folder/(row['image_id']+'.json')
old=json.loads(path.read_text()) if path.exists() else {}
with st.form('label_'+row['image_id']):
 reviewer=st.text_input('Reviewer ID',old.get('reviewer',''))
 event=st.text_input('Event/group ID (same accident or near-duplicate source = same ID)',old.get('event_id',row.get('event_id','')))
 incident=st.selectbox('Scene classification',LABELS['incident'],index=LABELS['incident'].index(old.get('incident','uncertain')))
 st.caption('Add each relevant asset. Mark visible damage only when you can point to evidence. Suspected damage and involvement alone are separate statuses. Use consistent component names for exact scoring.')
 data=st.data_editor(pd.DataFrame(old.get('findings',[]),columns=list(AssetFinding.model_fields)),num_rows='dynamic',hide_index=True,column_config={
 'asset':st.column_config.SelectboxColumn(options=LABELS['asset']),
 'damage_status':st.column_config.SelectboxColumn(options=['visible_damage','suspected_damage','involved_no_visible_damage','no_visible_damage']),
 'damage_type':st.column_config.SelectboxColumn(options=LABELS['damage_type']),
 'severity':st.column_config.SelectboxColumn(options=LABELS['severity']),
 'confidence':st.column_config.NumberColumn('Reviewer confidence',min_value=0.0,max_value=1.0)})
 verified=st.checkbox('I checked these labels independently of model output',value=False)
 if st.form_submit_button('Save labels'):
  try:
   if not reviewer.strip() or not event.strip():raise ValueError('Reviewer and event ID are required')
   findings=[]
   for number,item in enumerate(data.to_dict('records'),1):
    finding=validate_review_row(item,number)
    if finding is not None:findings.append(finding)
   record=dict(image_id=row['image_id'],reviewer=reviewer.strip(),event_id=event.strip(),incident=incident,findings=findings,annotation_status='verified' if verified else 'draft',split='unassigned')
   path.write_text(json.dumps(record,indent=2));st.success('Saved. Select the next image above.')
  except Exception as e:st.error(str(e))
records=[json.loads(p.read_text()) for p in folder.glob('*.json')]
st.write(f'{sum(r["annotation_status"]=="verified" for r in records)} of {len(rows)} images verified')
st.download_button('Download reference labels', '\n'.join(json.dumps(r) for r in records),file_name='truth.jsonl')
