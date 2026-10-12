"""Cicli colturali e osservazioni BBCH; database SQLite locale."""
import os
import sqlite3
from pathlib import Path
from datetime import date
from fastapi import HTTPException
from pydantic import BaseModel, Field

DB = Path(os.getenv("AGROPLAN_DB_PATH", str(Path(__file__).with_name("agroplan.db"))))

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def initialize():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS agr_crop_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, parcel_id TEXT NOT NULL,
            season TEXT NOT NULL, crop TEXT NOT NULL, variety TEXT,
            sowing_date TEXT, UNIQUE(parcel_id, season))""")
        db.execute("""CREATE TABLE IF NOT EXISTS agr_bbch_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER NOT NULL,
            observed_at TEXT NOT NULL, bbch INTEGER NOT NULL CHECK(bbch BETWEEN 0 AND 99),
            notes TEXT, FOREIGN KEY(cycle_id) REFERENCES agr_crop_cycles(id) ON DELETE CASCADE)""")

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

def register_crop_routes(app):
    initialize()
    @app.get("/crop/cycles")
    def list_cycles(parcel_id: str):
        with connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM agr_crop_cycles WHERE parcel_id=? ORDER BY season DESC", (parcel_id,))]

    @app.post("/crop/cycles", status_code=201)
    def save_cycle(item: CycleIn):
        with connect() as db:
            db.execute("""INSERT INTO agr_crop_cycles(parcel_id, season, crop, variety, sowing_date)
                VALUES(?,?,?,?,?) ON CONFLICT(parcel_id,season) DO UPDATE SET
                crop=excluded.crop, variety=excluded.variety, sowing_date=excluded.sowing_date""",
                (item.parcel_id, item.season, item.crop, item.variety, str(item.sowing_date) if item.sowing_date else None))
            return dict(db.execute("SELECT * FROM agr_crop_cycles WHERE parcel_id=? AND season=?", (item.parcel_id, item.season)).fetchone())

    @app.get("/crop/cycles/{cycle_id}/bbch")
    def list_bbch(cycle_id: int):
        with connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM agr_bbch_observations WHERE cycle_id=? ORDER BY observed_at DESC,id DESC", (cycle_id,))]

    @app.post("/crop/cycles/{cycle_id}/bbch", status_code=201)
    def add_bbch(cycle_id: int, item: BBCHIn):
        with connect() as db:
            if not db.execute("SELECT id FROM agr_crop_cycles WHERE id=?", (cycle_id,)).fetchone():
                raise HTTPException(404, "Ciclo non trovato")
            cursor=db.execute("INSERT INTO agr_bbch_observations(cycle_id,observed_at,bbch,notes) VALUES(?,?,?,?)", (cycle_id,str(item.observed_at),item.bbch,item.notes))
            return dict(db.execute("SELECT * FROM agr_bbch_observations WHERE id=?", (cursor.lastrowid,)).fetchone())
