"""Private visual field observations and immutable analysis results."""
from datetime import date, datetime, timezone
import json
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict, model_validator
from auth import CurrentUser, require_parcel
from storage import connect
from diagnostic_schema import DiagnosticDetails

router = APIRouter(tags=['Rilievi e risultati'])
SYMPTOMS = {'yellowing','wilting','spots','insects','uneven_growth','no_symptoms'}
DETAIL_DEFAULTS = {'leaf_age':'unknown','distribution':'unknown','root_condition':'unknown','noticed_since':None,'diagnostic_details':None}

class Observation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    parcel_id: str = Field(min_length=1,max_length=128)
    observed_at: date
    symptoms: list[Literal['yellowing','wilting','spots','insects','uneven_growth','no_symptoms']] = Field(default_factory=list,max_length=6)
    severity: Literal['mild','moderate','high'] = 'mild'
    affected_percent: float | None = Field(default=None,ge=0,le=100)
    plant_part: Literal['leaves','stem','roots','whole'] = 'leaves'
    notes: str = Field(default='',max_length=3000)
    leaf_age: Literal['unknown','young','old','all'] = 'unknown'
    distribution: Literal['unknown','scattered','patches','uniform'] = 'unknown'
    root_condition: Literal['unknown','normal','damaged','dry'] = 'unknown'
    noticed_since: date | None = None
    diagnostic_details: DiagnosticDetails | None = None

    @model_validator(mode='after')
    def valid_report(self):
        if self.observed_at > date.today(): raise ValueError('La data non può essere futura.')
        if self.noticed_since and self.noticed_since > self.observed_at: raise ValueError('L’inizio dei sintomi non può essere successivo al rilievo.')
        if self.diagnostic_details and self.diagnostic_details.event_date:
            if self.diagnostic_details.event_date > self.observed_at:
                raise ValueError('L’evento deve precedere o coincidere con il rilievo.')
            if self.diagnostic_details.recent_event in {'unknown','none'}:
                raise ValueError('La data dell’evento richiede un evento dichiarato.')
        if not self.symptoms and not self.notes.strip(): raise ValueError('Indica cosa hai osservato.')
        if 'no_symptoms' in self.symptoms and len(set(self.symptoms))>1: raise ValueError('Assenza di sintomi incompatibile con altri sintomi.')
        self.symptoms=sorted(set(self.symptoms))
        self.notes=self.notes.strip()
        return self


def observations(parcel_id, limit=30):
    with connect() as db:
        rows=db.execute('SELECT * FROM agr_field_observations WHERE parcel_id=? ORDER BY observed_at DESC,created_at DESC LIMIT ?', (parcel_id,limit)).fetchall()
    return [dict(json.loads(r['payload']),id=r['id'],created_at=r['created_at']) for r in rows]

@router.get('/observations')
def list_observations(user:CurrentUser,parcel_id:str,limit:int=Query(30,ge=1,le=100)):
    require_parcel(parcel_id,user)
    return observations(parcel_id,limit)

@router.put('/observations/{observation_id}')
def save_observation(observation_id:UUID,item:Observation,user:CurrentUser):
    require_parcel(item.parcel_id,user)
    key=str(observation_id)
    payload=json.dumps(item.model_dump(mode='json'),sort_keys=True)
    now=datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute('INSERT INTO agr_field_observations(id,parcel_id,observed_at,created_at,payload) VALUES(?,?,?,?,?) ON CONFLICT(id) DO NOTHING', (key,item.parcel_id,item.observed_at.isoformat(),now,payload))
        row=db.execute('SELECT * FROM agr_field_observations WHERE id=?',(key,)).fetchone()
        # New optional details must not break retries of observations saved by
        # older clients. Do not rewrite those immutable historical payloads.
        previous = dict(DETAIL_DEFAULTS, **json.loads(row['payload']))
        if row['parcel_id']!=item.parcel_id or previous!=json.loads(payload): raise HTTPException(409,'Questo rilievo è già stato salvato con dati diversi.')
    return dict(json.loads(row['payload']),id=key,created_at=row['created_at'])

@router.get('/agronomy/results')
def list_results(user:CurrentUser,parcel_id:str,limit:int=Query(20,ge=1,le=100)):
    require_parcel(parcel_id,user)
    with connect() as db:
        rows=db.execute('SELECT id,created_at,payload FROM agr_analysis_results WHERE parcel_id=? ORDER BY created_at DESC LIMIT ?', (parcel_id,limit)).fetchall()
    return [dict(json.loads(r['payload']),result_id=r['id'],saved_at=r['created_at']) for r in rows]


def save_result(parcel_id,result):
    import hashlib
    # A given input state creates one history item, even after retries.
    canonical=json.loads(json.dumps(result))
    canonical.get('crop_review',{}).pop('generated_at',None)
    canonical.pop('result_id',None)
    payload=json.dumps(canonical,sort_keys=True,ensure_ascii=False,allow_nan=False)
    key=hashlib.sha256(payload.encode()).hexdigest()
    with connect() as db:
        db.execute('INSERT INTO agr_analysis_results(id,parcel_id,created_at,payload) VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING', (key,parcel_id,datetime.now(timezone.utc).isoformat(),payload))
    return key
