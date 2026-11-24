from datetime import date
import pytest
from phenology import stage, assess
from crop_analysis import build_crop_review
from evidence_engine import integrate

TODAY=date(2026,11,24)


def crop(name='frumento_tenero',code=39,observed='2026-11-24',sown='2026-10-10'):
    return dict(crop=name,sowing_date=sown,latest_bbch=dict(bbch=code,observed_at=observed))


def test_species_specific_definitions_do_not_reuse_cereal_flag_leaf_for_maize():
    cereal=stage('Frumento tenero',39);maize=stage('mais',39)
    assert cereal['status']=='recognized' and 'bandiera' in cereal['description']
    assert 'nodi' in maize['description'] and 'bandiera' not in maize['description']
    assert 'antere' in stage('orzo',61)['description']
    assert 'spiga femminile' in stage('mais',61)['description']
    assert 'nero' in stage('mais',87)['description']
    assert 'pastosa dura' in stage('orzo',87)['description']


@pytest.mark.parametrize('name',['frumento_tenero','frumento_duro','orzo','avena','segale','Frumento duro','grano tenero','wheat'])
def test_explicit_crop_aliases_and_reviewed_codes(name):
    assert assess(crop(name),TODAY)['usable_for_current_analysis'] is True


@pytest.mark.parametrize('name',['triticale','riso','soia','frumento e mais',None])
def test_unreviewed_crops_are_not_guessed(name):
    result=assess(crop(name),TODAY)
    assert result['status']=='unsupported' and not result['usable_for_current_analysis']


@pytest.mark.parametrize('code',[20,29,41,45,49,52,57,77,92])
def test_maize_never_inherits_missing_cereal_substages(code):
    assert stage('mais',code)['status']=='unmapped'


@pytest.mark.parametrize('code',[2,4,8,38,40,60,62,68,70,80,90,98,True,'39'])
def test_unsupported_cereal_codes_stay_explicit(code):
    assert stage('orzo',code)['status']=='unmapped'


@pytest.mark.parametrize('changes,status',[
    ({'observed':'2026-11-25'},'invalid_date'),({'observed':'not-a-date'},'invalid_date'),
    ({'observed':'2026-10-20'},'stale'),({'observed':'2026-10-01'},'date_conflict'),
    ({'sown':'2027-01-01'},'date_conflict'),({'sown':'invalid'},'date_conflict')])
def test_dates_do_not_turn_historical_or_incoherent_reports_into_current_phase(changes,status):
    result=assess(crop(**changes),TODAY)
    assert result['status']==status and not result['usable_for_current_analysis']


def test_seed_before_sowing_and_harvest_are_not_treated_as_active_standing_plants():
    seed=assess(crop(code=0,observed='2026-10-01'),TODAY)
    assert seed['status']=='stale' and not seed['usable_for_current_analysis']
    for code in (0,97,99):
        assert not assess(crop(code=code),TODAY)['usable_for_current_analysis']


def test_phase_is_a_referenced_result_and_does_not_invent_kc():
    context=crop('mais',65)
    result=integrate(build_crop_review(context,None,[],today=TODAY),[],crop=context,today=TODAY)
    decision=result['decision_support'];manual=result['manual_assessment']
    conclusion=next(c for c in decision['conclusions'] if c['id']=='crop_phase')
    assert 'sete' in conclusion['explanation'] and conclusion['source_ids']==['bbch_2001']
    assert 'bbch_2001' in {r['id'] for r in decision['references']}
    assert 'kc' not in manual['parameters']
    assert next(f for f in manual['domains']['weather']['findings'] if f['rule_id']=='weather.crop_et')['status']=='missing'


def test_yellowing_uses_maturity_only_on_the_same_day_without_calling_it_normal():
    record=dict(observed_at='2026-11-24',symptoms=['yellowing'],severity='mild',plant_part='leaves',notes='')
    context=crop(code=85)
    def run(context):return integrate(build_crop_review(context,None,[],today=TODAY),[record],crop=context,today=TODAY)['decision_support']
    conclusion=next(c for c in run(context)['conclusions'] if c['id']=='yellowing_phase')
    assert 'non una prova' in conclusion['explanation']
    assert not any(c['id']=='yellowing_phase' for c in run(crop(code=85,observed='2026-11-23'))['conclusions'])
    assert not any(c['id']=='yellowing_phase' for c in run(crop(code=85,observed='2026-11-01'))['conclusions'])


def test_enriched_bbch_api_is_private_preserves_codes_and_rejects_new_future_reports(client,headers,parcel):
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    c=client.post('/crop/cycles',json={'parcel_id':'field-1','crop':'mais','season':'2026'},headers=auth).json()
    path=f"/crop/cycles/{c['id']}/bbch"
    assert client.post(path,json={'observed_at':'2099-01-01','bbch':61},headers=auth).status_code==422
    assert client.post(path,json={'observed_at':date.today().isoformat(),'bbch':61},headers=auth).status_code==201
    # An unmapped operator report is retained for clarification, not rewritten.
    assert client.post(path,json={'observed_at':date.today().isoformat(),'bbch':45},headers=auth).status_code==201
    rows=client.get(path,headers=auth).json()
    assert rows[0]['bbch']==45 and rows[0]['phenology']['status']=='unmapped'
    assert 'spiga femminile' in rows[1]['phenology']['description']
    assert client.get(path,headers=headers('bob')).status_code==404
    assert client.get(path).status_code==401
