"""Reviewed BBCH definitions; no stage prediction or automatic crop coefficients.

BBCH Monograph, 2nd edition 2001, cereal and maize keys (PDF pp. 14-16,
24-25). Descriptions below are concise Italian paraphrases. Only explicitly
reviewed codes are interpreted; numeric proximity never supplies a definition.
"""
from datetime import date
import re
import unicodedata

SOURCE = 'bbch_2001'
LABELS = {'frumento_tenero':'Frumento tenero','frumento_duro':'Frumento duro',
          'frumento':'Frumento (tipo non distinto)', 'orzo':'Orzo','avena':'Avena','segale':'Segale','mais':'Mais'}
ALIASES = {'wheat':'frumento','grano tenero':'frumento_tenero',
           'grano duro':'frumento_duro','barley':'orzo','oats':'avena','rye':'segale','maize':'mais','corn':'mais'}


def crop_key(value):
    if not isinstance(value,str):return None
    text=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower().strip()
    text=re.sub(r'[_\s-]+',' ',text)
    key=ALIASES.get(text,text.replace(' ','_'))
    return key if key in LABELS else None


COMMON = {0:'Seme asciutto',1:'Inizio imbibizione del seme',3:'Imbibizione completata',
          5:'Radichetta emersa',6:'Radice allungata, comparsa di peli radicali o radici laterali',
          7:'Coleoptile emerso dal seme',9:'Emergenza: il coleoptile supera la superficie del suolo',
          10:'Prima foglia che emerge dal coleoptile',
          **{n:f'{n-10} foglie distese sul germoglio principale' for n in range(11,19)},
          19:'Almeno nove foglie distese',97:'Pianta morta e collassata',99:'Prodotto raccolto'}
COMMON[11]='Prima foglia distesa'
CEREALS = dict(COMMON)
CEREALS.update({20:'Nessun culmo di accestimento',21:'Primo culmo di accestimento riconoscibile',
                **{n:f'{n-20} culmi di accestimento riconoscibili' for n in range(22,29)},
                29:'Fine accestimento: numero massimo di culmi riconoscibile',
                30:'Inizio levata: pseudofusto eretto e infiorescenza almeno 1 cm sopra il nodo di accestimento',
                31:'Primo nodo almeno 1 cm sopra il nodo di accestimento',
                **{n:f'Nodo {n-30} almeno 2 cm sopra il nodo precedente' for n in range(32,37)},
                37:'Foglia a bandiera appena visibile, ancora arrotolata',
                39:'Foglia a bandiera distesa, ligula visibile',
                41:'Inizio botticella: allungamento della guaina della foglia a bandiera',
                43:'Botticella: primo rigonfiamento visibile della guaina',45:'Botticella: guaina rigonfia',
                47:'Apertura della guaina della foglia a bandiera',49:'Prime ariste visibili, nelle forme aristate',
                51:'Inizio spigatura: prima spighetta visibile fuori dalla guaina',
                **{n:f'{(n-50)*10}% dell’infiorescenza emersa' for n in range(52,59)},
                59:'Infiorescenza completamente emersa',61:'Inizio fioritura: prime antere visibili',
                65:'Piena fioritura: circa metà delle antere mature',69:'Fine fioritura delle spighette',
                71:'Maturazione acquosa: prime cariossidi a metà dimensione finale',
                73:'Inizio maturazione lattea',75:'Maturazione lattea: cariossidi a dimensione finale, ancora verdi',
                77:'Fine maturazione lattea',83:'Inizio maturazione pastosa',85:'Cariosside pastosa soffice',
                87:'Cariosside pastosa dura',89:'Cariosside pienamente matura e dura',
                92:'Sovramaturazione: cariosside molto dura',93:'Distacco delle cariossidi durante il giorno'})
