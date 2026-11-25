"""Geographic soil source discovery; WMS GetFeatureInfo, no invented lab values."""
from __future__ import annotations
import asyncio
import json
import math
import xml.etree.ElementTree as ET
import httpx

RER_WMS = 'https://servizigis.regione.emilia-romagna.it/wms/suoli'
RER_SOURCE = 'Regione Emilia-Romagna — Carta dei suoli 1:50.000 (2021)'
RER_URL = 'https://geoportale.regione.emilia-romagna.it/catalogo/dati-cartografici/informazioni-geoscientifiche/suoli/layer-33'


def _valid_points(points):
    if not isinstance(points, list) or not 3 <= len(points) <= 2000:
        raise ValueError('Sono richiesti 3–2000 vertici del poligono')
    out = []
    for p in points:
        if not isinstance(p, dict):
            raise ValueError('Vertice non valido')
        lat, lon = float(p['lat']), float(p['lng'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Coordinate fuori intervallo')
        out.append((lat, lon))
    return out


def _sample(points):
    # Approximate representative sample, not polygon overlay/area weighting.
    center = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
    return [center] + [((center[0]+p[0])/2, (center[1]+p[1])/2) for p in points[:4]]


def _within_rer(lat, lon):
    return 43.703388 <= lat <= 45.169558 and 9.172921 <= lon <= 12.850398


def _queryable_layers(xml_data):
    root = ET.fromstring(xml_data)
    found = set()
    for el in root.iter():
        if el.tag.split('}')[-1] != 'Layer':
            continue
        name = None
        for child in el:
            if child.tag.split('}')[-1] == 'Name':
                name = (child.text or '').strip()
                break
        if name:
            found.add(name)
    return found


async def search_soil(points):
    coords = _valid_points(points)
    samples = _sample(coords)
    eligible = [p for p in samples if _within_rer(*p)]
    if not eligible:
        return {'status':'no_provider', 'sources_checked':[], 'results':[], 'message':'Nessuna fonte geografica automatica configurata per questa zona. Non significa che non esistano dati pedologici.'}
    provider = {'name':RER_SOURCE,'url':RER_URL,'scale':'1:50.000','type':'cartografia pedologica, non analisi di laboratorio'}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            cap = await client.get(RER_WMS, params={'service':'WMS','request':'GetCapabilities','version':'1.1.1'})
            cap.raise_for_status()
            layers = _queryable_layers(cap.content)
            if 'Carta_Suoli_50k' not in layers:
                return {'status':'unavailable','sources_checked':[provider],'results':[], 'message':'Il layer Carta_Suoli_50k non è stato trovato nel servizio WMS.'}
            async def get_info(lat, lon):
                # 101x101 image, coordinate sampled at pixel 50,50; WMS 1.1.1 uses SRS lon/lat.
                delta = 0.004
                params = {'SERVICE':'WMS','VERSION':'1.1.1','REQUEST':'GetFeatureInfo',
                          'LAYERS':'Carta_Suoli_50k','QUERY_LAYERS':'Carta_Suoli_50k',
                          'SRS':'EPSG:4326','BBOX':f'{lon-delta},{lat-delta},{lon+delta},{lat+delta}',
                          'WIDTH':'101','HEIGHT':'101','X':'50','Y':'50','INFO_FORMAT':'text/plain',
                          'FEATURE_COUNT':'5','FORMAT':'image/png','STYLES':''}
                r = await client.get(RER_WMS, params=params)
                r.raise_for_status()
                txt = r.text[:16000]
                if '<ServiceException' in txt or '<ExceptionReport' in txt:
                    raise ValueError('GetFeatureInfo non supportato dal servizio')
                return {'latitude':lat,'longitude':lon,'response':txt,'soil_units':parse_soil_units(txt)}
            checked = await asyncio.gather(*(get_info(*p) for p in eligible[:5]),return_exceptions=True)
            results = [x for x in checked if isinstance(x,dict) and x.get('soil_units')]
            failures = [str(x) for x in checked if isinstance(x,Exception)]
            return {'status':'ok' if results else 'unavailable', 'sources_checked':[provider],
                    'results':results, 'sample_count':len(eligible[:5]),
                    'message': 'Informazioni cartografiche grezze: da verificare prima di interpretare parametri chimici.' if results else 'Il servizio non ha restituito informazioni interpretabili.',
                    'warnings':failures[:2]}
    except (httpx.HTTPError, ValueError, ET.ParseError) as e:
        return {'status':'unavailable','sources_checked':[provider],'results':[], 'message':f'Servizio cartografico temporaneamente non disponibile: {type(e).__name__}'}


def parse_soil_units(raw):
    """Read the provider's flattened semicolon records without guessing lab data.

    Descriptive fields can themselves contain unescaped semicolons, so only
    the stable identifier/name prefix is labelled. Descriptive fragments keep
    their original text rather than being assigned to shifted column names.
    """
    import csv
    import re
    units=[]
    for table in re.split(r'@Carta_Suoli_50k\s*', raw)[1:]:
        try:
            cells=[cell.strip() for cell in next(csv.reader([table],delimiter=';'))]
            end=next(i for i,cell in enumerate(cells) if cell.upper()=='SHAPE.LEN')+1
        except (csv.Error,StopIteration):
            continue
        headers=cells[:end]
        values=cells[end:]
        if len(values)<9 or not values[0].isdigit() or 'NOME_UC' not in headers:
            continue
        name_index=headers.index('NOME_UC')
        code_index=headers.index('Sigla unità cart.') if 'Sigla unità cart.' in headers else None
        name=values[name_index] if name_index<len(values) else ''
        if not name:
            continue
        descriptions=[]
        for cell in values[name_index:]:
            if cell.startswith('http') or len(cell)<24 or len(cell)>2000:
                continue
            if re.search(r'[a-zA-ZÀ-ÿ]{4,}\s+[a-zA-ZÀ-ÿ]{3,}',cell) and cell not in descriptions:
                descriptions.append(cell)
        units.append({'name':name,'code':values[code_index] if code_index is not None else '',
                      'descriptions':descriptions[:8]})
    return units
