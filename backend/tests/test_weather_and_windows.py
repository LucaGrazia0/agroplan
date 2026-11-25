from datetime import date, timedelta
import asyncio
import httpx
import pytest
import main
from agronomy_engine import calculate_window
from agronomy_alerts import build_alerts


def history(days=30):
    return [{'date':(date(2026,10,1)+timedelta(days=i)).isoformat(), 'temperature_2m_max':20,
             'temperature_2m_min':10, 'precipitation_sum':2, 'et0_fao_evapotranspiration':3} for i in range(days)]


def test_calendar_windows():
    rows = history()
    assert calculate_window(rows,7)['climatic_balance_mm'] == -7
    assert calculate_window(list(reversed(rows)),7)['data_complete'] is True
    assert calculate_window([rows[-1]]*7,7)['data_complete'] is False
    assert calculate_window(rows[:-2]+[rows[-1]],7)['data_complete'] is False
    assert calculate_window(rows+[{**rows[-1],'date':'not-a-date'}],7)['data_complete'] is True
    assert calculate_window([{**r,'et0_fao_evapotranspiration':None} for r in rows],7)['climatic_balance_mm'] is None
    assert calculate_window([{**r,'precipitation_sum':float('nan')} for r in rows],7)['rain_mm'] is None


def test_alerts_do_not_count_duplicate_days():
    weather = {'history':[history()[-1]]*7}
    alerts = build_alerts(weather, {'crop':'frumento_tenero','latest_bbch':{'bbch':30}})
    assert not any(a['category']=='malattie' for a in alerts)
    assert any(a['status']=='dati_insufficienti' for a in alerts)


def test_open_meteo_preferred_and_cached(client, headers, monkeypatch):
    calls = []
    async def preferred(req,today):
        calls.append('open-meteo')
        return main._weather_result(req,date(2026,10,30),history(),'Open-Meteo')
    async def nasa(*args):
        pytest.fail('NASA must not replace a complete ET0 history')
    async def met(req): return {}, []
    monkeypatch.setattr(main,'_open_meteo_weather',preferred)
    monkeypatch.setattr(main,'_nasa_weather',nasa)
    monkeypatch.setattr(main,'_met_norway_weather',met)
    auth = headers()
    for _ in range(2):
        response = client.post('/weather', json={'latitude':44.5,'longitude':11.3}, headers=auth)
        assert response.status_code == 200 and response.json()['source']=='Open-Meteo'
    assert calls == ['open-meteo']


def test_nasa_fallback_is_explicit(client, headers, monkeypatch):
    async def unavailable(*args): raise httpx.ConnectError('offline')
    async def nasa(req,today):
        return main._weather_result(req,date(2026,10,30),[{**r,'et0_fao_evapotranspiration':None} for r in history()],'NASA POWER')
    async def met(req): return {}, []
    monkeypatch.setattr(main,'_open_meteo_weather',unavailable)
    monkeypatch.setattr(main,'_nasa_weather',nasa)
    monkeypatch.setattr(main,'_met_norway_weather',met)
    response = client.post('/weather', json={'latitude':44.5,'longitude':11.3}, headers=headers())
    assert response.status_code==200 and response.json()['source']=='NASA POWER'
    assert all(r['et0_fao_evapotranspiration'] is None for r in response.json()['history'])


def test_forecast_outage_keeps_archive(monkeypatch):
    original = httpx.AsyncClient
    def handler(request):
        if request.url.host == 'archive-api.open-meteo.com':
            start = date.fromisoformat(request.url.params['start_date'])
            end = date.fromisoformat(request.url.params['end_date'])
            dates = [(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
            return httpx.Response(200,json={'daily':{'time':dates, 'temperature_2m_max':[20]*len(dates),
                'temperature_2m_min':[10]*len(dates),'precipitation_sum':[2]*len(dates),
                'et0_fao_evapotranspiration':[3]*len(dates)}})
        return httpx.Response(503)
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs: original(transport=httpx.MockTransport(handler),**kwargs))
    result = asyncio.run(main._open_meteo_weather(main.WeatherRequest(latitude=44.5,longitude=11.3),date(2026,11,1)))
    assert result['source']=='Open-Meteo' and result['forecast']==[]
    assert len(result['history'])==60


def test_missing_end_date_is_not_a_complete_window():
    rows = history(7)
    assert calculate_window(rows, 7, date(2026,10,8))['data_complete'] is False


def test_failed_weather_calls_release_locks(client, headers, monkeypatch):
    async def unavailable(*args):
        raise main.HTTPException(503,'offline')
    async def unavailable_archive(*args):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(main,'_open_meteo_weather',unavailable_archive)
    monkeypatch.setattr(main,'_nasa_weather',unavailable)
    assert client.post('/weather',json={'latitude':44.5,'longitude':11.3},headers=headers()).status_code==503
    assert main._weather_locks == {}