MAIZE = dict(COMMON)
MAIZE.update({30:'Inizio allungamento del fusto',
              **{n:f'{n-30} nodi riconoscibili' for n in range(31,39)},39:'Almeno nove nodi riconoscibili',
              51:'Inizio comparsa del pennacchio alla sommità del fusto',53:'Punta del pennacchio visibile',
              55:'Pennacchio in emersione: la parte centrale inizia a separarsi',59:'Pennacchio completamente emerso e separato',
              61:'Stami visibili al centro del pennacchio; apice della spiga femminile in emersione',
              63:'Inizio emissione del polline; prime sete visibili',
              65:'Fioritura nelle parti alta e bassa del pennacchio; sete completamente emerse',
              67:'Fioritura maschile terminata; sete in disseccamento',69:'Fine fioritura: sete completamente secche',
              71:'Inizio sviluppo delle cariossidi: stadio a vescicola',73:'Inizio maturazione lattea',
              75:'Cariossidi centrali della spiga con contenuto lattiginoso',79:'Quasi tutte le cariossidi a dimensione finale',
              83:'Inizio maturazione pastosa',85:'Maturazione pastosa',
              87:'Maturità fisiologica: strato nero alla base della cariosside',89:'Cariossidi mature, dure e lucide'})
PRINCIPAL = {0:'Germinazione ed emergenza',1:'Sviluppo fogliare',2:'Accestimento',3:'Levata',4:'Botticella',
             5:'Spigatura',6:'Fioritura',7:'Sviluppo della granella',8:'Maturazione',9:'Senescenza e fine ciclo'}


def stage(crop,code):
    key=crop_key(crop)
    base={'crop_key':key,'crop_label':LABELS.get(key,str(crop or 'Coltura non registrata')),
          'code':code,'source_ids':[SOURCE] if key else []}
    if key is None:
        return dict(base,status='unsupported',description='Scala specifica non ancora verificata per questa coltura.')
    table=MAIZE if key=='mais' else CEREALS
    if not isinstance(code,int) or isinstance(code,bool) or code not in table:
        return dict(base,status='unmapped',description='Codice non presente nel catalogo verificato per questa coltura: confronta il manuale, senza sostituirlo automaticamente.')
    principal=code//10
    label='Comparsa del pennacchio' if key=='mais' and principal==5 else PRINCIPAL[principal]
    action=('Distingui pennacchio e sete e registra la loro comparsa nelle stesse piante.' if key=='mais' and principal in {5,6} else
            'Controlla ligula e foglia a bandiera sulle piante rappresentative.' if key!='mais' and code in {37,39} else
            'Osserva infiorescenza e antere su piante rappresentative e annota la disomogeneità del campo.' if principal in {5,6} else
            'Verifica il carattere morfologico su piante rappresentative e registra le zone con fasi diverse.')
    if code in {97,99}:action='Verifica se il ciclo è concluso; registra un nuovo ciclo se stai osservando una coltura successiva.'
    return dict(base,status='recognized',principal_stage=principal,phase=label,description=table[code],next_check=action)


def parse_day(value):
    try:return date.fromisoformat(value)
    except (ValueError,TypeError):return None


def assess(crop,today=None):
    today=today or date.today();crop=crop or {};bbch=crop.get('latest_bbch') or {}
    result=stage(crop.get('crop'),bbch.get('bbch'))
    result.update(observed_at=bbch.get('observed_at'),sowing_date=crop.get('sowing_date'),quality_notes=[],
                  limitations=['Descrizione del rilievo, non previsione della fase attuale né diagnosi.',
                               'Le macrofasi possono sovrapporsi: i codici non misurano una velocità di crescita e non vanno sottratti.',
                               'Soglia di aggiornamento di 21 giorni applicativa; nessun Kc, dose o trattamento dedotto dal BBCH.'])
    observed,sown=parse_day(bbch.get('observed_at')),parse_day(crop.get('sowing_date'))
    if not bbch:
        result.update(status='missing',description='Registra una fase osservata per contestualizzare la coltura.')
    elif observed is None or observed>today:
        result['status']='invalid_date';result['quality_notes'].append('Data BBCH non valida o futura: non interpreto la fase come attuale.')
    elif sown is not None and observed<sown and bbch.get('bbch')!=0:
        result['status']='date_conflict';result['quality_notes'].append('Il rilievo della pianta precede la semina registrata: chiarisci ciclo e date.')
    elif result['status']=='recognized':
        result['status']='available' if (today-observed).days<=21 else 'stale'
    if crop.get('sowing_date') and sown is None:
        result['status']='date_conflict';result['quality_notes'].append('Data di semina non interpretabile: chiarisci il record prima di collegarlo alla fase.')
    if sown is not None and sown>today:
        result['status']='date_conflict';result['quality_notes'].append('La semina è futura: il ciclo non descrive ancora una coltura osservata in campo.')
    result['usable_for_current_analysis']=result['status']=='available' and bbch.get('bbch') not in {0,97,99}
    return result
