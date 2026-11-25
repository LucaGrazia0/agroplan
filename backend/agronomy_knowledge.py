"""Versioned, reviewed references and the exact scope of implemented methods.

The application ships these methods; it does not silently scrape or execute
instructions from manuals at runtime. Changes require a version and tests.
"""
VERSION = '2026.11.25.1'
SOURCES = {
    'aps_diagnosis': {
        'title': 'American Phytopathological Society, Plant Disease Diagnosis',
        'url': 'https://www.apsnet.org/edcenter/Pages/PlantDiseaseDiagnosis.aspx',
        'section': 'Symptoms, signs, chronology and differential diagnosis',
        'scope': 'Metodo di indagine e distinzione tra sintomo e segno; nessuna diagnosi automatica.',
        'reviewed_on': '2026-11-25',
    },
    'unl_distribution': {
        'title': 'Broderick & Jackson-Ziems, University of Nebraska, Using Symptom Distribution (2019)',
        'url': 'https://cropwatch.unl.edu/2019/using-symptom-distribution/',
        'section': 'Distribuzione spaziale, condizioni del campo e attività colturali',
        'scope': 'Piste per il sopralluogo; i pattern hanno eccezioni e non sono test diagnostici.',
        'reviewed_on': '2026-11-25',
    },
    'ahdb_yellow_rust': {
        'title': 'AHDB, Yellow rust symptoms and management in wheat',
        'url': 'https://ahdb.org.uk/knowledge-library/yellow-rust-in-wheat',
        'section': 'Sintomi e disposizione delle pustole',
        'scope': 'Descrittori del frumento, senza soglie o prescrizioni fitosanitarie.',
        'reviewed_on': '2026-11-25',
    },
    'ahdb_septoria': {
        'title': 'AHDB, Septoria tritici in winter wheat',
        'url': 'https://ahdb.org.uk/knowledge-library/septoria-tritici-in-winter-wheat',
        'section': 'Lesioni, picnidi e latenza dei sintomi',
        'scope': 'Segni da confrontare; il contesto meteo di 14 giorni non ricostruisce l’infezione.',
        'reviewed_on': '2026-11-25',
    },
    'uc_small_grain_mildew': {
        'title': 'University of California IPM, Powdery Mildew / Small Grains',
        'url': 'https://ipm.ucanr.edu/agriculture/small-grains/powdery-mildew/',
        'section': 'Symptoms and signs',
        'scope': 'Confronto dei segni superficiali, senza indicazioni di trattamento.',
        'reviewed_on': '2026-11-25',
    },
    'uc_bydv': {
        'title': 'University of California IPM, Barley Yellow Dwarf / Small Grains',
        'url': 'https://ipm.ucanr.edu/agriculture/small-grains/barley-yellow-dwarf/',
        'section': 'Sintomi, ospiti e vettori',
        'scope': 'Virosi come pista da confermare; afidi e colore non confermano infezione.',
        'reviewed_on': '2026-11-25',
    },
    'jic_wheat_photos': {
        'title': 'Long, Hartley, Morris & Brown (2023), Wheat disease images (small dataset)',
        'url': 'https://doi.org/10.5281/zenodo.7573133',
        'section': '999 immagini etichettate: brown rust, yellow rust, septoria, mildew e healthy',
        'scope': 'Riferimenti per ricerca sul frumento, CC BY 4.0; nessuna accuratezza del motore AgroPlan è implicata.',
        'reviewed_on': '2026-11-25',
    },
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
