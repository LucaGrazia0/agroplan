from datetime import date
from copy import deepcopy
from io import BytesIO
import base64
import json
from uuid import uuid4

import pytest
from PIL import Image
from crop_analysis import build_crop_review
from evidence_engine import integrate
from photo_analysis import clean_photo, model_info, predict

TODAY=date(2026,11,25)


def report(details=None, crop='frumento_tenero', **changes):
    record=dict(id='record-1', observed_at=TODAY.isoformat(),symptoms=['spots'],severity='mild',notes='',
                diagnostic_details=details)
    record.update(changes)
    cycle={'crop':crop,'sowing_date':'2026-10-01','latest_bbch':None} if crop else None
    review=integrate(build_crop_review(cycle,None,[],today=TODAY),[record],today=TODAY,crop=cycle)
    return review['analysis_center']


def test_wheat_signs_focus_candidates_without_eliminating_unknown_causes():
    before=report()
    assert next(c for c in before['candidates'] if c['id']=='yellow_rust')['status']=='to_verify'
    focused=report({'signs':['yellow_pustule_rows']})
    assert focused['candidates'][0]['id']=='yellow_rust'
    assert focused['candidates'][0]['status']=='focused'
    assert any(c['id']=='septoria' for c in focused['candidates'])
    assert any(c['id']=='abiotic_other' for c in focused['candidates'])
    assert not any(q['id']=='focus_signs' for q in focused['questions'])
    assert all(c['source_ids'] for c in focused['candidates'])
    assert focused['observation_date']==TODAY.isoformat()


def test_multiple_visible_signs_allow_multiple_causes_and_no_crop_extrapolation():
    mixed=report({'signs':['white_powder','black_dots_in_lesions']})
    assert {'powdery_mildew','septoria'} <= {c['id'] for c in mixed['candidates'] if c['status']=='focused'}
    for crop in ['mais','orzo',None]:
        unsupported=report({'signs':['yellow_pustule_rows']},crop=crop)
        assert not {'yellow_rust','brown_rust','septoria'} & {c['id'] for c in unsupported['candidates']}


def test_event_chronology_can_weaken_application_hypothesis():
    details={'field_pattern':'spray_width','recent_event':'spray','event_date':'2026-11-24'}
    result=report(details,noticed_since='2026-11-20')
    candidate=next(c for c in result['candidates'] if c['id']=='application_injury')
    assert candidate['status']=='less_supported' and candidate['contradicting']
    details['event_date']='2026-11-19'
    candidate=next(c for c in report(details,noticed_since='2026-11-20')['candidates'] if c['id']=='application_injury')
    assert candidate['status']=='focused'


def test_conflicting_no_symptoms_and_signs_gate_focused_results():
    result=report({'signs':['white_powder']},symptoms=['no_symptoms'])
    assert result['status']=='conflicting_inputs'
    assert all(c['status']=='conflicting_inputs' for c in result['candidates'])


def test_focus_saved_as_new_immutable_observation_private_validated_and_in_snapshot(client,headers,parcel):
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    original=dict(parcel_id='field-1',observed_at=date.today().isoformat(),symptoms=['spots'],diagnostic_details={'signs':['white_powder']})
    key=str(uuid4())
    assert client.put('/observations/'+key,json=original,headers=auth).status_code==200
    changed=deepcopy(original);changed['diagnostic_details']['signs']=['brown_pustules']
    assert client.put('/observations/'+key,json=changed,headers=auth).status_code==409
    assert client.put('/observations/'+str(uuid4()),json=changed,headers=headers('bob')).status_code==404
    for invalid in [{'signs':['invented']},{'recent_event':'spray','event_date':'2099-01-01'},{'event_date':'2026-11-01'}]:
        assert client.put('/observations/'+str(uuid4()),json=dict(original,diagnostic_details=invalid),headers=auth).status_code==422
    # No coordinates, so no provider request or fabricated weather.
    from storage import connect
    with connect() as db:db.execute('UPDATE agr_parcels SET payload=NULL WHERE id=?',('field-1',))
    r=client.post('/agronomy/analyze',json={'parcel_id':'field-1'},headers=auth)
    assert r.status_code==200
    c=r.json()['crop_review']['analysis_center']
    assert any(row['id']=='powdery_mildew' for row in c['candidates'])
    history=client.get('/agronomy/results?parcel_id=field-1',headers=auth).json()
    assert history[0]['crop_review']['analysis_center']==c


def photo_bytes():
    image=Image.new('RGB',(256,256),'green');buffer=BytesIO();image.save(buffer,'PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def test_photo_quality_invalid_content_and_no_false_diagnosis():
    image,quality=clean_photo(photo_bytes())
    assert quality['issues']
    assert predict(image,quality)['status']=='retake'
    from fastapi import HTTPException
    for content in ['not base64',base64.b64encode(b'not a photo').decode()]:
        with pytest.raises(HTTPException):clean_photo(content)


def test_photo_routes_require_ownership_and_reject_unsupported_crops(client,headers,parcel):
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    data={'parcel_id':'field-1','image_base64':photo_bytes(),'wheat_leaf_confirmed':True}
    assert client.get('/analysis-center/schema').status_code==401
    assert client.post('/analysis-center/photo',json=data).status_code==401
    assert client.post('/analysis-center/photo',json=data,headers=headers('bob')).status_code==404
    r=client.post('/analysis-center/photo',json=data,headers=auth)
    assert r.status_code==200 and r.json()['recognition']['status']=='unsupported'
    assert client.get('/analysis-center/references/not-existing',headers=auth).status_code==404


def test_bundled_model_integrity_metadata_and_actual_cpu_inference():
    from pathlib import Path
    import hashlib,zipfile
    from photo_analysis import MODEL
    m=json.loads((MODEL/'metadata.json').read_text())
    assert model_info()['experimental'] is True and m['validated_on_italian_fields'] is False
    assert hashlib.sha256((MODEL/'bundle.zip').read_bytes()).hexdigest()==m['bundle_sha256']
    with zipfile.ZipFile(MODEL/'bundle.zip') as archive:
        bank=json.loads(archive.read('reference-bank.json'))
        assert len(bank)==60 and {r['label'] for r in bank}==set(m['classes'])
        first=bank[0]
        image=Image.open(BytesIO(archive.read(first['path']))).convert('RGB')
    result=predict(image,{'issues':[]})
    assert result['model_version']==m['version'] and len(result['candidates'])==3
    assert result['status'] in {'experimental_match','uncertain'}
    assert all(0<=c['model_score']<=1 for c in result['candidates'])
    assert result['candidates'][0]['reference_id'] in {r['id'] for r in bank}
