from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import base64,json,re,sqlite3
import pytest

TOKEN={'_csrf':'test-csrf'}
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+c5j8AAAAASUVORK5CYII=')

def logo_upload(client,content=PNG,name='logo.png'):
    return client.post('/admin/identidade',data={**TOKEN,'logo':(BytesIO(content),name)})

def current_logo(system):
    con=system.connect();row=con.execute('SELECT logo_filename FROM company_branding WHERE id=1').fetchone();con.close()
    return row[0] if row else None

def counts(system):
    con=system.connect()
    result={table:con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ['machines','machine_photos','clients','service_orders','service_items']}
    con.close();return result

def test_delete_review_identifies_orphan_without_modifying_records(system,admin):
    before=counts(system)
    response=admin.get('/machines/1/delete')
    assert response.status_code==200
    html=response.get_data(as_text=True)
    assert 'Sem vínculo com cliente' in html and 'Digite 1 para confirmar' in html
    assert '25030713' in html
    assert counts(system)==before
    assert 'href="/machines/1/delete"' in admin.get('/machines/1').get_data(as_text=True)
    assert 'href="/machines/1/delete"' in admin.get('/admin/conferencia').get_data(as_text=True)

@pytest.mark.parametrize('confirmation',['','errado','2'])
def test_delete_wrong_confirmation_does_not_touch_database(system,admin,confirmation):
    before=counts(system)
    response=admin.post('/machines/1/delete',data={**TOKEN,'confirmation':confirmation})
    assert response.status_code==400
    assert counts(system)==before
    assert not list((Path(system.DATA_DIR)/'backups').glob('*antes-excluir-maquina*'))

def test_delete_orphan_keeps_orders_clients_and_recoverable_original_files(system,admin):
    con=system.connect()
    # Ligação histórica com proprietário divergente, como em bancos antigos.
    oid=con.execute("INSERT INTO service_orders(reseller_id,client_id,machine_id,obs) VALUES (1,7,1,'Histórico a preservar')").lastrowid
    con.execute('INSERT INTO service_items(order_id,item_text) VALUES (?,?)',(oid,'Serviço preservado'))
    filename='machine_1/recovery-test.pdf'
    original=Path(system.UPLOAD_DIR)/filename;original.parent.mkdir(exist_ok=True);original.write_bytes(b'%PDF-original-test')
    con.execute('INSERT INTO machine_photos(machine_id,filename) VALUES (1,?)',(filename,))
    other_machine=dict(con.execute('SELECT * FROM machines WHERE id=2').fetchone())
    con.commit();con.close();before=counts(system)
    response=admin.post('/machines/1/delete',data={**TOKEN,'confirmation':'1'})
    assert response.status_code==302 and response.location=='/machines'
    after=counts(system)
    assert after=={**before,'machines':before['machines']-1,'machine_photos':before['machine_photos']-1}
    con=system.connect()
    assert con.execute('SELECT id FROM machines WHERE id=1').fetchone() is None
    assert dict(con.execute('SELECT * FROM machines WHERE id=2').fetchone())==other_machine
    order=con.execute('SELECT * FROM service_orders WHERE id=?',(oid,)).fetchone()
    assert order['machine_id'] is None and order['obs']=='Histórico a preservar' and order['client_id']==7
    event=json.loads(con.execute("SELECT details FROM maintenance_events WHERE action='excluir_maquina'").fetchone()[0])
    assert event['machine']['id']==1 and oid in {row['id'] for row in event['orders']}
    assert filename in {row['filename'] for row in event['photos']}
    con.close()
    assert original.read_bytes()==b'%PDF-original-test'
    assert admin.get('/uploads/'+filename).status_code==404
    assert admin.get('/machines/1').status_code==404
    assert admin.get(f'/os/{oid}').status_code==200
    assert 'Serviço preservado' in admin.get(f'/os/{oid}/print').get_data(as_text=True)
    copies=list((Path(system.DATA_DIR)/'backups').glob('*antes-excluir-maquina*'))
    assert len(copies)==1
    previous=sqlite3.connect(copies[0]);assert previous.execute('SELECT client_id FROM machines WHERE id=1').fetchone()[0]==1;previous.close()

def test_delete_failure_rolls_back_database_changes(system,admin,monkeypatch):
    con=system.connect()
    oid=con.execute('INSERT INTO service_orders(reseller_id,client_id,machine_id) VALUES (1,7,2)').lastrowid
    con.commit();con.close();before=counts(system)
    def fail_event(*args):raise RuntimeError('simulated log failure')
    monkeypatch.setattr(system,'record_event',fail_event)
    with pytest.raises(RuntimeError):admin.post('/machines/2/delete',data={**TOKEN,'confirmation':'2'})
    assert counts(system)==before
    con=system.connect();assert con.execute('SELECT machine_id FROM service_orders WHERE id=?',(oid,)).fetchone()[0]==2;con.close()

def test_delete_does_not_run_when_backup_fails(system,admin,monkeypatch):
    before=counts(system)
    def fail_backup(*args):raise OSError('simulated disk failure')
    monkeypatch.setattr(system,'snapshot',fail_backup)
    with pytest.raises(OSError):admin.post('/machines/1/delete',data={**TOKEN,'confirmation':'1'})
    assert counts(system)==before

