"""Evidence-based crop review. Missing observations stay missing."""
from datetime import date, datetime, timezone
import json
import hashlib
from storage import connect
from phenology import assess, parse_day


def saved_context(parcel_id):
    with connect() as db:
        soil = db.execute('SELECT * FROM agr_soil_analyses WHERE parcel_id=? ORDER BY sample_date DESC,id DESC LIMIT 1', (parcel_id,)).fetchone()
        parcel = db.execute('SELECT payload FROM agr_parcels WHERE id=?', (parcel_id,)).fetchone()
        points = json.loads(parcel['payload']).get('points', []) if parcel and parcel['payload'] else []
        observations = [dict(r) for r in db.execute('SELECT observed_at,mean,valid_percent FROM agr_satellite_observations WHERE parcel_id=? AND geometry_hash=? ORDER BY observed_at DESC LIMIT 6', (parcel_id, geometry_hash(points)))]
    return dict(soil) if soil else None, observations


def geometry_hash(points):
    return hashlib.sha256(json.dumps(points, sort_keys=True).encode()).hexdigest()


def build_crop_review(crop, soil, satellite, windows=None, geometry_available=False, today=None):
    today = today or date.today()
    checks, gaps = [], []
    bbch = (crop or {}).get('latest_bbch')
    phase = assess(crop,today)
    quality = {'crop': crop is not None, 'bbch': phase['usable_for_current_analysis'],
               'soil': soil is not None, 'geometry': geometry_available,
               'weather_7_days': bool((windows or {}).get('7', {}).get('data_complete'))}
    if not crop:
        gaps.append('Registra il ciclo colturale per contestualizzare le osservazioni.')
    elif not crop.get('sowing_date'):
        gaps.append('Data di semina assente: durata del ciclo e sviluppo termico non valutabili.')
    if bbch:
        observed = parse_day(bbch.get('observed_at'))
        age = (today - observed).days if observed else None
        if age is not None and age > 21:
            checks.append({'title': 'Aggiorna il rilievo BBCH', 'evidence': f'Ultimo rilievo di {age} giorni fa.', 'action': 'Rileva la fase attuale in campo: non viene estrapolata da una vecchia osservazione.'})
        elif age is None or age < 0:
            gaps.append('Il rilievo BBCH è datato nel futuro: correggi la data prima di interpretarlo.')
    else:
        gaps.append('Fase BBCH non disponibile: serve un rilievo in campo.')
    gaps.extend(phase['quality_notes'])
    if bbch and phase['status'] in {'unmapped','unsupported'}:
        gaps.append(phase['description'])
    if soil:
        soil = {key: value for key, value in soil.items() if key not in {'notes','client_id'}}
        age = (today - date.fromisoformat(soil['sample_date'])).days
        if age < 0:
            gaps.append('Campione del suolo con data futura: verificare il record.')
        checks.append({'title': 'Confronta il campione del suolo',
                       'evidence': f"Campione del {soil['sample_date']}; fonte: {soil['source']}; pH: {soil.get('ph') if soil.get('ph') is not None else 'non disponibile'}.",
                       'action': 'Verifica rappresentatività, profondità e metodo analitico. I nutrienti totali non equivalgono alla quota disponibile per la coltura.'})
    else:
        gaps.append('Analisi del suolo assente: nessuna dose di fertilizzante o diagnosi di carenza viene dedotta.')
    if not geometry_available:
        gaps.append('Confini della particella mancanti: importa o disegna il poligono per collegare i dati satellitari.')
    # Compare only sufficiently covered, distinct, recent acquisitions.
    valid = {}
    for item in satellite:
        day = date.fromisoformat(item['observed_at'])
        if 0 <= (today - day).days <= 45 and item.get('valid_percent', 0) is not None and item['valid_percent'] >= 50 and item.get('mean') is not None:
            valid[item['observed_at']] = item
    series = sorted(valid.values(), key=lambda x: x['observed_at'], reverse=True)
    quality['satellite'] = len(series) >= 2
    ndvi = {'status': 'insufficient_data', 'latest': series[0] if series else None, 'previous': None, 'delta': None}
    if len(series) >= 2:
        latest, previous = series[:2]
        delta = round(latest['mean'] - previous['mean'], 3)
        ndvi.update(status='available', previous=previous, delta=delta)
        checks.append({'title': 'Confronta la vegetazione osservata',
                       'evidence': f"NDVI {latest['mean']:.3f} il {latest['observed_at']}; variazione {delta:+.3f} rispetto al {previous['observed_at']}.",
                       'action': 'Confronta andamento, fase BBCH e sopralluogo. La variazione NDVI non identifica da sola malattie, carenze o resa.'})
    else:
        gaps.append('Servono due acquisizioni satellitari recenti con almeno il 50% di pixel validi per confrontare l’NDVI.')
    balance = (windows or {}).get('7', {}).get('climatic_balance_mm')
    if balance is not None and balance < 0:
        checks.append({'title': 'Verifica la disponibilità idrica in campo',
                       'evidence': f'Precipitazioni meno ET₀ negli ultimi 7 giorni: {balance:.1f} mm.',
                       'action': 'Controlla umidità del suolo e irrigazioni. Questo bilancio climatico non misura lo stress idrico né determina una dose irrigua.'})
    review = {'generated_at': datetime.now(timezone.utc).isoformat(),
            'summary': f"{(crop or {}).get('crop', 'Coltura non registrata')}: {sum(quality.values())} ambiti con dati su {len(quality)}. " + ('Sono necessari nuovi rilievi per completare la valutazione.' if gaps else 'Confronta gli indicatori con i rilievi in campo.'),
            'coverage': quality, 'soil_context': soil, 'satellite': ndvi, 'phenology': phase,
            'checks': checks, 'missing_data': gaps,
            'method': 'Sintesi deterministica dei record aziendali e delle osservazioni disponibili; nessun dato inventato e nessun modello diagnostico o di resa.',
            'references': [{'title': 'FAO 56: ET₀ ed evapotraspirazione colturale', 'url': 'https://www.fao.org/4/x0490e/x0490e0a.htm'}]}

    review['climatic_balance_7d'] = balance
    return review


def farm_overview(user):
    from agronomy_engine import crop_context
    with connect() as db:
        parcels = [dict(row) for row in db.execute('SELECT * FROM agr_parcels WHERE farm_id=? AND deleted=0 ORDER BY id', (user.farm_id,))]
    reviews = []
    for row in parcels:
        payload = json.loads(row['payload']) if row['payload'] else {}
        soil, satellite = saved_context(row['id'])
        reviews.append({'parcel_id': row['id'], 'name': payload.get('name', 'Particella da recuperare'),
                        'crop_context': crop_context(row['id'], None),
                        'review': build_crop_review(crop_context(row['id'], None), soil, satellite,
                                                   geometry_available=bool(payload.get('points')))})
    from evidence_engine import integrate
    from field_records import observations
    from analysis_parameters import parameters
    for item in reviews:
        item['review'] = integrate(item['review'], observations(item['parcel_id']),crop=item['crop_context'],parameters=parameters(item['parcel_id']))
    return {'farm_id': user.farm_id, 'parcel_count': len(reviews), 'parcels': reviews,
            'note': 'Riepilogo dei dati salvati: meteo aggiornato e nuove acquisizioni si richiedono nell’analisi della singola particella.'}
