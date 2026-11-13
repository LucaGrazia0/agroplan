"""Provider checks shared by the UI and command-line diagnostics."""
from datetime import date
import httpx

from soil_sources import search_soil


def provider_checks(backend):
    def request(req):
        return backend.WeatherRequest(latitude=req.latitude,longitude=req.longitude,history_days=30)

    async def copernicus(req):
        await backend.get_token()
        return {'status':'ok','message':'Credenziali accettate da Copernicus.'}

    async def archive(req):
        result=await backend._open_meteo_weather(request(req),date.today())
        return {'status':'ok','message':f"Storico di {len(result['history'])} giorni disponibile con ET0."}

    async def nasa(req):
        result=await backend._nasa_weather(request(req),date.today())
        return {'status':'ok','message':f"Storico di riserva disponibile fino al {result['historical_end']}."}

    async def forecast(req):
        current,days=await backend._met_norway_weather(request(req))
        if not current or not days:
            raise ValueError('Previsioni assenti')
        return {'status':'ok','message':f'Condizioni attuali e {len(days)} giorni di previsioni disponibili.'}

    async def soil(req):
        result=await search_soil([{'lat':req.latitude,'lng':req.longitude},
            {'lat':req.latitude+.001,'lng':req.longitude},{'lat':req.latitude,'lng':req.longitude+.001}])
        return {'status':'ok' if result['status']=='ok' else 'not_covered' if result['status']=='no_provider' else 'unavailable',
                'message':f"{len(result['results'])} punti cartografici disponibili." if result['status']=='ok' else result['message']}

    async def tile(url):
        async with httpx.AsyncClient(timeout=12,headers={'User-Agent':'AgroPlan/0.3 (+https://github.com/LucaGrazia0)'}) as client:
            response=await client.get(url)
            response.raise_for_status()
            if not response.headers.get('content-type','').startswith('image/'):
                raise ValueError('Il servizio non restituisce una mappa')
        return {'status':'ok','message':'Immagini della mappa disponibili.'}

    async def osm(req): return await tile('https://tile.openstreetmap.org/0/0/0.png')
    async def imagery(req): return await tile('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/0/0/0')
    return {'copernicus':copernicus,'open_meteo':archive,'nasa_power':nasa,'met_norway':forecast,
            'soil_rer':soil,'osm':osm,'imagery':imagery}
