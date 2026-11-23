"""Versioned, reviewed references and the exact scope of implemented methods.

The application ships these methods; it does not silently scrape or execute
instructions from manuals at runtime. Changes require a version and tests.
"""
VERSION = '2026.11.23.1'
SOURCES = {
    'fao56_6': {
        'title': 'FAO Irrigation and Drainage Paper 56 (1998), capitolo 6',
        'url': 'https://www.fao.org/4/x0490e/x0490e0b.htm',
        'section': 'Equazione 58 e tabella 12: ETc = Kc × ET₀',
        'scope': 'Evapotraspirazione in condizioni standard; Kc da verificare per coltura, periodo e condizioni locali.',
    },
    'fao56_8': {
        'title': 'FAO Irrigation and Drainage Paper 56 (1998), capitolo 8',
        'url': 'https://www.fao.org/4/x0490e/x0490e0e.htm',
        'section': 'Equazione 82: acqua disponibile nella zona radicale',
        'scope': 'TAW da capacità di campo, punto di appassimento e profondità radicale; non determina una dose irrigua.',
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
