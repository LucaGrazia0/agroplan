"""History comparison, explicit competing explanations, and answerable questions."""
from datetime import date
from manual_engine import day, number

SEVERITY = {'mild':0, 'moderate':1, 'high':2}


def context(record):
    return tuple(record.get(k, 'unknown') for k in ('plant_part','leaf_age','distribution'))


def compare_observations(records, latest, today):
    if not latest:
        return {'status':'insufficient','summary':'Aggiungi un rilievo recente per iniziare il confronto.','points':[],'limitations':[]}
    unique = {}
    for r in records:
        observed = day(r.get('observed_at'))
        if observed and 0 <= (today-observed).days <= 30:
            key = r.get('id') or (r['observed_at'],r.get('created_at'),context(r),tuple(sorted(r.get('symptoms',[]))),r.get('affected_percent'),r.get('severity'))
            unique[key] = r
    earlier = sorted((r for r in unique.values() if r['observed_at'] < latest['observed_at']),key=lambda r:(r['observed_at'],r.get('created_at','')),reverse=True)
    previous = next((r for r in earlier if context(r)==context(latest)), None)
    limitations=['Confronto descrittivo delle segnalazioni, non misura validata dell’evoluzione sanitaria. Campionamento e zona devono essere confrontabili.',
                 'Finestra di 30 giorni e criteri di comparabilità sono scelte applicative.']
    if not previous:
        return {'status':'insufficient','summary':'Manca un rilievo di un giorno precedente con la stessa parte della pianta e gli stessi dettagli di osservazione.','points':[],'limitations':limitations}
    points=[{k:r.get(k) for k in ('id','created_at','observed_at','symptoms','severity','affected_percent','plant_part','leaf_age','distribution')} for r in (previous,latest)]
    old_signs=set(previous.get('symptoms',[]))-{'no_symptoms'}
    signs=set(latest.get('symptoms',[]))-{'no_symptoms'}
    result={'status':'changed','summary':'Le segnalazioni sono cambiate: confronta i sintomi descritti.','points':points,'limitations':limitations}
    if 'no_symptoms' in previous.get('symptoms',[]) and signs:
        result.update(status='new_signs',summary='Sono comparsi sintomi segnalati rispetto al precedente rilievo senza sintomi evidenti.')
    elif old_signs and 'no_symptoms' in latest.get('symptoms',[]):
        result.update(status='not_reported',summary='I sintomi precedenti non sono segnalati nell’ultimo rilievo. Questo non dimostra che la causa sia risolta.')
    elif signs and signs==old_signs:
        before,after=number(previous.get('affected_percent')),number(latest.get('affected_percent'))
        if before is not None and after is not None:
            delta=round(after-before,3)
            result.update(status='reported_increase' if delta>0 else 'reported_decrease' if delta<0 else 'reported_unchanged',
                          delta_percentage_points=delta,
                          summary=f'Piante interessate segnalate: {before:g}% → {after:g}% ({delta:+g} punti percentuali).')
        a,b=SEVERITY.get(previous.get('severity')),SEVERITY.get(latest.get('severity'))
        if a is not None and b is not None:
            result['severity_change']='increased' if b>a else 'decreased' if b<a else 'unchanged'
            if (before is not None and after is not None) and ((after>before and b<a) or (after<before and b>a)):
                result['limitations'].append('Percentuale e intensità cambiano in direzioni diverse: non riassumo il confronto come miglioramento o peggioramento.')
    return result