def test_delete_is_admin_only_and_requires_csrf(system,admin,reseller):
    client,_,_,mid=reseller;before=counts(system)
    assert client.get(f'/machines/{mid}/delete').status_code==302
    assert client.post(f'/machines/{mid}/delete',data={**TOKEN,'confirmation':str(mid)}).status_code==302
    assert 'Excluir máquina' not in client.get(f'/machines/{mid}').get_data(as_text=True)
    assert admin.post('/machines/1/delete',data={'confirmation':'1'}).status_code==400
    assert system.app.test_client().get('/machines/1/delete').status_code==302
    assert counts(system)==before

def test_delete_missing_or_already_removed_machine_is_404(admin):
    assert admin.get('/machines/99999/delete').status_code==404
    assert admin.post('/machines/1/delete',data={**TOKEN,'confirmation':'1'}).status_code==302
    assert admin.post('/machines/1/delete',data={**TOKEN,'confirmation':'1'}).status_code==404

def test_archived_machine_can_be_deleted(system,admin):
    admin.post('/machines/1/archive',data={**TOKEN,'confirmation':'1','reason':'teste'})
    assert admin.get('/machines/1/delete').status_code==200
    assert admin.post('/machines/1/delete',data={**TOKEN,'confirmation':'1'}).status_code==302
    con=system.connect();assert con.execute('SELECT id FROM machines WHERE id=1').fetchone() is None;con.close()

def test_logo_persists_and_is_used_on_login_menu_and_both_prints(system,admin):
    assert logo_upload(admin).status_code==302
    filename=current_logo(system);assert re.fullmatch(r'logo-[0-9a-f]{32}\.png',filename)
    assert (Path(system.UPLOAD_DIR)/'company_brand'/filename).read_bytes()==PNG
    public=system.app.test_client();response=public.get('/brand/'+filename)
    assert response.status_code==200 and response.data==PNG
    assert response.mimetype=='image/png' and response.headers['X-Content-Type-Options']=='nosniff'
    for path in ['/login','/','/machines/2/print','/os/5/print','/admin/identidade']:
        html=admin.get(path).get_data(as_text=True)
        assert '/brand/'+filename in html
        assert '45.154.368/0001-42' in html
    system.init_db();assert current_logo(system)==filename

def test_logo_replacement_and_removal_hide_previous_public_urls(system,admin):
    logo_upload(admin);first=current_logo(system)
    logo_upload(admin);second=current_logo(system)
    assert first!=second and admin.get('/brand/'+first).status_code==404
    assert (Path(system.UPLOAD_DIR)/'company_brand'/first).exists()
    assert admin.post('/admin/identidade',data={**TOKEN,'action':'remove'}).status_code==302
    assert current_logo(system) is None and admin.get('/brand/'+second).status_code==404
    assert 'brand-mark' in admin.get('/login').get_data(as_text=True)

@pytest.mark.parametrize('content,name',[(b'<svg/>','logo.svg'),(b'fake image','logo.png'),(PNG,'logo.html'),(PNG+b'x'*(2*1024*1024),'logo.png'),(b'','logo.png')])
def test_invalid_logo_does_not_overwrite_current_brand(system,admin,content,name):
    logo_upload(admin);before=current_logo(system)
    assert logo_upload(admin,content,name).status_code==400
    assert current_logo(system)==before
    assert len(list((Path(system.UPLOAD_DIR)/'company_brand').iterdir()))==1

def test_logo_is_admin_only_and_requires_csrf(system,admin,reseller):
    client,_,_,_=reseller
    assert client.get('/admin/identidade').status_code==302
    assert logo_upload(client).status_code==302
    assert admin.post('/admin/identidade',data={'logo':(BytesIO(PNG),'logo.png')}).status_code==400
    assert current_logo(system) is None

def test_missing_or_untrusted_logo_path_has_safe_fallback(system,admin):
    logo_upload(admin);name=current_logo(system)
    (Path(system.UPLOAD_DIR)/'company_brand'/name).unlink()
    assert admin.get('/brand/'+name).status_code==404
    assert 'brand-mark' in admin.get('/login').get_data(as_text=True)
    con=system.connect();con.execute("UPDATE company_branding SET logo_filename='../solutec.db'");con.commit();con.close()
    assert admin.get('/admin/identidade').status_code==200
    assert admin.get('/brand/solutec.db').status_code==404

def test_backup_includes_uploaded_logo(system,admin):
    logo_upload(admin);name=current_logo(system)
    response=admin.post('/admin/backup',data=TOKEN)
    with ZipFile(BytesIO(response.data)) as archive:
        assert archive.read('uploads/company_brand/'+name)==PNG

def test_dashboard_uses_real_photos_without_assigning_them_to_customer_machines(system,admin):
    before=counts(system)
    html=admin.get('/').get_data(as_text=True)
    for name in ['tractor-trailer.webp','tractor-yard.webp','tractor-detail.webp','tractor-loader.webp']:
        assert '/static/solutec/'+name in html
        assert admin.get('/static/solutec/'+name).status_code==200
    assert counts(system)==before
