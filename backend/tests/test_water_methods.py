from datetime import date
import math
from uuid import uuid4
import pytest
from crop_analysis import build_crop_review
from evidence_engine import integrate, note_signs
from water_methods import measured_water, irrigation_quality

TODAY = date(2026,11,24)
PROFILE = dict(observed_at='2026-11-24',field_capacity_percent=30,wilting_point_percent=10,
               root_depth_m=1,depletion_fraction=.5,moisture_percent=15)


@pytest.mark.parametrize('theta,dr,ks,exceeded', [(30,0,1,False),(20,100,1,False),(15,150,.5,True),(10,200,0,True),(5,200,0,True),(35,0,1,False)])
def test_measured_profile_fao_equations_and_boundary(theta,dr,ks,exceeded):
    f=measured_water(dict(PROFILE,moisture_percent=theta),TODAY)
    assert f['values']['taw_mm']==200 and f['values']['raw_mm']==100
    assert f['values']['depletion_mm']==dr and f['values']['ks']==ks
    assert f['values']['threshold_exceeded'] is exceeded
    assert f['source_ids']==['fao56_8']
    assert f['status']==('attention' if exceeded else 'available')


@pytest.mark.parametrize('changes',[{'depletion_fraction':None},{'depletion_fraction':0},{'depletion_fraction':1},{'depletion_fraction':float('nan')},{'observed_at':'2099-01-01'},{'root_depth_m':None},{'field_capacity_percent':10}])
def test_no_guessed_p_or_invalid_profile(changes):
    f=measured_water(dict(PROFILE,**changes),TODAY)
    assert f['status']=='missing' and 'values' not in f


def test_raw_without_moisture_is_capacity_only_and_small_rounding_does_not_change_comparison():
    raw=measured_water(dict(PROFILE,moisture_percent=None),TODAY)
    assert raw['values']['raw_mm']==100 and 'ks' not in raw['values']
    f=measured_water(dict(PROFILE,moisture_percent=19.99999),TODAY)
    assert f['values']['depletion_mm']==100
    assert f['values']['threshold_exceeded'] is True  # compare before rounding


def quality(ec,sar=None,**changes):
    return {f['rule_id']:f for f in irrigation_quality(dict(water_sample_date='2026-11-20',water_ec_ds_m=ec,water_sar=sar,**changes),TODAY)}


@pytest.mark.parametrize('ec,restriction',[(.69,'none'),(.7,'slight_moderate'),(3,'slight_moderate'),(3.01,'severe')])
def test_water_salinity_table_exact_endpoints(ec,restriction):
    result=quality(ec)
    assert result['soil.irrigation_salinity']['values']['restriction']==restriction
    assert result['soil.irrigation_infiltration']['status']=='missing'


@pytest.mark.parametrize('sar,low,high',[(1,.2,.7),(4,.3,1.2),(8,.5,1.9),(15,1.3,2.9),(25,2.9,5)])
def test_infiltration_uses_both_ec_and_sar_and_includes_ec_boundaries(sar,low,high):
    for ec,expected in [(low-.01,'severe'),(low,'slight_moderate'),(high,'slight_moderate'),(high+.01,'none')]:
        f=quality(ec,sar)['soil.irrigation_infiltration']
        assert f['values']['possible_restrictions']==[expected]


def test_sar_shared_endpoints_keep_uncertainty_and_never_extrapolate():
    boundary=quality(1,3)['soil.irrigation_infiltration']
    assert boundary['status']=='partial'
    assert set(boundary['values']['possible_restrictions'])=={'none','slight_moderate'}
    assert quality(1,41)['soil.irrigation_infiltration']['status']=='partial'
    assert quality(.1,1)['soil.irrigation_salinity']['values']['restriction']=='none'
    assert quality(.1,1)['soil.irrigation_infiltration']['values']['possible_restrictions']==['severe']
    assert irrigation_quality({},TODAY)==[]
    for p in [{'water_ec_ds_m':1},{'water_ec_ds_m':1,'water_sample_date':'2099-01-01'}, {'water_ec_ds_m':math.nan}]:
        assert irrigation_quality(p,TODAY)[0]['status']=='missing'


def review(params,observed='2026-11-24'):
    return integrate(build_crop_review(None,None,[],today=TODAY),
                     [dict(id=str(uuid4()),observed_at=observed,symptoms=['wilting'],severity='mild',plant_part='leaves',notes='')],
                     today=TODAY,parameters=params)


