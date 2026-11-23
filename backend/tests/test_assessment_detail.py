from datetime import date
import json
from uuid import uuid4
from crop_analysis import build_crop_review
from evidence_engine import integrate
from storage import connect

TODAY=date(2026,11,23)


def report(day='2026-11-23', **extra):
    return dict(observed_at=day,symptoms=['wilting'],severity='mild',affected_percent=10,
                plant_part='leaves',notes='',**extra)


def assess(records,params=None):
    return integrate(build_crop_review(None,None,[],today=TODAY),records,today=TODAY,parameters=params)['decision_support']


def test_trend_compares_distinct_days_only_and_uses_percentage_points():
    previous=report('2026-11-21');latest=report();latest['affected_percent']=25
    same_day=report();same_day['affected_percent']=70
    same_day['created_at']='2026-11-23T08:00:00+00:00';latest['created_at']='2026-11-23T09:00:00+00:00'
    result=assess([previous,same_day,latest])['observation_trend']
    assert result['status']=='reported_increase' and result['delta_percentage_points']==15
    assert [p['observed_at'] for p in result['points']]==['2026-11-21','2026-11-23']
    assert 'punti percentuali' in result['summary']


def test_incompatible_context_old_data_and_notes_do_not_invent_a_trend():
    latest=report()
    for previous in [report('2026-11-21',distribution='patches'),report('2026-11-21',leaf_age='young'),report('2026-10-01')]:
        assert assess([previous,latest])['observation_trend']['status']=='insufficient'
    previous=report('2026-11-21');previous['symptoms']=[];previous['notes']='Appassimento'
    assert 'delta_percentage_points' not in assess([previous,latest])['observation_trend']


def test_no_symptoms_after_symptoms_does_not_certify_recovery():
    latest=report();latest['symptoms']=['no_symptoms'];latest['affected_percent']=0
    result=assess([report('2026-11-21'),latest])['observation_trend']
    assert result['status']=='not_reported'
    assert 'non dimostra' in result['summary']


def test_wet_measurement_weakens_dry_profile_and_changes_the_main_return():
    params={'observed_at':'2026-11-23','field_capacity_percent':30,'wilting_point_percent':15,'root_depth_m':.8,'moisture_percent':35}
    result=assess([report()],params)
    dry=next(c for c in result['differential'] if c['id']=='dry_profile')
    assert dry['status']=='less_supported' and dry['contradicting']
    assert any(c['id']=='wilting_wet_profile' for c in result['conclusions'])
    assert not any(c['id']=='wilting_soil' for c in result['conclusions'])
    params['observed_at']='2026-11-22'
    stale=next(c for c in assess([report()],params)['differential'] if c['id']=='dry_profile')
    assert stale['status']=='to_verify' and not stale['contradicting']


def test_dry_measurement_and_damaged_roots_can_support_competing_pistes():
    params={'observed_at':'2026-11-23','field_capacity_percent':30,'wilting_point_percent':15,'root_depth_m':.8,'moisture_percent':10}
    result=assess([report(root_condition='damaged')],params)
    assert {'dry_profile','root_uptake'} <= {c['id'] for c in result['differential'] if c['status']=='consistent_inputs'}
    assert 'Non sono probabilità' in result['evidence_note']


def test_questions_are_answerable_and_answered_details_remove_the_question():
    item=report();item['symptoms']=['yellowing','wilting']
    first=assess([item]);ids={q['id'] for q in first['questions']}
    assert {'leaf_age','distribution','onset','roots'} <= ids
    answered=dict(item,leaf_age='young',distribution='patches',root_condition='normal',noticed_since='2026-11-20')
    assert not ({'leaf_age','distribution','onset','roots'} & {q['id'] for q in assess([answered])['questions']})


def test_same_day_conflicting_reports_stay_visible_instead_of_silently_overriding():
    absent=report();absent.update(symptoms=['no_symptoms'],affected_percent=0,created_at='2026-11-23T08:00:00')
    latest=report();latest['created_at']='2026-11-23T09:00:00'
    result=assess([absent,latest])
    assert result['quality_notes']
    assert all(c['status']=='conflicting_inputs' for c in result['differential'])
    assert any(q['id']=='resolve_reports' for q in result['questions'])


def test_optional_details_validate_and_legacy_retry_stays_idempotent(client,headers,parcel):
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    key=str(uuid4());old=dict(report(date.today().isoformat()),parcel_id='field-1')
    with connect() as db:
        db.execute('INSERT INTO agr_field_observations VALUES(?,?,?,?,?)',(key,'field-1',old['observed_at'],'2026-11-23T08:00:00',json.dumps(old)))
    r=client.put('/observations/'+key,json=old,headers=auth)
    assert r.status_code==200
    with connect() as db:
        assert 'leaf_age' not in json.loads(db.execute('SELECT payload FROM agr_field_observations WHERE id=?',(key,)).fetchone()['payload'])
    enriched=dict(old,leaf_age='young',distribution='patches',root_condition='damaged',noticed_since='2026-11-20')
    assert client.put('/observations/'+key,json=enriched,headers=auth).status_code==409
    assert client.put('/observations/'+str(uuid4()),json=enriched,headers=auth).status_code==200
    for change in [{'leaf_age':'invented'},{'noticed_since':'2099-01-01'},{'root_condition':'diagnosis'}]:
        assert client.put('/observations/'+str(uuid4()),json=dict(enriched,**change),headers=auth).status_code==422
