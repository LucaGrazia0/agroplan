"""Parcel-scoped, optional measured inputs for manual-based water calculations."""
from datetime import date
import json
from fastapi import APIRouter
from pydantic import BaseModel, Field, ConfigDict, model_validator
from auth import CurrentUser, require_parcel
from storage import connect

router = APIRouter(prefix='/agronomy/parameters', tags=['Parametri agronomici'])


class WaterParameters(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    observed_at: date
    field_capacity_percent: float | None = Field(None, ge=0, le=100)
    wilting_point_percent: float | None = Field(None, ge=0, le=100)
    root_depth_m: float | None = Field(None, gt=0, le=5)
    moisture_percent: float | None = Field(None, ge=0, le=100)
    kc: float | None = Field(None, gt=0, le=2.5)
    kc_from: date | None = None
    kc_to: date | None = None

    @model_validator(mode='after')
    def coherent(self):
        if self.observed_at > date.today():
            raise ValueError('La misura non può avere una data futura.')
        if self.field_capacity_percent is not None and self.wilting_point_percent is not None:
            if self.wilting_point_percent >= self.field_capacity_percent:
                raise ValueError('Il punto di appassimento deve essere inferiore alla capacità di campo.')
        if self.kc is not None:
            if not self.kc_from or not self.kc_to or self.kc_from > self.kc_to or self.kc_to > date.today():
                raise ValueError('Indica un intervallo Kc valido, terminato entro oggi.')
        elif self.kc_from or self.kc_to:
            raise ValueError('Le date del coefficiente richiedono un Kc.')
        return self


def parameters(parcel_id):
    with connect() as db:
        row = db.execute('SELECT payload FROM agr_analysis_parameters WHERE parcel_id=?', (parcel_id,)).fetchone()
    return json.loads(row['payload']) if row else {}


@router.get('/{parcel_id}')
def get_parameters(parcel_id: str, user: CurrentUser):
    require_parcel(parcel_id, user)
    return parameters(parcel_id)


@router.put('/{parcel_id}')
def put_parameters(parcel_id: str, item: WaterParameters, user: CurrentUser):
    require_parcel(parcel_id, user)
    payload = item.model_dump(mode='json')
    with connect() as db:
        db.execute('INSERT INTO agr_analysis_parameters(parcel_id,payload) VALUES(?,?) '
                   'ON CONFLICT(parcel_id) DO UPDATE SET payload=excluded.payload',
                   (parcel_id, json.dumps(payload, sort_keys=True, allow_nan=False)))
    return payload
