from datetime import date
from uuid import uuid4
from storage import connect
from field_records import save_result


def test_workspace_archive_is_private_recoverable_and_preserves_related_data(client,headers,parcel):
    alice=headers();bob=headers('bob')
    assert client.put('/parcels/field-1',json=parcel,headers=alice).status_code==200
    other=dict(parcel,id='field-b');assert client.put('/parcels/field-b',json=other,headers=bob).status_code==200
    cycle=client.post('/crop/cycles',json={'parcel_id':'field-1','season':'2026','crop':'orzo'},headers=alice).json()
    client.post(f"/crop/cycles/{cycle['id']}/bbch",json={'observed_at':date.today().isoformat(),'bbch':25},headers=alice)
    client.post('/soil/analyses',json={'parcel_id':'field-1','sample_date':date.today().isoformat(),'ph':7},headers=alice)
    client.put('/observations/'+str(uuid4()),json={'parcel_id':'field-1','observed_at':date.today().isoformat(),'symptoms':['yellowing']},headers=alice)
    save_result('field-1',{'parcel_id':'field-1','crop_review':{'summary':'Record da conservare'}})
    assert client.get('/workspace/status').status_code==401
    assert client.post('/workspace/reset',json={'expected_generation':0}).status_code==401
    result=client.post('/workspace/reset',json={'expected_generation':0},headers=alice)
    assert result.status_code==200
    data=result.json();assert data['generation']==1 and data['archived_parcels']==1
    assert client.get('/parcels',headers=alice).json()==[]
    assert client.get('/agronomy/overview',headers=alice).json()['parcel_count']==0
    assert client.get('/observations?parcel_id=field-1',headers=alice).status_code==404
    assert client.get('/auth/me',headers=alice).status_code==200
    assert len(client.get('/parcels',headers=bob).json())==1
    assert client.get('/workspace/archives',headers=bob).json()==[]
    path='/workspace/archives/'+data['archive_id']+'/restore'
    assert client.post(path,json={'expected_generation':0},headers=bob).status_code==404
    archive=client.get('/workspace/archives',headers=alice).json()[0]
    assert 'payload' not in archive and archive['parcel_count']==1
    # A stale phone cannot silently recreate a tombstoned parcel.
    stale=client.put('/parcels/field-1',json=dict(parcel,revision=1),headers=alice)
    assert stale.status_code==409 and stale.json()['detail']['deleted'] is True
    assert client.post('/workspace/reset',json={'expected_generation':0},headers=alice).status_code==409
    fresh=dict(parcel,id='new-field',name='Nuovo campo')
    assert client.put('/parcels/new-field',json=fresh,headers=alice).status_code==200
    restored=client.post(path,json={'expected_generation':1},headers=alice)
    assert restored.status_code==200 and restored.json()=={'generation':1,'restored_parcels':1}
    assert len(client.get('/parcels',headers=alice).json())==2
    assert client.get('/crop/cycles?parcel_id=field-1',headers=alice).json()[0]['id']==cycle['id']
    assert len(client.get('/observations?parcel_id=field-1',headers=alice).json())==1
    assert len(client.get('/agronomy/results?parcel_id=field-1',headers=alice).json())==1
    assert client.post(path,json={'expected_generation':1},headers=alice).json()['restored_parcels']==0
    row=next(p for p in client.get('/parcels',headers=alice).json() if p['id']=='field-1')
    assert row['revision']==3


def test_empty_workspace_starts_empty_and_empty_reset_does_not_create_an_archive(client,headers):
    auth=headers()
    assert client.get('/workspace/status',headers=auth).json()=={'generation':0,'active_parcels':0}
    response=client.post('/workspace/reset',json={'expected_generation':0},headers=auth).json()
    assert response=={'generation':1,'archived_parcels':0,'archive_id':None}
    assert client.get('/workspace/archives',headers=auth).json()==[]
