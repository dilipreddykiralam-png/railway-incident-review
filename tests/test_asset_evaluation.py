import pytest
from railreview.evaluate_assets import score

def test_asset_matching_false_positive_and_missing():
 f=dict(asset='wagon',component='body',damage_type='deformation',severity='severe',damage_status='visible_damage')
 truth=[dict(image_id='a',annotation_status='verified',findings=[f]),dict(image_id='b',annotation_status='verified',findings=[f])]
 predictions=[dict(image_id='a',prediction={'findings':[f,dict(f,asset='track')]})]
 result=score(truth,predictions)
 assert result['asset']['tp']==1 and result['asset']['fp']==1 and result['asset']['fn']==1
 assert result['asset']['f1']==.5 and result['failures_or_missing']==1
 with pytest.raises(ValueError):score([dict(truth[0],annotation_status='draft')],predictions)
