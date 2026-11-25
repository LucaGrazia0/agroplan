"""Evidence ledger, focused differentials and discriminating next observations.

No statistical diagnostic probability is inferred from counts or weather.
Missing features are unknown, not negative tests. Multiple causes can coexist.
"""
from datetime import date
from agronomy_knowledge import VERSION, references
from manual_engine import day
from diagnostic_schema import SIGN_LABELS

WHEAT = {'frumento_tenero','frumento_duro'}
RULES = [
    ('yellow_rust','Ruggine gialla del frumento',{'yellowing','spots'},'yellow_pustule_rows',
     'Cerca pustole gialle in file sulla lamina; sulle piante giovani le strisce possono non essere evidenti.',
     'Confronta ruggine bruna e altre macchie; fai confermare i segni da un tecnico.', ['ahdb_yellow_rust']),
    ('brown_rust','Ruggine bruna del frumento',{'yellowing','spots'},'brown_pustules',
     'Osserva colore, disposizione e consistenza delle pustole con una lente.',
     'Distingui pustole sparse da strisce gialle; la foto da sola non conferma il patogeno.', ['jic_wheat_photos','aps_diagnosis']),
    ('powdery_mildew','Oidio dei cereali',{'spots'},'white_powder',
     'Verifica se sono presenti ciuffi o patina bianca superficiale, anche sulle foglie inferiori.',
     'Confronta residui di prodotti, polvere e lesioni senza crescita superficiale.', ['uc_small_grain_mildew']),
    ('septoria','Septoria del frumento',{'spots'},'black_dots_in_lesions',
     'Cerca piccoli punti neri nelle lesioni mature e confronta foglie inferiori e superiori.',
     'I picnidi possono mancare nelle lesioni giovani: la loro assenza non esclude septoria. Valuta altre maculature con un tecnico.', ['ahdb_septoria']),
    ('viral_syndrome','Virosi o alterazione di colore da distinguere',{'yellowing','uneven_growth'},'mosaic',
     'Confronta striature, colore, accrescimento e presenza di afidi; annota la distribuzione.',
     'Afidi o ingiallimento non provano una virosi. Servono identificazione e, quando indicato, analisi di laboratorio.', ['uc_bydv','aps_diagnosis']),
    ('nutrient_uptake','Nutrizione o assorbimento alterato',{'yellowing','uneven_growth'},'interveinal_yellowing',
     'Confronta foglie giovani e vecchie, radici e campioni di suolo e tessuto di zone sane e interessate.',
     'Non scegliere un nutriente dal solo colore: metodo analitico, coltura e campionamento contano.', ['csu_diagnosis']),
    ('feeding_damage','Danno da organismi fitofagi',{'insects','spots'},'chewing_or_holes',
     'Fotografa organismo e danno, anche sulla pagina inferiore; verifica se il danno è recente.',
     'La presenza di un insetto non dimostra che sia il responsabile; verifica specie, stadio e segni di alimentazione.', ['aps_diagnosis']),
    ('ear_problem','Sbiancamento della spiga da approfondire',{'spots','yellowing'},'bleached_ear',
     'Confronta singole spighette, intera spiga e base del culmo con piante sane.',
     'Vanno distinti problemi della spiga, del culmo e stress ambientali; chiedi un esame del campione prima di attribuire una specie.', ['aps_diagnosis']),
]


