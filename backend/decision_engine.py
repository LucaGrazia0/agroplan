"""Turn validated domain results into a parcel-specific, actionable response.

This layer composes the documented methods; it does not invent diagnostic
thresholds, probabilities, missing measurements or treatment prescriptions.
"""
from datetime import date
from agronomy_knowledge import VERSION
from manual_engine import day, number


def synthesize(review, crop=None, today=None):
    today = today or date.today()
    manual = review.get('manual_assessment') or {}
    findings = {f['rule_id']: f for domain in manual.get('domains', {}).values() for f in domain['findings']}
    crop = crop or {}
    soil = review.get('soil_context') or {}
    visual = review.get('visual_context') or {}
    latest = visual.get('latest')
    params = manual.get('parameters') or {}
    satellite = review.get('satellite') or {}
    water = findings.get('soil.available_water', {})
    weather = findings.get('weather.climatic_balance', {})
    soil_date = day(soil.get('sample_date'))
    soil_valid = soil_date is not None and soil_date <= today
    bbch = crop.get('latest_bbch') or {}
    bbch_day = day(bbch.get('observed_at'))
    valid_bbch = bbch_day is not None and 0 <= (today-bbch_day).days <= 21
    inputs = [
        {'id': 'crop', 'label': 'Coltura e fase', 'status': 'available' if crop and valid_bbch else 'partial' if crop else 'missing',
         'detail': f"{crop.get('crop', 'Coltura non registrata')}; " + (f"BBCH {bbch.get('bbch')} del {bbch_day}." if valid_bbch else 'fase attuale da rilevare.')},
        {'id': 'soil', 'label': 'Referto del suolo', 'status': 'available' if soil_valid else 'missing',
         'detail': f"Campione del {soil_date}; pH {soil.get('ph') if soil.get('ph') is not None else 'assente'}." if soil_valid else 'Nessun campione con data valida.'},
        {'id': 'weather', 'label': 'Meteo', 'status': 'available' if weather.get('status') == 'available' else 'missing',
         'detail': weather.get('evidence', 'Finestra meteo completa non disponibile.')},
        {'id': 'observations', 'label': 'Rilievi sulle piante', 'status': 'available' if latest else 'stale' if visual.get('record_count') else 'missing',
         'detail': f"Rilievo del {latest['observed_at']}; {visual.get('recent_count', 0)} rilievi negli ultimi 14 giorni." if latest else 'Nessun rilievo negli ultimi 14 giorni.'},
        {'id': 'satellite', 'label': 'Satellite', 'status': 'available' if satellite.get('delta') is not None else 'missing',
         'detail': f"NDVI: variazione {satellite['delta']:+.3f}; ultima acquisizione {satellite['latest']['observed_at']}." if satellite.get('delta') is not None else 'Confronto tra due acquisizioni valide non disponibile.'},
        {'id': 'water', 'label': 'Misure idriche', 'status': 'available' if water.get('status') == 'available' else 'missing',
         'detail': water.get('evidence', 'Misure del profilo radicale non disponibili.')},
    ]
    conclusions, gaps = [], []

    def add(key, title, explanation, action, input_ids, sources=(), priority='check'):
        conclusions.append(dict(id=key, title=title, explanation=explanation, action=action,
                                input_ids=input_ids, source_ids=list(sources), priority=priority))

    signs = set((latest or {}).get('symptoms', [])) - {'no_symptoms'}
    inferred = [e for e in (review.get('integrated_assessment') or {}).get('evidence', []) if e.get('source') == 'Parola nella nota da confermare']
    measured = day(params.get('observed_at'))
    moisture, fc, wp = (number(params.get(k)) for k in ('moisture_percent', 'field_capacity_percent', 'wilting_point_percent'))
    same_day_dry = (water.get('status') == 'available' and moisture is not None and measured is not None
                    and 0 <= (today-measured).days <= 7 and measured == day((latest or {}).get('observed_at')) and moisture <= wp)
    urgent = bool(signs and (latest.get('severity') == 'high' or (number(latest.get('affected_percent')) or 0) >= 30))
    if urgent:
        add('field_priority', 'La prima priorità è un sopralluogo',
            f"Il rilievo del {latest['observed_at']} indica sintomi intensi o diffusi. La priorità è organizzativa dell’app, non una soglia di trattamento.",
            'Verifica in campo estensione, evoluzione e radici; confronta i rilievi con un tecnico.', ['observations'], ['csu_diagnosis'], 'priority')
    if inferred:
        add('confirm_notes', 'Conferma i segnali descritti nelle note',
            'Nel testo riconosco: ' + ', '.join(e['label'] for e in inferred) + '. Sono indizi testuali, non osservazioni strutturate confermate.',
            'Se presenti, seleziona i sintomi nel rilievo e indica distribuzione e percentuale di piante.', ['observations'], ['csu_diagnosis'])
    aligned = 'problems.water_context' in findings
    if 'wilting' in signs and same_day_dry:
        add('wilting_soil', 'Appassimento e misura del suolo indicano una verifica idrica prioritaria',
            f'Il rilievo e la misura sono entrambi del {measured}: umidità {moisture:g}% in volume, punto di appassimento indicato {wp:g}%. '
            'Nel modello del profilo il valore è compatibile con disponibilità idrica molto ridotta. La coincidenza sostiene questa pista, senza provare che sia l’unica causa.',
            'Verifica subito misura, profondità e stato delle radici; confronta irrigazioni e distribuzione dei sintomi con un tecnico prima di decidere l’intervento.',
            ['observations', 'water'], ['fao56_8', 'csu_diagnosis'])
    elif 'wilting' in signs and aligned:
        balance = weather['values']['balance_mm']
        add('wilting_weather', 'Appassimento: verifica prima acqua e radici',
            f"Il rilievo ricade nel periodo meteo analizzato, con P − ET₀ pari a {balance:g} mm. " +
            ('Il saldo negativo rende utile verificare la disponibilità idrica, ma non prova uno stress della coltura.' if balance < 0 else 'Il saldo non negativo non garantisce umidità sufficiente e non esclude problemi radicali o di drenaggio.'),
            'Misura l’umidità alla profondità radicale e controlla irrigazioni, drenaggio e stato delle radici prima di decidere un intervento.',
            ['observations', 'weather', 'water'], ['fao56_8', 'csu_diagnosis'])
    elif 'wilting' in signs:
        add('wilting_unaligned', 'Appassimento: la causa non è ancora distinguibile',
            'Il sintomo è segnalato, ma manca un confronto meteo dello stesso periodo. Non attribuisco l’appassimento alla sola pioggia o al saldo climatico.',
            'Controlla umidità e radici e confronta dati meteo dello stesso periodo del rilievo.', ['observations', 'weather', 'water'], ['csu_diagnosis'])
    ph = findings.get('soil.ph_class', {})
    if 'yellowing' in signs:
        explanation = 'L’ingiallimento può avere cause diverse; il solo sintomo non identifica una carenza.'
        if ph.get('status') == 'available':
            explanation += f" Il referto del {soil_date} riporta pH {ph['values']['ph']:g} ({ph['values']['class']}): è un contesto da confrontare, non una prova della causa."
        add('yellowing_context', 'Ingiallimento: confronta foglie, radici e referto', explanation,
            'Annota se colpisce foglie giovani o vecchie e come è distribuito; verifica radici, umidità e metodi delle analisi prima di considerare una carenza.',
            ['observations', 'soil', 'water'], ['csu_diagnosis'] + (['usda_ph'] if ph.get('status') == 'available' else []))
    if signs & {'spots', 'insects'}:
        add('identify_damage', 'Identifica macchie e organismi prima di intervenire',
            'Il rilievo segnala macchie o insetti; presenza e danno non identificano automaticamente specie o patogeno.',
            'Rileva forma, posizione, estensione ed evoluzione delle lesioni e identifica gli organismi con un tecnico o un servizio diagnostico.', ['observations'], ['csu_diagnosis'])
    if 'uneven_growth' in signs:
        add('growth_distribution', 'Confronta le zone con sviluppo diverso',
            'La crescita irregolare richiede un confronto tra zone, fase colturale, radici e condizioni del suolo.',
            'Confronta piante sane e interessate nelle stesse condizioni; annota distribuzione, lavorazioni e irrigazioni.', ['observations', 'crop', 'soil'], ['csu_diagnosis'])
    if not ('wilting' in signs and same_day_dry) and water.get('status') == 'available' and moisture is not None and measured and 0 <= (today-measured).days <= 7 and (moisture <= wp or moisture > fc):
        add('water_measurement', 'Verifica il valore di umidità del profilo',
            f'La misura del {measured} è {moisture:g}% in volume; capacità di campo {fc:g}%, appassimento {wp:g}%. ' +
            ('Il valore è pari o inferiore al punto di appassimento inserito.' if moisture <= wp else 'Il valore supera la capacità di campo inserita.') +
            ' Non basta per attribuire una causa ai sintomi; i 7 giorni sono un criterio applicativo di aggiornamento.',
            'Verifica misura, unità e rappresentatività del profilo e controlla le piante nella stessa data.', ['water', 'observations'], ['fao56_8'])
    texture = findings.get('soil.texture_quality', {})
    if texture.get('status') == 'attention':
        add('quality_first', 'Correggi la tessitura prima di interpretarla', texture['evidence'], texture['next_check'], ['soil'], priority='data_quality')
    if satellite.get('delta') is not None:
        delta = satellite['delta']
        add('satellite_context', 'Confronta il segnale satellitare con il campo',
            f"NDVI {satellite['latest']['mean']:.3f} il {satellite['latest']['observed_at']}; variazione {delta:+.3f} dal {satellite['previous']['observed_at']}. La variazione non identifica da sola la causa.",
            'Confronta le date delle acquisizioni con il rilievo e la fase BBCH; verifica in campo le aree diverse.', ['satellite', 'observations', 'crop'], ['csu_diagnosis'])
    if latest and 'no_symptoms' in latest.get('symptoms', []):
        add('reported_no_symptoms', 'Nel rilievo non sono segnalati sintomi',
            f"L’operatore non ha osservato sintomi evidenti il {latest['observed_at']}. Questo non certifica lo stato sanitario della particella.",
            'Ripeti i rilievi nel tempo e confrontali con fase colturale e dati ambientali.', ['observations', 'crop'], ['csu_diagnosis'], 'monitor')
    if not signs and weather.get('status') == 'available':
        values = weather['values']
        add('water_context', 'Il meteo orienta il controllo dell’acqua',
            f"Nel periodo disponibile P − ET₀ è {values['balance_mm']:g} mm. " +
            (f"La capacità di riserva calcolata è {water['values']['taw_mm']:g} mm, ma non è la quantità attualmente disponibile né una dose irrigua." if water.get('status') == 'available' else 'La riserva radicale non è calcolabile con i dati attuali.'),
            'Confronta misure di umidità, irrigazioni e piogge effettivamente infiltrate prima di decidere come gestire l’acqua.', ['weather', 'water'], ['fao56_6', 'fao56_8'], 'monitor')
    for text in review.get('missing_data', []):
        if text not in gaps: gaps.append(text)
    for text in (review.get('integrated_assessment') or {}).get('questions', []):
        if text not in gaps: gaps.append(text)
    if crop and not valid_bbch:
        gaps.append('Registra una fase BBCH attuale nella sezione Coltura: non estrapolo la fase da un rilievo vecchio o futuro.')
    for f in findings.values():
        if f['status'] == 'missing' and f['next_check'] not in gaps: gaps.append(f['next_check'])
    if not latest:
        gaps.insert(0, 'Registra cosa osservi sulle piante, anche se non noti sintomi: serve per un ritorno sullo stato del campo.')
    if 'problems.time_alignment' in findings:
        gaps.append(findings['problems.time_alignment']['evidence'] + ' Servono date confrontabili per collegare sintomi e meteo.')
    sufficient = any(i['status'] == 'available' for i in inputs)
    status = 'priority_check' if urgent else 'needs_verification' if signs or inferred else 'incomplete' if gaps else 'monitoring'
    headline = ('Sopralluogo prioritario per i sintomi segnalati' if urgent else
                'Ci sono segnali da verificare incrociando i dati' if signs else
                'Conferma i sintomi descritti nel testo' if inferred else
                'Quadro disponibile: continua il monitoraggio' if not gaps else
                'Valutazione parziale: completa il quadro del campo' if sufficient else
                'Servono input per iniziare la valutazione')
    summary = ('La valutazione parte dal rilievo sulle piante e lo confronta con le misure compatibili per data e metodo.' if signs else
               'I dati disponibili orientano i controlli; i collegamenti non supportati restano esplicitamente da verificare.' if sufficient else
               'Inserisci almeno i dati colturali e un rilievo delle piante; aggiungi referto e meteo per distinguere le possibili cause.')
    priority_order = {'priority': 0, 'data_quality': 1, 'check': 2, 'monitor': 3}
    conclusions.sort(key=lambda c: priority_order[c['priority']])
    next_steps = list(dict.fromkeys([c['action'] for c in conclusions] + gaps))
    return dict(engine_version=VERSION, status=status, headline=headline, summary=summary, inputs=inputs,
                conclusions=conclusions, next_steps=next_steps, missing_inputs=gaps,
                references=manual.get('references', []),
                limits='Valutazione motivata dei dati inseriti: ipotesi da verificare, senza diagnosi automatica o dosi di trattamento.')
