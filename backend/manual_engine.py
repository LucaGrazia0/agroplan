"""Auditable agronomic methods with prerequisites, equations and provenance."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import math
from agronomy_knowledge import VERSION, references


def number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def day(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def finding(rule, title, status, evidence, interpretation, action, sources, **extra):
    return dict(rule_id=rule, title=title, status=status, evidence=evidence,
                interpretation=interpretation, next_check=action, source_ids=sources, **extra)


def evaluate(review, crop=None, windows=None, parameters=None, today=None):
    today = today or date.today()
    windows, params = windows or {}, parameters or {}
    domains = {key: {'findings': []} for key in ('soil', 'weather', 'problems')}
    soil_rows, weather_rows, problem_rows = (domains[key]['findings'] for key in domains)
    soil = review.get('soil_context') or {}
    sampled = day(soil.get('sample_date'))
    soil_valid = sampled is not None and sampled <= today
    ph = number(soil.get('ph')) if soil_valid else None
    if ph is not None and 0 <= ph <= 14:
        # Table 3-15 is expressed to one decimal place; ties round upwards.
        rounded = float(Decimal(str(ph)).quantize(Decimal('.1'), rounding=ROUND_HALF_UP))
        boundaries = [(3.5, 'ultra acido'), (4.5, 'estremamente acido'), (5.1, 'molto fortemente acido'),
                      (5.6, 'fortemente acido'), (6.1, 'moderatamente acido'), (6.6, 'leggermente acido'),
                      (7.4, 'neutro'), (7.9, 'leggermente alcalino'), (8.5, 'moderatamente alcalino'),
                      (9.1, 'fortemente alcalino'), (float('inf'), 'molto fortemente alcalino')]
        label = next(label for upper, label in boundaries if rounded < upper)
        soil_rows.append(finding('soil.ph_class', 'Reazione del suolo', 'available',
                                 f'pH {ph:g}; campione del {sampled}; fonte: {soil.get("source", "non indicata")}.',
                                 f'Classe descrittiva USDA: {label}. Non determina da sola disponibilità dei nutrienti o idoneità della coltura.',
                                 'Confronta metodo di misura, profondità e rappresentatività del campione; nessuna correzione calcica viene calcolata.',
                                 ['usda_ph'], values={'ph': ph, 'class': label},
                                 limitations=['Metodo del pH non strutturato nei record attuali: la classe è descrittiva, non una raccomandazione.']))
    else:
        soil_rows.append(finding('soil.ph_class', 'Reazione del suolo', 'missing',
                                 'Nessun pH valido con data di campionamento non futura.',
                                 'Classificazione non calcolata.', 'Inserisci il referto con pH, data e metodo nelle note.', ['usda_ph']))
    texture = [number(soil.get(k)) for k in ('sand_percent', 'silt_percent', 'clay_percent')]
    if soil_valid and all(v is not None for v in texture):
        total = sum(texture)
        coherent = all(0 <= v <= 100 for v in texture) and abs(total - 100) <= 2
        soil_rows.append(finding('soil.texture_quality', 'Controllo dei dati di tessitura', 'available' if coherent else 'attention',
                                 f'Sabbia {texture[0]:g}%, limo {texture[1]:g}%, argilla {texture[2]:g}%; somma {total:g}%.',
                                 'Percentuali coerenti.' if coherent else 'Percentuali incoerenti: non uso la tessitura per dedurre proprietà idriche.',
                                 'Controlla il referto. La tolleranza di 2 punti percentuali è un controllo applicativo per gli arrotondamenti, non una soglia agronomica.',
                                 [], values={'sum_percent': total}))
    soil_rows.append(finding('soil.nutrients_gate', 'Nutrienti e fertilità', 'partial' if soil_valid else 'missing',
                             'Il referto distingue azoto totale e valori di fosforo/potassio; mancano metodi analitici strutturati e tarature locali.',
                             'Non vengono convertiti in una diagnosi di carenza o in dosi di concime.',
                             'Confronta il laboratorio e le indicazioni regionali per coltura, resa obiettivo e metodo di estrazione.', [],
                             limitations=['Modulo di bilancio nutritivo e tarature regionali non ancora implementati.']))

    fc, wp, depth, moisture = (number(params.get(k)) for k in ('field_capacity_percent', 'wilting_point_percent', 'root_depth_m', 'moisture_percent'))
    measured = day(params.get('observed_at'))
    valid_water = measured is not None and measured <= today and fc is not None and wp is not None and depth is not None and 0 <= wp < fc <= 100 and 0 < depth <= 5
    if valid_water:
        taw = 1000 * (fc - wp) / 100 * depth
        values = {'taw_mm': round(taw, 2), 'observed_at': measured.isoformat()}
        evidence = f'Capacità di campo {fc:g}% vol.; appassimento {wp:g}% vol.; profondità radicale {depth:g} m. Dati del {measured}.'
        if moisture is not None and 0 <= moisture <= 100:
            values['depletion_mm'] = round(min(taw, max(0, (fc - moisture) / 100 * 1000 * depth)), 2)
            evidence += f' Umidità misurata {moisture:g}% vol.; esaurimento stimato {values["depletion_mm"]:g} mm (limitato tra 0 e TAW).'
        soil_rows.append(finding('soil.available_water', 'Riserva idrica nella zona radicale', 'available', evidence,
                                 f'Acqua totale disponibile (TAW): {taw:.1f} mm. È una capacità del profilo, non l’acqua da irrigare.',
                                 'Verifica che le misure rappresentino lo stesso profilo e la profondità radicale attuale.', ['fao56_8'], values=values,
                                 equation='TAW = 1000 × (θFC − θWP) × Zr; θ in m³/m³, Zr in m',
                                 limitations=['Modello uniforme nella zona radicale; non include strati, salinità, falda o bilancio giornaliero.',
                                              'La dose irrigua non è calcolata; RAW e Ks richiedono un p effettivo verificato e sono riportati separatamente.']))
    else:
        soil_rows.append(finding('soil.available_water', 'Riserva idrica nella zona radicale', 'missing',
                                 'Servono capacità di campo, punto di appassimento e profondità radicale misurati.',
                                 'TAW non calcolata; nessun valore viene stimato dalla sola tessitura.',
                                 'Completa i parametri idrici nella sezione Suolo se disponi delle misure.', ['fao56_8']))

    from water_methods import measured_water, irrigation_quality
    soil_rows.append(measured_water(params, today))
    soil_rows.extend(irrigation_quality(params, today))

    seven = windows.get('7') or {}
    start, end = day(seven.get('start_date')), day(seven.get('end_date'))
    rain, et0 = number(seven.get('rain_mm')), number(seven.get('et0_mm'))
    weather_valid = seven.get('data_complete') is True and start is not None and end is not None and end <= today and (end-start).days == 6 and rain is not None and et0 is not None and rain >= 0 and et0 >= 0
    if weather_valid:
        balance = round(rain-et0, 2)
        weather_rows.append(finding('weather.climatic_balance', 'Pioggia ed evapotraspirazione', 'available',
                                    f'Dal {start} al {end}: pioggia {rain:g} mm, ET₀ {et0:g} mm.',
                                    f'Bilancio climatico P − ET₀: {balance:g} mm. Non equivale al bilancio della zona radicale.',
                                    'Confronta irrigazioni, infiltrazione e misure del suolo prima di interpretare la disponibilità idrica.', ['fao56_6', 'fao56_8'],
                                    values={'rain_mm': rain, 'et0_mm': et0, 'balance_mm': balance}, equation='P − ET₀'))
    else:
        weather_rows.append(finding('weather.climatic_balance', 'Pioggia ed evapotraspirazione', 'missing',
                                    'Finestra di 7 giorni assente o incompleta.', 'Bilancio non calcolato; dati mancanti diversi da zero.',
                                    'Aggiorna il meteo e controlla le date effettivamente disponibili.', ['fao56_6']))
    kc = number(params.get('kc'))
    kc_from, kc_to = day(params.get('kc_from')), day(params.get('kc_to'))
    if weather_valid and kc is not None and 0 < kc <= 2.5 and kc_from and kc_to and kc_from <= start <= end <= kc_to <= today:
        etc = round(kc*et0, 2)
        weather_rows.append(finding('weather.crop_et', 'Evapotraspirazione colturale standard', 'available',
                                    f'Kc {kc:g} fornito dall’operatore per l’intero periodo {start}–{end}; ET₀ {et0:g} mm.',
                                    f'ETc standard stimata: {etc:g} mm nei 7 giorni. Non è una dose irrigua né il consumo effettivo in condizioni di stress.',
                                    'Verifica Kc per coltura, copertura e condizioni locali con la tabella 12 e le correzioni FAO.', ['fao56_6'],
                                    values={'kc': kc, 'etc_mm': etc}, equation='ETc = Kc × ET₀',
                                    limitations=['Kc costante nell’intervallo dichiarato; non interpolato dal BBCH e non corretto automaticamente per clima e bagnature.']))
    else:
        weather_rows.append(finding('weather.crop_et', 'Evapotraspirazione colturale standard', 'missing',
                                    'Occorrono meteo completo e Kc verificato che copra tutto il periodo.',
                                    'ETc non calcolata. Il BBCH non viene trasformato automaticamente in Kc.',
                                    'Se disponibile, inserisci Kc e il suo intervallo di validità nei parametri della sezione Meteo.', ['fao56_6']))

    assessment = review.get('integrated_assessment') or {}
    latest = (review.get('visual_context') or {}).get('latest')
    signs = set((latest or {}).get('symptoms', [])) - {'no_symptoms'}
    observed = day((latest or {}).get('observed_at'))
    for index, hypothesis in enumerate(assessment.get('hypotheses', [])):
        problem_rows.append(finding(f'problems.differential.{index}', 'Cause da distinguere in campo', 'partial',
                                    hypothesis['evidence'], hypothesis['hypothesis'], hypothesis['next_check'], ['csu_diagnosis'],
                                    limitations=['Il metodo è generale: nessuna identificazione di patogeno o soglia di trattamento è implementata.']))
    if signs and weather_valid and observed and start <= observed <= end:
        problem_rows.append(finding('problems.water_context', 'Confronto tra sintomi e meteo', 'partial',
                                    f'Rilievo del {observed} nel periodo meteorologico {start}–{end}; P − ET₀ {rain-et0:.1f} mm.',
                                    'I dati sono temporalmente confrontabili, ma non dimostrano una causa comune.',
                                    'Verifica umidità e radici: appassimento e ingiallimento possono avere più cause.', ['fao56_8', 'csu_diagnosis']))
    elif signs and weather_valid:
        problem_rows.append(finding('problems.time_alignment', 'Date da riallineare', 'partial',
                                    f'Rilievo del {observed}; meteo dal {start} al {end}.',
                                    'Il rilievo è fuori dalla finestra meteo: non attribuisco il sintomo al bilancio di questi giorni.',
                                    'Attendi dati meteorologici dello stesso periodo o aggiungi un rilievo datato correttamente.', ['csu_diagnosis']))
    if not problem_rows:
        problem_rows.append(finding('problems.observation_gate', 'Osservazione delle piante', 'partial' if latest else 'missing',
                                    'Ultimo rilievo recente senza sintomi riconosciuti.' if latest else 'Nessun rilievo visivo degli ultimi 14 giorni.',
                                    'Assenza di segnalazioni non significa assenza di problematiche.',
                                    'Registra sintomi, distribuzione, evoluzione e parti interessate nella sezione Problematiche.', ['csu_diagnosis']))
    for key, domain in domains.items():
        rows = domain['findings']
        domain['status'] = 'attention' if any(r['status']=='attention' for r in rows) else 'partial' if any(r['status'] in {'partial','missing'} for r in rows) else 'available'
        domain['computed_count'] = sum(r['status']=='available' for r in rows)
        domain['summary'] = {'soil': 'Referto, qualità dei dati e riserva idrica.', 'weather': 'Finestre meteorologiche e calcoli dell’acqua.', 'problems': 'Sintomi, possibili cause e verifiche in campo.'}[key]
    source_ids = [s for d in domains.values() for f in d['findings'] for s in f['source_ids']]
    return {'engine_version': VERSION, 'domains': domains, 'references': references(source_ids),
            'method': 'Metodi numerici e regole documentati, con prerequisiti e provenienza per ogni risultato.',
            'scope': 'pH descrittivo, qualità del referto, TAW, RAW/Ks alla misura, confronto ECw–SAR dell’acqua irrigua, P − ET₀, ETc standard e indagine dei sintomi. Tarature nutritive, modelli patogeno-specifici e dosi non implementati.',
            'parameters': params}
