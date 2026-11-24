"""Versioned, reviewed references and the exact scope of implemented methods.

The application ships these methods; it does not silently scrape or execute
instructions from manuals at runtime. Changes require a version and tests.
"""
VERSION = '2026.11.24.3'
SOURCES = {
    'bbch_2001': {
        'title': 'U. Meier (ed.), BBCH Monograph, 2a edizione (2001), copia MASAF',
        'url': 'https://www.masaf.gov.it/flex/AppData/WebLive/Agrometeo/MIEPFY800_ORI/BBCHengl2001.pdf',
        'section': 'Chiavi specifiche Cereals e Maize, pagine PDF 14–16 e 24–25; principi generali pagine 6–8',
        'scope': 'Descrizione di codici osservati per frumento, orzo, avena, segale e mais; nessuna previsione o indicazione di trattamento.',
        'reviewed_on': '2026-11-24',
    },
    'fao56_6': {
        'title': 'FAO Irrigation and Drainage Paper 56 (1998), capitolo 6',
        'url': 'https://www.fao.org/4/x0490e/x0490e0b.htm',
        'section': 'Equazione 58 e tabella 12: ETc = Kc × ET₀',
        'scope': 'Evapotraspirazione in condizioni standard; Kc da verificare per coltura, periodo e condizioni locali.',
    },
    'fao56_8': {
        'title': 'FAO Irrigation and Drainage Paper 56 (1998), capitolo 8',
        'url': 'https://www.fao.org/4/x0490e/x0490e0e.htm',
        'section': 'Equazioni 82–84, 86–87: TAW, RAW, Ks ed esaurimento dalla misura del profilo',
        'scope': 'Fotografia del profilo misurato, con p effettivo verificato dall’operatore; nessuna previsione o dose irrigua.',
        'reviewed_on': '2026-11-24',
    },
    'fao29_water': {
        'title': 'FAO Irrigation and Drainage Paper 29 Rev. 1 (1985), Water quality for agriculture',
        'url': 'https://www.fao.org/4/t0234e/t0234e01.htm',
        'section': 'Tabella 1 e relative assunzioni: ECw, SAR, salinità e infiltrazione',
        'scope': 'Confronto orientativo dell’acqua irrigua, non del suolo. Linee guida per condizioni prevalentemente aride/semiaride, da verificare localmente.',
        'reviewed_on': '2026-11-24',
    },
    'usda_ph': {
        'title': 'USDA NRCS, Soil Survey Manual (2017), capitolo 3',
        'url': 'https://www.nrcs.usda.gov/sites/default/files/2022-09/SSM-ch3.pdf',
        'section': 'Tabella 3-15, pagina stampata 199: classi di reazione del suolo',
        'scope': 'Classificazione descrittiva del pH; metodo analitico da confrontare. Non misura la fertilità.',
    },
    'csu_diagnosis': {
        'title': 'Colorado State University Extension, Diagnosing Plant Disorders',
        'url': 'https://extension.colostate.edu/resource/diagnosing-plant-disorders/',
        'section': 'Raccolta delle informazioni e confronto delle cause biotiche e abiotiche',
        'scope': 'Metodo di indagine generale, non modello fitopatologico specifico per cereali.',
    },
}


def references(ids):
    return [dict(id=key, **SOURCES[key]) for key in dict.fromkeys(ids)]
