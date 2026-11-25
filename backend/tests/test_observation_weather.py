from datetime import date, timedelta
from copy import deepcopy
import asyncio
import httpx
import main
from uuid import uuid4
from weather_history import observation_context
from crop_analysis import build_crop_review
from evidence_engine import integrate

TODAY = date(2026, 11, 24)


def rows(first=10, last=19):
    return [{'date': f'2026-11-{d:02d}', 'precipitation_sum': 2,
             'et0_fao_evapotranspiration': 3, 'temperature_2m_max': 20,
             'temperature_2m_min': 10} for d in range(first, last + 1)]


def test_provider_lag_uses_actual_two_weeks_without_moving_observation():
    history = rows(1, 19)
    record = dict(observed_at='2026-11-24', symptoms=['wilting'], severity='mild', notes='')
    original = deepcopy(record)
    review = integrate(build_crop_review(None, None, [], today=TODAY), [record],
                       today=TODAY, weather_history=history)
    c = review['observation_weather']
    assert c['start_date'] == '2026-11-10' and c['end_date'] == '2026-11-23'
    assert c['observation_date'] == '2026-11-24' and record == original
    assert c['available_days'] == 10 and c['paired_days'] == 10
    assert c['available_through'] == '2026-11-19' and c['climatic_balance_mm'] == -10
    assert c['missing_dates'] == [f'2026-11-{d}' for d in range(20, 24)]
    assert c['trailing_missing_dates'] == c['missing_dates'] and not c['internal_missing_dates']
    findings = [f for domain in review['manual_assessment']['domains'].values() for f in domain['findings']]
    assert any(f['rule_id'] == 'problems.water_context' for f in findings)
    assert not any(f['rule_id'] == 'problems.time_alignment' for f in findings)
    conclusions = review['decision_support']['conclusions']
    linked = next(c for c in conclusions if c['id'] == 'wilting_weather')
    assert '10 giorni' in linked['explanation'] and '2026-11-24' in linked['explanation']
    assert 'Date da riallineare' not in str(review)


def test_missing_metrics_use_intersection_not_unmatched_totals_or_zero_fill():
    history = rows()
    history[0]['precipitation_sum'] = None
    history[1]['et0_fao_evapotranspiration'] = None
    history[2]['precipitation_sum'] = -1
    history[3]['et0_fao_evapotranspiration'] = float('nan')
    c = observation_context(history, TODAY)
    assert c['available_days'] == 10 and c['paired_days'] == 6
    assert c['rain_mm'] == 16 and c['et0_mm'] == 24
    assert c['paired_rain_mm'] == 12 and c['paired_et0_mm'] == 18
    assert c['climatic_balance_mm'] == -6 and c['data_complete'] is False
    assert c['coverage']['rain']['valid_days'] == 8
    assert '2026-11-10' in c['coverage']['rain']['missing_dates']
    assert '2026-11-10' not in c['missing_dates']  # temperatures remain usable


def test_boundaries_duplicates_gaps_empty_rows_and_order_are_explicit():
    history = rows(1, 28)
    history += [dict(history[14])]  # November 15 is ambiguous
    history[11] = {'date': '2026-11-12'}
    history += [{'date': 'invalid', 'precipitation_sum': 1000}]
    c = observation_context(history, TODAY)
    assert c == observation_context(list(reversed(history)), TODAY)
    assert c['available_days'] == 12 and c['missing_dates'] == ['2026-11-12', '2026-11-15']
    assert c['available_through'] == '2026-11-23' and c['paired_days'] == 12
    assert c['rain_mm'] == 24 and c['et0_mm'] == 36
    assert c['internal_missing_dates'] == c['missing_dates']
    assert not c['trailing_missing_dates']
    empty = observation_context(rows(1, 5) + rows(24, 28), TODAY)
    assert empty['available_days'] == 0 and empty['available_through'] is None
    assert empty['rain_mm'] is None and empty['climatic_balance_mm'] is None
    assert len(empty['missing_dates']) == 14


def test_temperature_only_or_rain_only_context_never_crashes_or_claims_balance():
    for key in ['temperature_2m_max', 'precipitation_sum']:
        history = [{'date': '2026-11-19', key: 12}]
        record = dict(observed_at='2026-11-24', symptoms=['wilting'], severity='mild', notes='')
        review = integrate(build_crop_review(None, None, [], today=TODAY), [record], today=TODAY, weather_history=history)
        c = review['observation_weather']
        assert c['available_days'] == 1 and c['paired_days'] == 0
        assert c['climatic_balance_mm'] is None
        conclusion = next(c for c in review['decision_support']['conclusions'] if c['id'] == 'wilting_weather')
        assert 'non sono confrontabili' in conclusion['explanation']


def test_backdated_visit_anchors_its_own_window_and_zero_is_a_valid_measurement():
    history = [dict(r, precipitation_sum=0, et0_fao_evapotranspiration=0) for r in rows(1, 28)]
    c = observation_context(history, date(2026, 11, 20))
    assert c['start_date'] == '2026-11-06' and c['end_date'] == '2026-11-19'
    assert c['available_days'] == 14 and c['data_complete'] is True
    assert c['climatic_balance_mm'] == 0 and c['missing_dates'] == []
    assert '2026-11-20' not in c['available_dates']


def test_open_meteo_partial_archive_is_retained_when_forecast_is_down(monkeypatch):
    original = httpx.AsyncClient
    def handler(request):
        if request.url.host == 'archive-api.open-meteo.com':
            return httpx.Response(200, json={'daily': {'time': ['2026-11-18', '2026-11-19'],
                'temperature_2m_max': [20, None], 'temperature_2m_min': [10, 10],
                'precipitation_sum': [2, 3], 'et0_fao_evapotranspiration': [3, None]}})
        return httpx.Response(503)
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(main._open_meteo_weather(main.WeatherRequest(latitude=44.5, longitude=11.3), TODAY))
    assert len(result['history']) == 2 and result['source'] == 'Open-Meteo'
    assert result['rain_7d_mm'] is None and result['forecast'] == []


def test_api_wires_daily_weather_to_snapshot_and_keeps_real_record(client, headers, parcel, monkeypatch):
    today = date.today()
    auth = headers()
    client.put('/parcels/field-1', json=parcel, headers=auth)
    record = dict(parcel_id='field-1', observed_at=today.isoformat(), symptoms=['wilting'], severity='mild')
    assert client.put('/observations/'+str(uuid4()), json=record, headers=auth).status_code == 200
    history = [dict(r, date=(today-timedelta(days=14-i)).isoformat()) for i, r in enumerate(rows())]
    async def weather(req, current):
        return main._weather_result(req, today-timedelta(days=5), history, 'Test archive')
    async def no_forecast(req): return {}, []
    monkeypatch.setattr(main, '_open_meteo_weather', weather)
    monkeypatch.setattr(main, '_met_norway_weather', no_forecast)
    response = client.post('/agronomy/analyze', json={'parcel_id': 'field-1'}, headers=auth)
    assert response.status_code == 200
    snapshot = response.json()
    c = snapshot['crop_review']['observation_weather']
    assert c['available_days'] == 10 and c['observation_date'] == today.isoformat()
    assert c['available_through'] == (today-timedelta(days=5)).isoformat()
    assert snapshot['crop_review']['visual_context']['latest']['observed_at'] == today.isoformat()
    history_results = client.get('/agronomy/results?parcel_id=field-1', headers=auth).json()
    assert history_results[0]['crop_review']['observation_weather'] == c
    assert client.get('/observations?parcel_id=field-1', headers=auth).json()[0]['observed_at'] == today.isoformat()
