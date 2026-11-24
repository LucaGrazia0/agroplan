"""FAO calculations from explicit inputs, without guessing crop coefficients.

FAO 56: equations 82-84, 86-87. FAO 29 Rev.1: table 1.
Numbers used for comparisons are unrounded. Rounded values are display only.
"""
from manual_engine import day, finding, number


def measured_water(params, today):
    fc, wp, depth, theta, p = (number(params.get(k)) for k in (
        'field_capacity_percent', 'wilting_point_percent', 'root_depth_m',
        'moisture_percent', 'depletion_fraction'))
    measured = day(params.get('observed_at'))
    valid = measured is not None and measured <= today and fc is not None and wp is not None and depth is not None and 0 <= wp < fc <= 100 and 0 < depth <= 5
    if not valid or p is None or not 0 < p < 1:
        return finding('soil.water_stress', 'Acqua facilmente utilizzabile e coefficiente Ks', 'missing',
                       'Servono profilo misurato e frazione p effettiva, verificata per coltura e domanda evaporativa alla data della misura.',
                       'RAW e Ks non calcolati; nessun p predefinito viene scelto dalla coltura o dal BBCH.',
                       'Se disponi di un p verificato, aggiungilo ai parametri idrici; per Ks serve anche l’umidità media del profilo.', ['fao56_8'])
    taw = 10 * (fc - wp) * depth
    raw = p * taw
    values = {'taw_mm': round(taw, 2), 'raw_mm': round(raw, 2), 'p': p, 'observed_at': str(measured)}
    limits = ['p effettivo fornito dall’operatore: non viene corretto automaticamente per ETc, tessitura o fase.',
              'Profilo uniforme e non salino; salinità, falda, anossia e danni radicali non sono rappresentati.',
              'Fotografia alla data della misura: nessun bilancio giornaliero, previsione o dose irrigua.',
              'Ks descrive la limitazione modellata della traspirazione, non l’evaporazione del suolo né una diagnosi.']
    evidence = f'Profilo del {measured}; p effettivo {p:g}; TAW {taw:g} mm; RAW {raw:g} mm.'
    status = 'available'
    interpretation = f'RAW: {raw:g} mm. Per confrontarla con l’esaurimento serve l’umidità media della zona radicale.'
    if theta is not None and 0 <= theta <= 100:
        depletion = min(taw, max(0, 10 * (fc - theta) * depth))
        limited = depletion > raw
        ks = (taw - depletion) / (taw - raw) if limited else 1.0
        values.update(depletion_mm=round(depletion, 2), ks=round(ks, 4), threshold_exceeded=limited)
        evidence += f' Umidità {theta:g}% vol.; esaurimento Dr {depletion:g} mm.'
        interpretation = (f'Dr supera RAW: Ks {ks:.3f}, compatibile con limitazione idrica della traspirazione nel modello alla data della misura.' if limited else
                          'Dr non supera RAW: Ks 1 nel modello. Questo non esclude salinità, problemi radicali o altre cause dei sintomi.')
        if theta < wp or theta > fc:
            limits.append('Umidità fuori dall’intervallo appassimento–capacità di campo: Dr è limitato tra 0 e TAW. Verificare misura e rappresentatività.')
        # Attention means check the modeled limitation, not an irrigation order.
        status = 'attention' if limited else 'available'
    return finding('soil.water_stress', 'Acqua facilmente utilizzabile e coefficiente Ks', status, evidence,
                   interpretation, 'Verifica misure, p effettivo e radici; confronta il rilievo dello stesso giorno. Aggiorna le misure prima di decidere interventi.',
                   ['fao56_8'], values=values,
                   equation='RAW = p × TAW; Dr = 1000 × (θFC − θ) × Zr, limitato tra 0 e TAW; Ks = 1 se Dr ≤ RAW, altrimenti (TAW − Dr)/(TAW − RAW)', limitations=limits)


