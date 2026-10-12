"""Analisi chimico-fisiche del suolo per particella."""
from datetime import date
from fastapi import APIRouter, HTTPException
from soil_sources import search_soil
from pydantic import BaseModel, Field
from crop_api import connect

router = APIRouter(prefix="/soil", tags=["Soil"])

class SoilAnalysis(BaseModel):
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

def initialize():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS agr_soil_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, parcel_id TEXT NOT NULL,
            sample_date TEXT NOT NULL, source TEXT NOT NULL,
            ph REAL, nitrogen_g_kg REAL, sand_percent REAL, silt_percent REAL,
            clay_percent REAL, phosphorus_mg_kg REAL, potassium_mg_kg REAL, notes TEXT)""")

initialize()

@router.post("/analyses", status_code=201)
def add_analysis(item: SoilAnalysis):
    values=item.model_dump(mode="json")
    with connect() as db:
        columns=list(values)
        cursor=db.execute(f"INSERT INTO agr_soil_analyses ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", list(values.values()))
        return dict(db.execute("SELECT * FROM agr_soil_analyses WHERE id=?", (cursor.lastrowid,)).fetchone())

@router.get("/analyses")
def list_analyses(parcel_id: str):
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM agr_soil_analyses WHERE parcel_id=? ORDER BY sample_date DESC,id DESC", (parcel_id,))]


class SoilSearchRequest(BaseModel):
    parcel_id: str = Field(min_length=1)
    points: list[dict[str, float]] = Field(min_length=3, max_length=2000)

@router.post("/automatic-analysis")
async def automatic_analysis(item: SoilSearchRequest):
    try:
        return await search_soil(item.points)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
