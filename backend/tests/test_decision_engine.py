from datetime import date, timedelta
import json
from uuid import uuid4
from crop_analysis import build_crop_review
from evidence_engine import integrate

TODAY = date(2026, 11, 20)
WINDOWS = {'7': {'start_date':'2026-11-10','end_date':'2026-11-16','data_complete':True,'rain_mm':12,'et0_mm':21}}


def analyze(symptoms=None, observed_at='2026-11-16', severity='mild', percent=10, notes='', windows=None):
    record={'observed_at':observed_at,'symptoms':symptoms or [],'severity':severity,'affected_percent':percent,'plant_part':'leaves','notes':notes}
    base=build_crop_review(None,None,[],windows=windows or {},today=TODAY)
    seven=(windows or {}).get('7')
    history=[{'date':(date.fromisoformat(seven['start_date'])+timedelta(days=i)).isoformat(),
              'precipitation_sum':12/7, 'et0_fao_evapotranspiration':3} for i in range(7)] if seven else []
    return integrate(base,[record],today=TODAY,windows=windows or {},weather_history=history)['decision_support']


def test_return_crosses_wilting_with_matching_weather_and_proposes_checks():
    result=analyze(['wilting'], observed_at='2026-11-17', windows=WINDOWS)
    finding=next(c for c in result['conclusions'] if c['id']=='wilting_weather')
    assert '-9 mm' in finding['explanation']
    assert {'observations','weather','water'}==set(finding['input_ids'])
    assert finding['action'] in result['next_steps']
    assert result['status']=='needs_verification'
    assert result['references'] and result['engine_version']


def test_severe_symptoms_get_first_priority_but_notes_alone_do_not():
    result=analyze(['spots'],severity='high')
    assert result['status']=='priority_check'
    assert result['conclusions'][0]['id']=='field_priority'
    result=analyze([],severity='high',notes='Vedo macchie')
    assert result['status']!='priority_check'
    assert any(c['id']=='confirm_notes' for c in result['conclusions'])


def test_old_or_negated_observations_and_disjoint_dates_do_not_create_causality():
    old=analyze(['wilting'],observed_at='2026-10-01',windows=WINDOWS)
    assert not any(c['id'].startswith('wilting') for c in old['conclusions'])
    assert next(i for i in old['inputs'] if i['id']=='observations')['status']=='stale'
    negative=analyze([],notes='Non vedo appassimento',windows=WINDOWS)
    assert not any(c['id'].startswith('wilting') or c['id']=='confirm_notes' for c in negative['conclusions'])
    disjoint=analyze(['wilting'],observed_at='2026-11-20',windows=WINDOWS)
    assert any(c['id']=='wilting_weather' for c in disjoint['conclusions'])
    assert '7/14' in next(i for i in disjoint['inputs'] if i['id']=='weather')['detail']


def test_missing_inputs_get_a_useful_response_without_an_all_clear():
    review=integrate(build_crop_review(None,None,[],today=TODAY),[],today=TODAY)
    result=review['decision_support']
    assert result['status']=='incomplete'
    assert result['headline']=='Servono input per iniziare la valutazione'
    assert result['conclusions']==[]
    assert result['next_steps'] and result['missing_inputs']
    assert all(i['status']=='missing' for i in result['inputs'])


def test_no_symptoms_report_is_not_a_health_certificate():
    result=analyze(['no_symptoms'])
    conclusion=next(c for c in result['conclusions'] if c['id']=='reported_no_symptoms')
    assert 'non certifica' in conclusion['explanation']
    assert result['status']!='priority_check'


def test_wilting_and_dry_root_zone_are_connected_only_for_the_same_recent_day():
    record={'observed_at':'2026-11-20','symptoms':['wilting'],'severity':'mild','affected_percent':10,'plant_part':'leaves','notes':''}
    params={'observed_at':'2026-11-20','field_capacity_percent':30,'wilting_point_percent':15,'root_depth_m':.8,'moisture_percent':10}
    base=build_crop_review(None,None,[],today=TODAY)
    result=integrate(base,[record],today=TODAY,parameters=params)['decision_support']
    linked=next(c for c in result['conclusions'] if c['id']=='wilting_soil')
    assert set(linked['input_ids'])=={'observations','water'}
    assert linked['action']==result['next_steps'][0]
    assert not any(c['id']=='wilting_unaligned' for c in result['conclusions'])
    for change in [{'observed_at':'2026-11-19'},{'moisture_percent':20}]:
        other=integrate(build_crop_review(None,None,[],today=TODAY),[record],today=TODAY,parameters=dict(params,**change))['decision_support']
        assert not any(c['id']=='wilting_soil' for c in other['conclusions'])


def test_reports_without_geometry_work_without_inventing_weather(client,headers,parcel,monkeypatch):
    import main
    auth=headers()
    assert client.put('/parcels/field-1',json=parcel,headers=auth).status_code==200
    from storage import connect
    with connect() as db:
        db.execute('UPDATE agr_parcels SET payload=NULL WHERE id=?', ('field-1',))
    async def forbidden(*args): raise AssertionError('No coordinates: weather provider must not be called')
    monkeypatch.setattr(main,'_open_meteo_weather',forbidden)
    monkeypatch.setattr(main,'_nasa_weather',forbidden)
    request={'parcel_id':'field-1'}
    assert client.post('/agronomy/analyze',json=request).status_code==401
    assert client.post('/agronomy/analyze',json=request,headers=headers('bob')).status_code==404
    assert client.post('/agronomy/analyze',json=dict(request,latitude=44.5),headers=auth).status_code==422
    response=client.post('/agronomy/analyze',json=request,headers=auth)
    assert response.status_code==200
    data=response.json()
    assert data['latitude'] is None and data['windows']=={}
    assert data['crop_review']['decision_support']['status']=='incomplete'
    observation={'parcel_id':'field-1','observed_at':date.today().isoformat(),'symptoms':['spots'],'severity':'high'}
    client.put('/observations/'+str(uuid4()),json=observation,headers=auth)
    updated=client.post('/agronomy/analyze',json=request,headers=auth).json()
    assert updated['crop_review']['decision_support']['status']=='priority_check'
    history=client.get('/agronomy/results?parcel_id=field-1',headers=auth).json()
    by_id={r['result_id']:r for r in history}
    assert by_id[data['result_id']]['crop_review']['decision_support']['status']=='incomplete'
    assert by_id[updated['result_id']]['crop_review']['decision_support']['status']=='priority_check'
