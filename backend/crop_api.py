"""Cicli colturali e osservazioni BBCH; database SQLite locale."""
from datetime import date
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from storage import connect
from auth import CurrentUser, require_parcel, require_cycle

class CycleIn(BaseModel):
    parcel_id: str = Field(min_length=1)
    season: str = Field(min_length=1)
    crop: str = Field(min_length=1)
    variety: str | None = None
    sowing_date: date | None = None

class BBCHIn(BaseModel):
    observed_at: date
    bbch: int = Field(ge=0, le=99)
    notes: str | None = None
    @model_validator(mode='after')
    def observed_date(self):
        if self.observed_at > date.today():
            raise ValueError('La data del rilievo non può essere futura.')
        return self

def register_crop_routes(app):
    @app.get("/crop/cycles")
    def list_cycles(parcel_id: str, user: CurrentUser):
        require_parcel(parcel_id, user)
        with connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM agr_crop_cycles WHERE parcel_id=? ORDER BY season DESC", (parcel_id,))]

    @app.post("/crop/cycles", status_code=201)
    def save_cycle(item: CycleIn, user: CurrentUser):
        require_parcel(item.parcel_id, user)
        with connect() as db:
            db.execute("""INSERT INTO agr_crop_cycles(parcel_id, season, crop, variety, sowing_date)
                VALUES(?,?,?,?,?) ON CONFLICT(parcel_id,season) DO UPDATE SET
                crop=excluded.crop, variety=excluded.variety, sowing_date=excluded.sowing_date""",
                (item.parcel_id, item.season, item.crop, item.variety, str(item.sowing_date) if item.sowing_date else None))
            return dict(db.execute("SELECT * FROM agr_crop_cycles WHERE parcel_id=? AND season=?", (item.parcel_id, item.season)).fetchone())

    @app.get("/crop/cycles/{cycle_id}/bbch")
    def list_bbch(cycle_id: int, user: CurrentUser):
        cycle = require_cycle(cycle_id, user)
        with connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM agr_bbch_observations WHERE cycle_id=? ORDER BY observed_at DESC,id DESC", (cycle_id,))]
        from phenology import assess
        return [dict(r,phenology=assess(dict(cycle,latest_bbch=r))) for r in rows]

    @app.post("/crop/cycles/{cycle_id}/bbch", status_code=201)
    def add_bbch(cycle_id: int, item: BBCHIn, user: CurrentUser):
        require_cycle(cycle_id, user)
        with connect() as db:
            if not db.execute("SELECT id FROM agr_crop_cycles WHERE id=?", (cycle_id,)).fetchone():
                raise HTTPException(404, "Ciclo non trovato")
            cursor=db.execute("INSERT INTO agr_bbch_observations(cycle_id,observed_at,bbch,notes) VALUES(?,?,?,?)", (cycle_id,str(item.observed_at),item.bbch,item.notes))
            return dict(db.execute("SELECT * FROM agr_bbch_observations WHERE id=?", (cursor.lastrowid,)).fetchone())
