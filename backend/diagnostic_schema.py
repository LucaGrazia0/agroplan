"""Operator-confirmed observations for a transparent differential investigation."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

SIGN_LABELS = {
    'yellow_pustule_rows': 'Pustole gialle disposte in strisce',
    'brown_pustules': 'Piccole pustole brune sparse',
    'white_powder': 'Patina o ciuffi bianchi superficiali',
    'black_dots_in_lesions': 'Puntini neri dentro lesioni brune',
    'interveinal_yellowing': 'Ingiallimento tra le nervature',
    'tip_margin_yellowing': 'Ingiallimento da punta e margini',
    'chewing_or_holes': 'Erosioni, fori o parti mangiate',
    'mosaic': 'Mosaico o striature di colore',
    'bleached_ear': 'Spighe o spighette sbiancate',
}
CHOICES = {
    'field_pattern': {'unknown': 'Non so', 'random': 'Piante sparse', 'low_spots': 'Avvallamenti',
                      'traffic_lines': 'Tracce di passaggio', 'spray_width': 'Fasce o larghezza dei trattamenti',
                      'field_edge': 'Bordo del campo', 'everywhere': 'Tutto il campo'},
    'progression': {'unknown': 'Non so', 'sudden': 'Comparsa improvvisa', 'spreading': 'Si sta estendendo',
                    'stable': 'Sembra stabile'},
    'recent_event': {'unknown': 'Non so', 'none': 'Nessun evento noto', 'spray': 'Trattamento o diserbo',
                     'fertilizer': 'Concimazione', 'frost': 'Gelo', 'hail': 'Grandine',
                     'traffic': 'Passaggio di mezzi', 'irrigation': 'Irrigazione'},
}


class DiagnosticDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    signs: list[Literal['yellow_pustule_rows','brown_pustules','white_powder','black_dots_in_lesions',
                       'interveinal_yellowing','tip_margin_yellowing','chewing_or_holes','mosaic','bleached_ear']] = Field(default_factory=list,max_length=9)
    field_pattern: Literal['unknown','random','low_spots','traffic_lines','spray_width','field_edge','everywhere'] = 'unknown'
    progression: Literal['unknown','sudden','spreading','stable'] = 'unknown'
    recent_event: Literal['unknown','none','spray','fertilizer','frost','hail','traffic','irrigation'] = 'unknown'
    event_date: date | None = None


def schema():
    return {'signs': SIGN_LABELS, 'choices': CHOICES,
            'method': 'Le risposte sono osservazioni dell’operatore, non diagnosi né soglie statistiche.'}
