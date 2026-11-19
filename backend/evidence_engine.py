"""Transparent synthesis of measured data and reported plant observations."""
from datetime import date
import re

LABELS={'yellowing':'Ingiallimento','wilting':'Appassimento','spots':'Macchie sulle piante','insects':'Insetti osservati','uneven_growth':'Crescita irregolare','no_symptoms':'Nessun sintomo evidente'}
TERMS={'yellowing':r'ingiall|foglie gialle','wilting':r'appass|avvizz','spots':r'macchi','insects':r'insett|afidi|larve','uneven_growth':r'crescita irregolare|sviluppo irregolare'}


def integrate(review,records,today=None):
    today=today or date.today()
    recent=[r for r in records if 0 <= (today-date.fromisoformat(r['observed_at'])).days <= 14]
    evidence=[]; hypotheses=[]; questions=[]
    latest=recent[0] if recent else None
    if latest:
        explicit=set(latest['symptoms'])
        clauses=re.split(r'[.;\n]',latest.get('notes',''))
        inferred={key for key,pattern in TERMS.items() if any(re.search(pattern,clause,re.I) and not re.search(r'\b(no|non|senza|nessun[oa]?|assenza)\b',clause,re.I) for clause in clauses)}
        if 'no_symptoms' in explicit and inferred:
            questions.append('La nota descrive possibili sintomi ma il rilievo indica assenza di sintomi: verifica il testo prima di interpretarlo.')
            inferred=set()
        signs=(explicit|inferred)-{'no_symptoms'}
        for key in sorted(signs):
            evidence.append({'label':LABELS[key],'source':'Rilievo visivo' if key in explicit else 'Parola nella nota da confermare','date':latest['observed_at']})
        if not signs and 'no_symptoms' in explicit:
            evidence.append({'label':LABELS['no_symptoms'],'source':'Rilievo visivo','date':latest['observed_at']})
        if signs:
            parts={'leaves':'foglie','stem':'fusto','roots':'radici','whole':'pianta intera'}
            evidence.append({'label':f"Parte osservata: {parts.get(latest.get('plant_part'),'non indicata')}; piante interessate: {latest.get('affected_percent') if latest.get('affected_percent') is not None else 'non indicato'}%.",'source':'Rilievo visivo','date':latest['observed_at']})
            if latest['severity']=='high' or (latest.get('affected_percent') is not None and latest['affected_percent']>=30):
                review['checks'].insert(0,{'title':'Sopralluogo prioritario','evidence':'Segnalati sintomi intensi o diffusi nel rilievo visivo.','action':'Verifica estensione, andamento e condizioni delle piante con un tecnico; non attendere soltanto il prossimo dato satellitare.'})
            if 'yellowing' in signs:
                hypotheses.append({'hypothesis':'L’ingiallimento può avere cause nutrizionali, idriche o fisiologiche.','evidence':'Sintomo riportato nel rilievo.','next_check':'Descrivi se interessa foglie giovani o vecchie; confronta radici, umidità e analisi disponibili.'})
            if 'wilting' in signs:
                balance=review.get('climatic_balance_7d')
                hypotheses.append({'hypothesis':'L’appassimento richiede un controllo dell’apparato radicale e della disponibilità idrica.','evidence':f'Rilievo visivo; bilancio P − ET₀: {balance} mm.' if balance is not None else 'Rilievo visivo; bilancio climatico non disponibile.','next_check':'Controlla umidità a profondità radicale e irrigazioni: il sintomo non prova da solo una carenza d’acqua.'})
            if signs & {'spots','insects'}:
                hypotheses.append({'hypothesis':'Macchie o insetti richiedono identificazione in campo.','evidence':'Segnalazione dell’operatore, non identificazione automatica.','next_check':'Descrivi forma, posizione, evoluzione e presenza di organismi; consulta il tecnico o il bollettino locale.'})
            if review['satellite']['delta'] is not None:
                evidence.append({'label':f"Variazione NDVI {review['satellite']['delta']:+.3f}",'source':'Satellite: confronto distinto dal rilievo visivo','date':review['satellite']['latest']['observed_at']})
            if not latest.get('affected_percent') and latest.get('affected_percent')!=0: questions.append('Quale percentuale di piante presenta i sintomi?')
        elif latest.get('notes') and not explicit:
            questions.append('La nota è conservata, ma non identifica un sintomo riconoscibile: seleziona un sintomo o precisa il rilievo.')
    else:
        questions.append('Aggiungi un rilievo visivo degli ultimi 14 giorni per confrontarlo con gli altri dati.')
    review['coverage']['visual_observations']=latest is not None
    review['visual_context']={'latest':latest,'record_count':len(records),'recent_count':len(recent)}
    review['integrated_assessment']={'evidence':evidence,'hypotheses':hypotheses,'questions':questions,'method':'Regole esplicite: record strutturati e termini nelle note, confrontati con dati colturali, meteo, suolo e satellite. Le parole riconosciute vanno confermate; nessuna diagnosi automatica o dose di trattamento.'}
    review['summary']=f"{sum(review['coverage'].values())} fonti disponibili su {len(review['coverage'])}. "+('Confronta le evidenze e completa le verifiche suggerite.' if latest else 'Manca un rilievo visivo recente delle piante.')
    return review
