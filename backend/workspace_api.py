"""Recoverable farm-scoped workspace reset and explicit archive restoration."""
from datetime import datetime, timezone
import json
from uuid import uuid4, UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from auth import CurrentUser
from storage import connect

router=APIRouter(prefix='/workspace',tags=['Area di lavoro'])


class WorkspaceChange(BaseModel):
    expected_generation:int=Field(ge=0)


def status(farm_id):
    with connect() as db:
        row=db.execute('SELECT COALESCE((SELECT generation FROM agr_workspace_state WHERE farm_id=?),0) AS generation, '
                       '(SELECT count(*) FROM agr_parcels WHERE farm_id=? AND deleted=0) AS active_parcels',(farm_id,farm_id)).fetchone()
    return dict(row)


def archive_workspace(farm_id,expected_generation):
    now=datetime.now(timezone.utc).isoformat()
    with connect() as db:
        # Both database adapters serialize this with parcel saves/deletes.
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO agr_workspace_state(farm_id,generation) VALUES(?,0) ON CONFLICT(farm_id) DO NOTHING',(farm_id,))
        generation=db.execute('SELECT generation FROM agr_workspace_state WHERE farm_id=?',(farm_id,)).fetchone()['generation']
        if generation!=expected_generation:raise HTTPException(409,'Area di lavoro aggiornata altrove. Ricarica prima di continuare.')
        rows=[dict(r) for r in db.execute('SELECT * FROM agr_parcels WHERE farm_id=? AND deleted=0 ORDER BY id',(farm_id,))]
        archive_id=str(uuid4()) if rows else None
        if rows:
            payload=json.dumps({'generation_before':generation,'parcels':rows},sort_keys=True,allow_nan=False)
            db.execute('INSERT INTO agr_workspace_archives(id,farm_id,created_at,payload) VALUES(?,?,?,?)',(archive_id,farm_id,now,payload))
            # Related records stay protected behind these tombstones and can
            # be recovered through the normal restore flow. No auth changes.
            db.execute('UPDATE agr_parcels SET deleted=1,payload=NULL,revision=revision+1 WHERE farm_id=? AND deleted=0',(farm_id,))
        db.execute('UPDATE agr_workspace_state SET generation=generation+1 WHERE farm_id=?',(farm_id,))
    return {'generation':generation+1,'archived_parcels':len(rows),'archive_id':archive_id}


def restore_workspace(farm_id,archive_id,expected_generation):
    now=datetime.now(timezone.utc).isoformat();restored=0
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM agr_workspace_archives WHERE id=? AND farm_id=?',(archive_id,farm_id)).fetchone()
        if not row:raise HTTPException(404,'Archivio non trovato.')
        generation_row=db.execute('SELECT generation FROM agr_workspace_state WHERE farm_id=?',(farm_id,)).fetchone()
        generation=generation_row['generation'] if generation_row else 0
        if generation!=expected_generation:raise HTTPException(409,'Area di lavoro aggiornata altrove. Ricarica prima di continuare.')
        if not row['restored_at']:
            for parcel in json.loads(row['payload'])['parcels']:
                current=db.execute('SELECT * FROM agr_parcels WHERE id=?',(parcel['id'],)).fetchone()
                if not current or current['farm_id']!=farm_id:
                    raise HTTPException(409,'Archivio non ripristinabile senza verifica: nessun dato è stato sovrascritto.')
                if current['deleted']:
                    db.execute('UPDATE agr_parcels SET deleted=0,payload=?,revision=revision+1 WHERE id=? AND farm_id=?',(parcel['payload'],parcel['id'],farm_id))
                    restored+=1
            db.execute('UPDATE agr_workspace_archives SET restored_at=? WHERE id=?',(now,archive_id))
    # Restore is additive. Keeping the generation preserves newer offline edits.
    return {'generation':generation,'restored_parcels':restored}


@router.get('/status')
def workspace_status(user:CurrentUser):return status(user.farm_id)


@router.get('/archives')
def workspace_archives(user:CurrentUser):
    with connect() as db:
        rows=db.execute('SELECT * FROM agr_workspace_archives WHERE farm_id=? ORDER BY created_at DESC LIMIT 20',(user.farm_id,)).fetchall()
    return [{'id':r['id'],'created_at':r['created_at'],'restored_at':r['restored_at'],
             'parcel_count':len(json.loads(r['payload'])['parcels'])} for r in rows]


@router.post('/reset')
def reset_workspace(item:WorkspaceChange,user:CurrentUser):return archive_workspace(user.farm_id,item.expected_generation)


@router.post('/archives/{archive_id}/restore')
def restore_archive(archive_id:UUID,item:WorkspaceChange,user:CurrentUser):return restore_workspace(user.farm_id,str(archive_id),item.expected_generation)
