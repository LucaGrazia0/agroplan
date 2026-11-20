"""Analisi chimico-fisiche del suolo per particella."""
from datetime import date
from fastapi import APIRouter, HTTPException
from soil_sources import search_soil
from pydantic import BaseModel, Field, ConfigDict, model_validator
from storage import connect
from auth import CurrentUser, require_parcel

router = APIRouter(prefix="/soil", tags=["Soil"])

class SoilAnalysis(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    parcel_id: str = Field(min_length=1)
    sample_date: date
    source: str = "laboratory"
    ph: float | None = Field(default=None, ge=0, le=14)
    nitrogen_g_kg: float | None = Field(default=None, ge=0)
    sand_percent: float | None = Field(default=None, ge=0, le=100)
    silt_percent: float | None = Field(default=None, ge=0, le=100)
    clay_percent: float | None = Field(default=None, ge=0, le=100)
    phosphorus_mg_kg: float | None = Field(default=None, ge=0)
    potassium_mg_kg: float | None = Field(default=None, ge=0)
    notes: str = ""
    client_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode='after')
    def not_future(self):
        if self.sample_date > date.today():
            raise ValueError('La data del campione non può essere futura.')
        return self

@router.post("/analyses", status_code=201)
def add_analysis(item: SoilAnalysis, user: CurrentUser):
    require_parcel(item.parcel_id, user)
    values=item.model_dump(mode="json")
    with connect() as db:
        columns=list(values)
        cursor=db.execute(f"INSERT INTO agr_soil_analyses ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) ON CONFLICT(parcel_id,client_id) DO NOTHING", list(values.values()))
        if item.client_id is not None:
            row = db.execute('SELECT * FROM agr_soil_analyses WHERE parcel_id=? AND client_id=?',
                             (item.parcel_id,item.client_id)).fetchone()
            if any(row[key] != value for key,value in values.items()):
                raise HTTPException(409, 'Identificativo analisi già utilizzato con dati diversi.')
        else:
            row = db.execute('SELECT * FROM agr_soil_analyses WHERE id=?', (cursor.lastrowid,)).fetchone()
        return dict(row)


@router.get("/analyses")
def list_analyses(parcel_id: str, user: CurrentUser):
    require_parcel(parcel_id, user)
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM agr_soil_analyses WHERE parcel_id=? ORDER BY sample_date DESC,id DESC", (parcel_id,))]


class SoilSearchRequest(BaseModel):
    parcel_id: str = Field(min_length=1)
    points: list[dict[str, float]] = Field(min_length=3, max_length=2000)

@router.post("/automatic-analysis")
async def automatic_analysis(item: SoilSearchRequest, user: CurrentUser):
    require_parcel(item.parcel_id, user)
    try:
        return await search_soil(item.points)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
