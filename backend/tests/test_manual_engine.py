from datetime import date
from copy import deepcopy
import pytest
from crop_analysis import build_crop_review
from evidence_engine import integrate
from manual_engine import evaluate

TODAY = date(2026, 11, 20)
WINDOWS = {'7': {'start_date': '2026-11-10', 'end_date': '2026-11-16', 'data_complete': True, 'rain_mm': 12, 'et0_mm': 21}}
PARAMS = {'observed_at': '2026-11-16', 'field_capacity_percent': 30, 'wilting_point_percent': 15, 'root_depth_m': .8,
          'moisture_percent': 20, 'kc': 1.15, 'kc_from': '2026-11-01', 'kc_to': '2026-11-18'}


def rule(result, category, name):
    return next(r for r in result['domains'][category]['findings'] if r['rule_id'] == name)


def test_manual_equations_units_and_reproducible_provenance():
    result = evaluate(build_crop_review(None, None, []), windows=WINDOWS, parameters=PARAMS, today=TODAY)
    water = rule(result, 'soil', 'soil.available_water')
    assert water['values']['taw_mm'] == 120  # 1000 * (.30-.15) * .8
    assert water['values']['depletion_mm'] == 80
    assert rule(result, 'weather', 'weather.crop_et')['values']['etc_mm'] == 24.15
    assert rule(result, 'weather', 'weather.climatic_balance')['values']['balance_mm'] == -9
    assert result['engine_version']
    refs = {r['id'] for r in result['references']}
    assert all(s in refs for d in result['domains'].values() for r in d['findings'] for s in r['source_ids'])
    assert evaluate(build_crop_review(None, None, []), windows=WINDOWS, parameters=PARAMS, today=TODAY) == result


@pytest.mark.parametrize('changes', [{'data_complete':False}, {'et0_mm':None}, {'end_date':'2026-11-21'}, {'start_date':'2026-11-11'}])
def test_incomplete_or_invalid_weather_never_becomes_zero_or_etc(changes):
    windows=deepcopy(WINDOWS); windows['7'].update(changes)
    result=evaluate({}, windows=windows, parameters=PARAMS, today=TODAY)
    assert rule(result, 'weather', 'weather.crop_et')['status']=='missing'
    assert rule(result, 'weather', 'weather.climatic_balance')['status']=='missing'


def test_kc_must_cover_whole_window_and_missing_water_inputs_block_calculation():
    for changes in [{'kc_from':'2026-11-11'}, {'kc_to':'2026-11-15'}, {'kc':None}]:
        result=evaluate({}, windows=WINDOWS, parameters=dict(PARAMS,**changes), today=TODAY)
        assert rule(result,'weather','weather.crop_et')['status']=='missing'
    assert rule(evaluate({}), 'soil','soil.available_water')['status']=='missing'


def test_note_negations_do_not_hide_a_distinct_positive_symptom():
    from evidence_engine import note_signs
    assert note_signs('Non vedo afidi, ma noto macchie sulle foglie') == {'spots'}
    assert not note_signs('Ingiallimento assente; senza appassimento; insetti non presenti')


@pytest.mark.parametrize('ph,label', [(3.4,'ultra acido'),(5.55,'moderatamente acido'),(6.5,'leggermente acido'),(6.6,'neutro'),(7.3,'neutro'),(7.4,'leggermente alcalino'),(9.1,'molto fortemente alcalino')])
def test_ph_table_boundaries_and_rounding(ph,label):
    review={'soil_context':{'sample_date':'2026-11-01','ph':ph,'source':'laboratory'}}
    assert rule(evaluate(review,today=TODAY),'soil','soil.ph_class')['values']['class']==label


def test_incoherent_texture_future_referto_and_symptoms_from_different_dates():
    soil={'sample_date':'2026-11-01','source':'laboratory','ph':8,'sand_percent':60,'silt_percent':60,'clay_percent':20}
    review=build_crop_review(None,soil,[],today=TODAY)
    record={'observed_at':'2026-11-20','symptoms':['wilting'],'severity':'mild','plant_part':'leaves','notes':''}
    result=integrate(review,[record],today=TODAY,windows=WINDOWS)['manual_assessment']
    assert rule(result,'soil','soil.texture_quality')['status']=='attention'
    assert rule(result,'problems','problems.weather_missing')['status']=='missing'
    assert not any(r['rule_id']=='problems.water_context' for r in result['domains']['problems']['findings'])
    review['soil_context']['sample_date']='2026-11-21'
    assert rule(evaluate(review,today=TODAY),'soil','soil.ph_class')['status']=='missing'


def test_parameters_private_validated_and_included_in_snapshot(client,headers,parcel,monkeypatch):
    import main
    from fastapi import HTTPException
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    path='/agronomy/parameters/field-1'
    assert client.get(path).status_code==401
    assert client.get(path,headers=headers('bob')).status_code==404
    assert client.put(path,json=PARAMS,headers=auth).status_code==200
    assert client.get(path,headers=auth).json()['kc']==1.15
    for invalid in [{'wilting_point_percent':31},{'root_depth_m':0},{'kc_from':'2026-11-19'},{'field_capacity_percent':'NaN'},{'observed_at':'2099-01-01'}]:
        assert client.put(path,json=dict(PARAMS,**invalid),headers=auth).status_code==422
    async def unavailable(*args): raise main.httpx.ConnectError('offline')
    async def no_fallback(*args): raise HTTPException(503,'offline')
    monkeypatch.setattr(main,'_open_meteo_weather',unavailable)
    monkeypatch.setattr(main,'_nasa_weather',no_fallback)
    response=client.post('/agronomy/analyze',json={'parcel_id':'field-1','latitude':44.5,'longitude':11.3},headers=auth)
    assert response.status_code==200
    engine=response.json()['crop_review']['manual_assessment']
    assert engine['parameters']['field_capacity_percent']==30
    assert rule(engine,'soil','soil.available_water')['values']['taw_mm']==120
    history=client.get('/agronomy/results?parcel_id=field-1',headers=auth).json()
    assert history[0]['crop_review']['manual_assessment']==engine