def enrich(review, records, crop=None, today=None):
    today=today or date.today()
    decision=review['decision_support']
    manual=review['manual_assessment']
    latest=(review.get('visual_context') or {}).get('latest') or {}
    detail_labels={
        'leaf_age':{'young':'foglie giovani','old':'foglie vecchie','all':'foglie giovani e vecchie'},
        'distribution':{'scattered':'piante isolate','patches':'a chiazze','uniform':'uniforme'},
        'root_condition':{'normal':'radici apparentemente regolari','damaged':'radici scure o danneggiate','dry':'radici secche'},
    }
    details=[labels[latest[key]] for key,labels in detail_labels.items() if latest.get(key) in labels]
    if latest.get('noticed_since'): details.append('sintomi dal '+latest['noticed_since'])
    for entry in decision['inputs']:
        if entry['id']=='observations' and details:entry['detail']+=' Dettagli: '+', '.join(details)+'.'
    signs=set(latest.get('symptoms',[]))-{'no_symptoms'}
    findings={f['rule_id']:f for d in manual['domains'].values() for f in d['findings']}
    params=manual.get('parameters') or {}
    stress=(findings.get('soil.water_stress') or {}).get('values',{})
    fc,wp,theta=(number(params.get(k)) for k in ('field_capacity_percent','wilting_point_percent','moisture_percent'))
    measured=day(params.get('observed_at'))
    aligned=(findings.get('soil.available_water',{}).get('status')=='available' and theta is not None and measured is not None
             and 0 <= (today-measured).days <= 7 and measured==day(latest.get('observed_at')))
    candidates=[];questions=[];quality=[]

    def question(key,text,reason,section=3,field='notes'):
        if not any(q['id']==key for q in questions):
            questions.append(dict(id=key,text=text,reason=reason,section=section,field=field))

    def candidate(key,title,support,against,missing,action,sources,strong=False):
        candidates.append(dict(id=key,title=title,status='consistent_inputs' if strong else 'less_supported' if against else 'to_verify',
                               supporting=support,contradicting=against,missing=missing,next_check=action,source_ids=sources))

    if 'wilting' in signs:
        support=['Appassimento dichiarato nel rilievo.'];against=[];missing=[]
        if aligned and theta<=wp:
            support.append(f'Misura dello stesso giorno: umidità {theta:g}% vol., appassimento indicato {wp:g}% vol.')
        elif aligned and theta>=fc:
            against.append(f'La misura del profilo ({theta:g}% vol.) è almeno pari alla capacità di campo ({fc:g}% vol.): non sostiene una scarsità d’acqua in quel profilo.')
        elif aligned and stress.get('ks') is not None:
            if stress['threshold_exceeded']:
                support.append(f'Nel modello alla stessa data Dr {stress["depletion_mm"]:g} mm supera RAW {stress["raw_mm"]:g} mm; Ks {stress["ks"]:g}, con p effettivo fornito dall’operatore.')
            else:
                against.append('Alla stessa data Dr non supera RAW: il modello non indica limitazione idrica della traspirazione; non esclude salinità o problemi radicali.')
        elif aligned:
            missing.append('L’umidità è tra punto di appassimento e capacità di campo: senza p effettivo verificato non classifico lo stress idrico.')
            question('verified_p','Disponi di una frazione p effettiva verificata per coltura e condizioni alla data della misura?',
                     'Permette il confronto tra esaurimento e RAW; non viene scelta automaticamente dal nome della coltura.',1,'depletion_fraction')
        else:
            missing.append('Manca un’umidità valida del profilo misurata nello stesso giorno del rilievo.')
            question('water_same_day','Puoi misurare l’umidità alla profondità radicale nello stesso giorno del rilievo?', 'Serve a distinguere scarsità d’acqua nel suolo da problemi di assorbimento.',1,'moisture_percent')
        candidate('dry_profile','Poca acqua nel profilo radicale misurato',support,against,missing,
                  'Verifica misura, unità, profondità e rappresentatività del profilo. Un problema di assorbimento può avere altre cause.', ['fao56_8','csu_diagnosis'],strong=bool(aligned and (theta<=wp or stress.get('threshold_exceeded'))))
        root=latest.get('root_condition','unknown')
        root_support=['L’appassimento richiede anche un controllo dell’assorbimento e delle radici.']
        if root in {'damaged','dry'}: root_support.append('L’operatore segnala radici ' + ('scure o danneggiate.' if root=='damaged' else 'secche.'))
        if aligned and theta>fc: root_support.append('Il profilo è misurato oltre la capacità di campo: controllare drenaggio e radici, senza dedurre ristagno dal solo numero.')
        candidate('root_uptake','Problema radicale o di assorbimento',root_support,[],
                  ['Stato e funzionalità delle radici da confermare; l’aspetto da solo non identifica un patogeno.'],
                  'Confronta radici di piante interessate e apparentemente sane e verifica drenaggio e danni.', ['csu_diagnosis'],strong=root in {'damaged','dry'})
        if root=='unknown':question('roots','Che aspetto hanno le radici delle piante interessate?','Una misura di acqua nel terreno non descrive da sola la capacità di assorbimento.',field='root_condition')
    if 'yellowing' in signs or 'uneven_growth' in signs:
        support=['Ingiallimento o sviluppo irregolare dichiarato.']
        age=latest.get('leaf_age','unknown')
        if age!='unknown':support.append('Foglie interessate: '+{'young':'giovani','old':'vecchie','all':'sia giovani sia vecchie'}.get(age,age)+'.')
        candidate('nutrition_physiology','Cause nutrizionali o fisiologiche da distinguere',support,[],
                  ['Mancano un’identificazione della causa, metodi analitici e tarature pertinenti; il pH da solo non dimostra una carenza.'],
                  'Confronta foglie, radici, distribuzione e analisi appropriate con un tecnico prima di scegliere un intervento.', ['csu_diagnosis'])
        if 'yellowing' in signs and latest.get('plant_part','leaves') in {'leaves','whole'} and age=='unknown':question('leaf_age','L’ingiallimento interessa foglie giovani, vecchie o entrambe?','Aggiunge un dettaglio utile al confronto delle possibili cause.',field='leaf_age')
    if signs & {'spots','insects'}:
        candidate('biotic','Organismi o danni da identificare',['Macchie o insetti dichiarati nel rilievo.'],[],
                  ['Organismo, lesione e relazione con il danno non sono identificati.'],
                  'Descrivi forma e posizione delle lesioni, evoluzione e organismi osservati; richiedi identificazione quando necessaria.', ['csu_diagnosis'])
    if signs:
        water_findings=[findings.get(k,{}) for k in ('soil.irrigation_salinity','soil.irrigation_infiltration')]
        if any(f.get('status') in {'attention','partial'} for f in water_findings):
            candidate('irrigation_water_context','Qualità dell’acqua irrigua da contestualizzare',
                      [f['evidence']+' '+f['interpretation'] for f in water_findings if f.get('status') in {'attention','partial'}],[],
                      ['Non è confermato se e quando questa fonte sia stata usata; mancano esposizione della coltura, salinità del suolo e verifica locale.'],
                      'Verifica fonte e date delle irrigazioni prima di collegare il referto ai sintomi. La tabella FAO è orientativa.', ['fao29_water'])
            question('water_source_used','Questa acqua è stata usata nella particella? In quali date?',
                     'Il referto dell’acqua, da solo, non dimostra esposizione delle piante o causa dei sintomi.')
        if latest.get('distribution','unknown')=='unknown':question('distribution','I sintomi sono isolati, a chiazze o uniformi?','Aiuta a confrontare zone e rilievi successivi.',field='distribution')
        if not latest.get('noticed_since'):question('onset','Da quando noti questi sintomi?','Serve per confrontare l’esordio con condizioni ambientali e attività nel campo.',field='noticed_since')
        if latest.get('affected_percent') is None:question('extent','Quale percentuale di piante è interessata?','Permette un confronto descrittivo con i rilievi successivi.',field='affected_percent')
        if not crop:question('crop','Quali sono coltura e fase attuale?','La valutazione dei sintomi richiede il contesto della pianta.',4,'crop')
    for r in records:
        if r is latest or r.get('id') and r.get('id')==latest.get('id'):continue
        if r.get('observed_at')==latest.get('observed_at') and context(r)==context(latest):
            other=set(r.get('symptoms',[]))
            if ('no_symptoms' in other and signs) or ('no_symptoms' in latest.get('symptoms',[]) and other-{'no_symptoms'}):
                quality.append('Rilievi dello stesso giorno e con lo stesso contesto non concordano sulla presenza di sintomi. Potrebbero riferirsi a zone diverse.')
                question('resolve_reports','I rilievi discordanti riguardano le stesse piante e la stessa zona?','Prima di interpretarli va chiarito il contesto delle osservazioni.')
                break
    if signs and latest.get('affected_percent')==0:
        quality.append('Sono dichiarati sintomi, ma la percentuale è zero: controlla la stima o lascia il dato non disponibile.')
    if not signs and 'no_symptoms' in latest.get('symptoms',[]) and (number(latest.get('affected_percent')) or 0)>0:
        quality.append('Il rilievo indica assenza di sintomi ma una percentuale positiva: chiarisci il significato della percentuale.')
    trend=compare_observations(records,latest or None,today)
    if quality:
        candidates=[dict(c,status='conflicting_inputs',missing=c['missing']+['Chiarire prima i rilievi non concordanti.']) for c in candidates]
    candidates.sort(key=lambda c:{'consistent_inputs':0,'to_verify':1,'less_supported':2,'conflicting_inputs':3}[c['status']])
    decision.update(differential=candidates, questions=questions, observation_trend=trend, quality_notes=quality,
                    evidence_note='Le piste sono ordinate per tipo di riscontro disponibile. Non sono probabilità, diagnosi o cause mutuamente esclusive.')
    if quality and decision['status']!='priority_check':
        decision.update(status='needs_verification',headline='Chiarisci i rilievi prima di interpretare le cause')
    return decision