def test_model_informs_differential_only_same_recent_day_and_retains_competing_causes():
    result=review(PROFILE)['decision_support']
    dry=next(c for c in result['differential'] if c['id']=='dry_profile')
    assert dry['status']=='consistent_inputs' and any('Ks' in s for s in dry['supporting'])
    assert any(c['id']=='root_uptake' for c in result['differential'])
    assert any(c['id']=='wilting_raw' for c in result['conclusions'])
    assert not any(c['id']=='wilting_unaligned' for c in result['conclusions'])
    different=review(dict(PROFILE,observed_at='2026-11-23'))['decision_support']
    assert next(c for c in different['differential'] if c['id']=='dry_profile')['status']=='to_verify'
    historical=review(dict(PROFILE,observed_at='2026-11-10'),observed='2026-11-10')['decision_support']
    assert next(c for c in historical['differential'] if c['id']=='dry_profile')['status']=='to_verify'
    assert any('storica' in c['explanation'] for c in historical['conclusions'] if c['id']=='measured_water_model')
    hydrated=review(dict(PROFILE,moisture_percent=25))['decision_support']
    assert next(c for c in hydrated['differential'] if c['id']=='dry_profile')['status']=='less_supported'


def test_water_referto_never_proves_exposure_and_has_complete_source_trace():
    result=review(dict(PROFILE,water_sample_date='2026-11-20',water_ec_ds_m=4,water_sar=8))
    decision=result['decision_support']
    candidate=next(c for c in decision['differential'] if c['id']=='irrigation_water_context')
    assert candidate['status']=='to_verify' and candidate['missing']
    assert any(q['id']=='water_source_used' for q in decision['questions'])
    assert any(i['id']=='irrigation_water' for i in decision['inputs'])
    refs={r['id'] for r in decision['references']}
    assert 'fao29_water' in refs
    assert all(set(c['source_ids']) <= refs for c in decision['conclusions']+decision['differential'])


def test_repeat_positive_keyword_and_negated_note_and_disjoint_weather():
    assert note_signs('Afidi assenti sulle foglie e insetti presenti sul fusto')=={'insects'}
    assert not note_signs('Senza afidi; insetti non presenti')
    windows={'7':dict(start_date='2026-11-10',end_date='2026-11-16',data_complete=True,rain_mm=10,et0_mm=30,climatic_balance_mm=-20)}
    result=integrate(build_crop_review(None,None,[],windows=windows,today=TODAY),
                     [dict(observed_at='2026-11-24',symptoms=['wilting'],severity='mild',plant_part='leaves',notes='')],windows=windows,today=TODAY)
    assert all('-20' not in h['evidence'] for h in result['integrated_assessment']['hypotheses'])


def test_parameters_new_fields_validated_private_and_old_payloads_still_work(client,headers,parcel):
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    path='/agronomy/parameters/field-1'
    params=dict(PROFILE,water_sample_date='2026-11-20',water_ec_ds_m=.1,water_sar=1)
    assert client.put(path,json=params,headers=auth).status_code==200
    assert client.get(path,headers=auth).json()['water_sar']==1
    assert client.get(path,headers=headers('bob')).status_code==404
    for changes in [{'depletion_fraction':1},{'depletion_fraction':0},{'water_sample_date':None},{'water_sample_date':'2099-01-01'},{'water_ec_ds_m':-1},{'water_sar':-1}]:
        assert client.put(path,json=dict(params,**changes),headers=auth).status_code==422
    # Saved results retain their original inputs and calculations after edits.
    from storage import connect
    with connect() as db:
        db.execute('UPDATE agr_parcels SET payload=NULL WHERE id=?',('field-1',))
    result=client.post('/agronomy/analyze',json={'parcel_id':'field-1'},headers=auth)
    assert result.status_code==200
    snapshot=result.json()['crop_review']['manual_assessment']
    assert snapshot['parameters']['water_ec_ds_m']==.1
    assert any(f.get('values',{}).get('ks')==.5 for f in snapshot['domains']['soil']['findings'])
    client.put(path,json=dict(params,moisture_percent=25,water_ec_ds_m=1),headers=auth)
    history=client.get('/agronomy/results?parcel_id=field-1',headers=auth).json()
    assert history[0]['crop_review']['manual_assessment']==snapshot
    assert client.put(path,json={'observed_at':'2026-11-20','kc':1,'kc_from':'2026-11-10','kc_to':'2026-11-20'},headers=auth).status_code==200