def build_center(review, records, crop=None, today=None):
    today=today or date.today()
    latest=(review.get('visual_context') or {}).get('latest')
    decision=review.get('decision_support') or {}
    if not latest:
        return {'version': VERSION,'status':'needs_observation','headline':'Inizia da un rilievo delle piante',
                'candidates':[],'questions':[], 'next_steps':['Aggiungi un rilievo in Problematiche, con data reale e sintomi osservati.'],
                'sources':references(['aps_diagnosis','csu_diagnosis']), 'coverage':decision.get('inputs',[])}
    observed=day(latest['observed_at'])
    details=latest.get('diagnostic_details') or {}
    signs=set(details.get('signs',[]));symptoms=set(latest.get('symptoms',[]))-{'no_symptoms'}
    crop_name=(crop or {}).get('crop');wheat=crop_name in WHEAT
    quality=list(decision.get('quality_notes',[]))
    if signs and 'no_symptoms' in latest.get('symptoms',[]):
        quality.append('Il rilievo indica assenza di sintomi ma contiene segni visibili da chiarire.')
    candidates=[]; questions=[]

    def add(key,title,support,against,missing,check,sources,targeted=False,category='general'):
        status='conflicting_inputs' if quality else 'less_supported' if against else 'focused' if targeted else 'to_verify'
        candidates.append(dict(id=key,title=title,status=status,supporting=support,contradicting=against,
                               missing=missing,next_check=check,source_ids=sources,category=category))

    for candidate in decision.get('differential',[]):
        if candidate['id'] in {'biotic','nutrition_physiology'}: continue
        add(candidate['id'],candidate['title'],candidate['supporting'],candidate['contradicting'],
            candidate['missing'],candidate['next_check'],candidate['source_ids'],candidate['status']=='consistent_inputs')
    for key,title,triggers,feature,check,alternative,sources in RULES:
        specific_crop=key in {'yellow_rust','brown_rust','septoria'}
        if specific_crop and not wheat: continue
        if not (symptoms & triggers or feature in signs): continue
        support=['Segno confermato dall’operatore: '+SIGN_LABELS[feature]+'.'] if feature in signs else []
        support+=['Sintomi generali compatibili, condivisi da più cause.'] if symptoms & triggers else []
        missing=[] if feature in signs else ['Il segno caratteristico non è ancora stato controllato; non viene considerato assente.']
        add(key,title,support,[],missing,check+' '+alternative,sources,feature in signs,'biotic' if key not in {'nutrient_uptake','ear_problem'} else 'general')
    pattern=details.get('field_pattern','unknown');event=details.get('recent_event','unknown')
    event_date=day(details.get('event_date'));onset=day(latest.get('noticed_since'))
    if symptoms and (pattern in {'spray_width','field_edge'} or event in {'spray','fertilizer'}):
        support=['Distribuzione o attività colturale dichiarata merita un confronto con i sintomi.']
        against=[]
        if event_date and onset and event_date>onset: against.append('L’evento è successivo all’esordio riferito: non spiega l’inizio dei sintomi.')
        missing=[] if event_date and onset else ['Mancano date confrontabili di evento ed esordio.']
        add('application_injury','Fitotossicità, distribuzione o deriva da verificare',support,against,missing,
            'Confronta fasce di passaggio, bordi e zone non esposte; annota prodotto e data con il tecnico. La forma del danno non basta a dimostrare fitotossicità.',
            ['aps_diagnosis','unl_distribution'],bool(event_date and onset and event_date<=onset and pattern=='spray_width'))
    if symptoms and pattern in {'low_spots','traffic_lines'}:
        add('physical_soil','Drenaggio o limitazione fisica del suolo',
            ['Distribuzione in avvallamenti o lungo tracce dichiarata.'],[],['Mancano confronto del profilo radicale e misure fisiche rappresentative.'],
            'Confronta radici, umidità, struttura e profondità esplorata in zone sane e interessate; il solo disegno delle chiazze non dimostra compattamento o ristagno.', ['unl_distribution','csu_diagnosis'])
    if symptoms and event in {'frost','hail'}:
        against=['Evento successivo all’esordio: non spiega la comparsa iniziale.'] if event_date and onset and event_date>onset else []
        add('weather_event','Danno fisico da evento meteorologico da verificare',
            ['Evento dichiarato: '+event+'.'],against,[] if event_date and onset else ['Mancano date confrontabili.'],
            'Verifica organi e zone esposte e confronta la cronologia. Il meteo su griglia non prova gelo o grandine nella particella.', ['aps_diagnosis'])
    # Explicitly retain alternatives even after observing a characteristic sign.
    if symptoms and not any(c['id']=='nutrient_uptake' for c in candidates):
        add('abiotic_other','Cause abiotiche o altre cause non ancora distinte',[],[],
            ['Mancano misure o un’identificazione che consentano di restringere questa famiglia.'],
            'Confronta radici, acqua, nutrizione, lavorazioni ed esposizioni. Più cause possono essere presenti insieme.', ['aps_diagnosis','csu_diagnosis'])
    for q in decision.get('questions',[]): questions.append(dict(q, kind='record'))
    if symptoms:
        for field,text,reason in [
            ('signs','Quali segni riesci a vedere da vicino?','Distingue pustole, patina, lesioni con puntini neri e danni non specifici.'),
            ('field_pattern','Il danno segue una zona o un percorso del campo?','Confronta avvallamenti, passaggi dei mezzi, fasce e piante sparse.'),
            ('recent_event','Che cosa è successo prima della comparsa dei sintomi?','Serve per confrontare eventi colturali e cause biotiche, senza assumere causalità.'),
            ('progression','Il problema è comparso di colpo o si sta estendendo?','L’andamento può orientare i controlli; esistono eccezioni e cause concomitanti.')]:
            if (not signs if field=='signs' else details.get(field,'unknown')=='unknown'):
                questions.append(dict(id='focus_'+field,field=field,text=text,reason=reason,kind='focus'))
    order={'focused':0,'to_verify':1,'less_supported':2,'conflicting_inputs':3}
    candidates.sort(key=lambda c:order[c['status']])
    source_ids=[s for c in candidates for s in c['source_ids']]+['aps_diagnosis','jic_wheat_photos']
    weather=review.get('observation_weather')
    progression=details.get('progression','unknown')
    temporal_note={'spreading':'Estensione dichiarata: confronta piante e zone nel tempo; non prova trasmissione di un patogeno.',
                   'sudden':'Comparsa improvvisa dichiarata: confronta eventi ed esposizioni, senza escludere cause biotiche.',
                   'stable':'Stabilità dichiarata: non dimostra che la causa sia risolta.'}.get(progression,'Andamento non ancora descritto.')
    limits=['Ordine basato sul tipo di riscontro, non su probabilità di malattia.',
            'Il catalogo specifico è inizialmente limitato al frumento; altre colture mantengono solo controlli generali.',
            'Assenza di un segno non verificato o di dati meteo non esclude una causa.',
            'Nessuna indicazione di prodotto o dose è generata.']
    if weather: limits.append('Il meteo dei 14 giorni precedenti è contesto: non ricostruisce infezioni latenti, bagnatura fogliare o presenza di inoculo.')
    return dict(version=VERSION,observation_id=latest.get('id'),observation_date=str(observed),
                status='conflicting_inputs' if quality else 'investigation' if symptoms or signs else 'monitoring',
                headline='Chiarisci i dati discordanti' if quality else 'Piste più circoscritte e prossime verifiche' if signs else 'Raccogli i dettagli che distinguono le cause',
                candidates=candidates,questions=questions,quality_notes=quality,details=details,
                next_steps=list(dict.fromkeys([q['text'] for q in questions[:3]]+[c['next_check'] for c in candidates[:3]])),
                sources=references(source_ids),coverage=decision.get('inputs',[]),limitations=limits,temporal_note=temporal_note)
