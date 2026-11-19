from datetime import date,timedelta
from uuid import uuid4
import copy
from crop_analysis import build_crop_review
from evidence_engine import integrate
from field_records import save_result

def record(**changes):
    return {'parcel_id':'field-1','observed_at':date.today().isoformat(),'symptoms':['yellowing'],'severity':'high','affected_percent':40,'plant_part':'leaves','notes':'Foglie giovani ingiallite',**changes}

def test_observations_ownership_validation_and_retry(client,headers,parcel):
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    path='/observations/'+str(uuid4());data=record()
    assert client.put(path,json=data).status_code==401
    first=client.put(path,json=data,headers=auth)
    assert first.status_code==200
    assert client.put(path,json=data,headers=auth).json()['id']==first.json()['id']
    assert len(client.get('/observations?parcel_id=field-1',headers=auth).json())==1
    assert client.put(path,json=record(notes='Altro'),headers=auth).status_code==409
    assert client.get('/observations?parcel_id=field-1',headers=headers('bob')).status_code==404
    for invalid in [record(symptoms=['no_symptoms','spots']),record(observed_at=(date.today()+timedelta(days=1)).isoformat()),record(affected_percent=101),record(symptoms=[],notes=' ')]:
        assert client.put('/observations/'+str(uuid4()),json=invalid,headers=auth).status_code==422

def test_engine_marks_hypotheses_and_does_not_infer_negated_or_old_symptoms():
    base=build_crop_review(None,None,[])
    review=integrate(copy.deepcopy(base),[record()])
    assert review['checks'][0]['title']=='Sopralluogo prioritario'
    assert review['integrated_assessment']['hypotheses']
    assert review['coverage']['visual_observations'] is True
    for item in [record(symptoms=[],notes='Non vedo ingiallimento'),record(observed_at=(date.today()-timedelta(days=20)).isoformat())]:
        result=integrate(copy.deepcopy(base),[item])
        assert not result['integrated_assessment']['hypotheses']

def test_results_are_private_immutable_and_retry_deduplicated(client,headers,parcel):
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    result={'parcel_id':'field-1','crop_review':build_crop_review(None,None,[])}
    first=save_result('field-1',result)
    result['crop_review']['generated_at']='later'
    assert save_result('field-1',result)==first
    result['crop_review']['summary']='new inputs'
    assert save_result('field-1',result)!=first
    rows=client.get('/agronomy/results?parcel_id=field-1',headers=auth).json()
    assert len(rows)==2
    assert client.get('/agronomy/results?parcel_id=field-1',headers=headers('bob')).status_code==404

def test_saved_visual_input_is_used_in_analysis_and_history(client,headers,parcel,monkeypatch):
    import main
    from fastapi import HTTPException
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    assert client.put('/observations/'+str(uuid4()),json=record(),headers=auth).status_code==200
    async def unavailable(*args):raise main.httpx.ConnectError('offline')
    async def fallback_unavailable(*args):raise HTTPException(503,'offline')
    monkeypatch.setattr(main,'_open_meteo_weather',unavailable)
    monkeypatch.setattr(main,'_nasa_weather',fallback_unavailable)
    response=client.post('/agronomy/analyze',json={'parcel_id':'field-1','latitude':44.5,'longitude':11.3},headers=auth)
    assert response.status_code==200
    result=response.json()
    assert result['crop_review']['integrated_assessment']['hypotheses']
    assert result['crop_review']['visual_context']['latest']['notes']=='Foglie giovani ingiallite'
    history=client.get('/agronomy/results?parcel_id=field-1',headers=auth).json()
    assert history[0]['result_id']==result['result_id']
