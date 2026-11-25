"""Cloud parcel storage with ownership and optimistic concurrency checks."""
import json

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator

from auth import CurrentUser
from storage import connect

router = APIRouter(prefix='/parcels', tags=['Particelle'])


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Parcel(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    crop: str = Field(min_length=1, max_length=100)
    points: list[Point] = Field(min_length=3, max_length=2000)
    soil: dict[str, str] = Field(default_factory=dict, max_length=50)
    revision: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def non_degenerate(self):
        if len({(p.lat, p.lng) for p in self.points}) < 3:
            raise ValueError('Servono almeno tre vertici distinti.')
        twice_area = sum(a.lng*b.lat - b.lng*a.lat
                         for a,b in zip(self.points, self.points[1:] + self.points[:1]))
        if abs(twice_area) <= 1e-12:
            raise ValueError('Il poligono deve racchiudere una superficie.')
        return self


def conflict(row):
    return HTTPException(409, {'message': 'La particella è stata modificata su un altro dispositivo.',
        'current': json.loads(row['payload']) if row['payload'] and not row['deleted'] else None,
        'revision': row['revision'], 'deleted': bool(row['deleted'])})


@router.get('')
def list_parcels(user: CurrentUser):
    with connect() as db:
        rows = db.execute('SELECT * FROM agr_parcels WHERE farm_id=? AND deleted=0 AND payload IS NOT NULL',
                          (user.farm_id,)).fetchall()
    return [dict(json.loads(r['payload']), revision=r['revision']) for r in rows]


@router.put('/{parcel_id}')
def save_parcel(parcel_id: str, item: Parcel, user: CurrentUser):
    if parcel_id != item.id:
        raise HTTPException(422, 'Identificativo della particella incoerente.')
    payload = item.model_dump(exclude={'revision'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM agr_parcels WHERE id=?', (parcel_id,)).fetchone()
        if row is not None:
            if row['farm_id'] != user.farm_id:
                raise HTTPException(404, 'Particella non trovata.')
            if row['revision'] != item.revision or row['deleted']:
                raise conflict(row)
            revision = row['revision'] + 1
            db.execute('UPDATE agr_parcels SET payload=?,revision=? WHERE id=?',
                       (json.dumps(payload), revision, parcel_id))
        else:
            if item.revision != 0:
                raise HTTPException(409, 'La particella non esiste più sul server.')
            revision = 1
            db.execute('INSERT INTO agr_parcels(id,farm_id,payload,revision) VALUES(?,?,?,?)',
                       (parcel_id, user.farm_id, json.dumps(payload), revision))
    return dict(payload, revision=revision)


@router.delete('/{parcel_id}', status_code=204)
def delete_parcel(parcel_id: str, user: CurrentUser, revision: int = Query(ge=1)):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM agr_parcels WHERE id=? AND farm_id=?',
                         (parcel_id, user.farm_id)).fetchone()
        if row is None:
            raise HTTPException(404, 'Particella non trovata.')
        if row['deleted']:
            return Response(status_code=204)
        if row['revision'] != revision:
            raise conflict(row)
        # Keep the ordinary recovery flow available for a single deletion too.
        from datetime import datetime, timezone
        from uuid import uuid4
        db.execute('INSERT INTO agr_workspace_archives(id,farm_id,created_at,payload) VALUES(?,?,?,?)',
                   (str(uuid4()),user.farm_id,datetime.now(timezone.utc).isoformat(),
                    json.dumps({'parcels':[dict(row)]},sort_keys=True,allow_nan=False)))
        # A tombstone prevents an offline device from recreating deleted data.
        db.execute('UPDATE agr_parcels SET deleted=1,payload=NULL,revision=revision+1 WHERE id=?', (parcel_id,))
    return Response(status_code=204)
