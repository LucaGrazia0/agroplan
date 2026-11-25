def test_single_deletion_is_confirmable_idempotent_and_recoverable_with_related_records(client,headers,parcel):
    auth=headers();client.put('/parcels/field-1',json=parcel,headers=auth)
    cycle=client.post('/crop/cycles',json={'parcel_id':'field-1','crop':'mais','season':'2026'},headers=auth).json()
    path='/parcels/field-1?revision=1'
    assert client.delete(path,headers=headers('bob')).status_code==404
    assert client.delete(path,headers=auth).status_code==204
    assert client.delete(path,headers=auth).status_code==204
    archives=client.get('/workspace/archives',headers=auth).json()
    assert len(archives)==1 and archives[0]['parcel_count']==1
    assert client.get('/parcels',headers=auth).json()==[]
    assert client.get('/workspace/archives',headers=headers('bob')).json()==[]
    restored=client.post('/workspace/archives/'+archives[0]['id']+'/restore',json={'expected_generation':0},headers=auth)
    assert restored.status_code==200 and restored.json()['restored_parcels']==1
    assert client.get('/parcels',headers=auth).json()[0]['revision']==3
    assert client.get('/crop/cycles?parcel_id=field-1',headers=auth).json()[0]['id']==cycle['id']