def irrigation_quality(params, today):
    ec, sar = number(params.get('water_ec_ds_m')), number(params.get('water_sar'))
    sampled = day(params.get('water_sample_date'))
    if params.get('water_ec_ds_m') is None and params.get('water_sar') is None:
        return []  # Optional assessment: do not add irrelevant missing-data noise.
    limits = ['ECw dell’acqua a 25 °C in dS/m, non ECe del suolo e non EC di estratti 1:5.',
              'Linee guida FAO orientative, soprattutto per climi aridi/semiaridi e suoli drenati; verificare piogge, falda, coltura e tecnica irrigua locale.',
              'Nessuna idoneità complessiva o potabilità: ioni specifici, tossicità, microbiologia e lisciviazione non sono valutati.',
              'Il campione descrive la data indicata; la qualità della fonte può variare.']
    if sampled is None or sampled > today or ec is None or ec < 0 or sar is not None and sar < 0:
        return [finding('soil.irrigation_quality', 'Qualità dell’acqua irrigua', 'missing',
                        'Mancano ECw valida e data non futura dello stesso campione.', 'Confronto non eseguito.',
                        'Inserisci ECw a 25 °C e data del campione; aggiungi SAR del medesimo referto.', ['fao29_water'], limitations=limits)]
    salinity = 'none' if ec < .7 else 'slight_moderate' if ec <= 3 else 'severe'
    labels = {'none':'nessuna restrizione indicata', 'slight_moderate':'restrizione da lieve a moderata', 'severe':'restrizione severa'}
    rows = [finding('soil.irrigation_salinity', 'Salinità dell’acqua irrigua', 'available' if salinity == 'none' else 'attention',
                    f'Campione del {sampled}; ECw {ec:g} dS/m a 25 °C.',
                    f'Tabella FAO 29, solo salinità: {labels[salinity]}. Non descrive la salinità del suolo o la risposta effettiva della coltura.',
                    'Confronta la qualità della fonte con coltura, drenaggio e analisi del suolo; verifica anche ECw e SAR insieme.',
                    ['fao29_water'], values={'ecw_ds_m':ec, 'restriction':salinity, 'sample_date':str(sampled)}, limitations=limits)]
    if sar is None or not 0 <= sar <= 40:
        rows.append(finding('soil.irrigation_infiltration', 'Acqua e infiltrazione nel suolo', 'missing' if sar is None else 'partial',
                            f'ECw {ec:g} dS/m; SAR non disponibile o fuori dal campo 0–40 della tabella.',
                            'La sola ECw non basta a classificare il possibile problema di infiltrazione; non estrapolo la tabella.',
                            'Aggiungi il SAR dello stesso campione o richiedi una valutazione specifica se fuori tabella.', ['fao29_water'], limitations=limits))
        return rows
    # Adjacent printed SAR bands share endpoints. Keep both interpretations
    # where their outcomes differ, rather than inventing an exact cutoff.
    bands = [(0,3,.2,.7),(3,6,.3,1.2),(6,12,.5,1.9),(12,20,1.3,2.9),(20,40,2.9,5)]
    possibilities = list(dict.fromkeys('severe' if ec < low else 'none' if ec > high else 'slight_moderate'
                                      for a,b,low,high in bands if a <= sar <= b))
    uncertain = len(possibilities) > 1
    rows.append(finding('soil.irrigation_infiltration', 'Acqua e infiltrazione nel suolo',
                        'partial' if uncertain else 'available' if possibilities == ['none'] else 'attention',
                        f'Campione del {sampled}; ECw {ec:g} dS/m a 25 °C e SAR {sar:g} nello stesso referto.',
                        ('SAR al confine tra fasce: le letture della tabella differiscono. ' if uncertain else 'Confronto ECw–SAR secondo FAO 29: ') +
                        '; '.join(labels[k] for k in possibilities) + '. Non misura la velocità di infiltrazione in campo.',
                        'Verifica il referto e osserva infiltrazione, struttura e drenaggio con un tecnico; non aggiungere sali o correttivi da questo solo confronto.',
                        ['fao29_water'], values={'ecw_ds_m':ec,'sar':sar,'possible_restrictions':possibilities,'sample_date':str(sampled)}, limitations=limits))
    return rows
