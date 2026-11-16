from io import BytesIO
from pathlib import Path
import json,sqlite3,zipfile,unicodedata
import pytest
from maintenance import audit,attachment_path

TOKEN={'_csrf':'test-csrf'}
def post(client,path,**data):
    return client.post(path,data={**TOKEN,**data},follow_redirects=True)
def count(system,table):
    con=system.connect();result=con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0];con.close();return result

def machine_data(**changes):
    return dict(client_id='7',name='Máquina de teste',brand='Bruthor',model='2026',motor_model='Teste',nf_number='T900',
                serial_number='NOVO-900',engine_number='MOTOR-900',delivery_date='2026-11-16',initial_hours='0',**changes)

@pytest.mark.parametrize('path',['/','/machines','/machines?status=orphan','/machines?status=review','/machines/1',
 '/machines/2','/machines/new','/machines/2/edit','/machines/2/print','/clients','/clients/new','/clients/7/edit',
 '/clients/7/painel','/os/1','/os/1/print','/os/5','/resellers','/admin/conferencia'])
def test_existing_pages_open(admin,path):
    assert admin.get(path).status_code==200

def test_seed_audit_exposes_hidden_machine_and_old_orders(system,admin):
    con=system.connect();report=audit(con,system.UPLOAD_DIR);con.close()
    assert len(report['active'])==21
    assert [m['id'] for m in report['orphan_machines']]==[1]
    assert {o['id'] for o in report['orphan_orders']}=={1,2,3,4}
    orphan=report['orphan_machines'][0]
    assert orphan['duplicate_ids']==[2]
    candidate=next(m for m in report['active'] if m['id']==2)
    assert candidate['client_name']=='Sebastião Claudio dos Santos'
    assert len(report['duplicates'])==5
    assert len(report['review_machines'])==6
    assert b'/machines/1' in admin.get('/machines').data

def test_all_ten_legacy_pdf_attachments_open_with_accents(system,admin):
    con=system.connect();files=[r['filename'] for r in con.execute('SELECT filename FROM machine_photos')];con.close()
    assert len(files)==10
    for file in files:
        response=admin.get('/uploads/'+file)
        assert response.status_code==200,file
        assert response.data.startswith(b'%PDF-'),file
    con=system.connect();report=audit(con,system.UPLOAD_DIR);con.close()
    assert report['missing_files']==[]

def test_pdf_rendered_as_document_not_broken_image(admin):
    response=admin.get('/machines/2').get_data(as_text=True)
    assert 'pdf-mark' in response
    assert '<img src="/uploads/' not in response

@pytest.mark.parametrize('query,expected',[('sebastiao',2),('Bruthor',21),('25030713',1),('L820310661B',2),('173',21),('2026/2026',21)])
def test_search_name_model_serial_motor_nf_and_accents(admin,query,expected):
    from urllib.parse import quote
    html=admin.get('/machines?q='+quote(query)).get_data(as_text=True)
    assert 'href="/machines/'+str(expected)+'"' in html

@pytest.mark.parametrize('field,value',[('serial_number','25030713'),('engine_number','L820310661B'),('serial_number','2503-0713'),('engine_number','l820310661b')])
def test_duplicate_machine_is_rejected(system,admin,field,value):
    data=machine_data();data[field]=value
    response=post(admin,'/machines/new',**data)
    assert 'já está cadastrado' in response.get_data(as_text=True)
    assert count(system,'machines')==21

@pytest.mark.parametrize('field,value',[('client_id','99999'),('initial_hours','-1'),('initial_hours','NaN'),('initial_hours','infinity'),('initial_hours','abc'),('delivery_date','2026-02-30'),('name','')])
def test_invalid_machine_values_do_not_write(system,admin,field,value):
    data=machine_data();data[field]=value
    response=post(admin,'/machines/new',**data)
    assert response.status_code==200
    assert count(system,'machines')==21
    assert 'flash error' in response.get_data(as_text=True)

def test_create_edit_machine_and_keep_zero_hours(system,admin):
    response=post(admin,'/machines/new',**machine_data())
    assert response.status_code==200
    assert '0.0 h' in response.get_data(as_text=True)
    con=system.connect();m=con.execute('SELECT * FROM machines WHERE serial_number=?',('NOVO-900',)).fetchone();con.close()
    assert m['client_id']==7 and m['initial_hours']==0
    data=machine_data();data['name']='Nome alterado';data['initial_hours']='12,5'
    assert 'Nome alterado' in post(admin,f'/machines/{m["id"]}/edit',**data).get_data(as_text=True)
    con=system.connect();assert con.execute('SELECT initial_hours FROM machines WHERE id=?',(m['id'],)).fetchone()[0]==12.5;con.close()

def test_legacy_duplicates_can_be_edited_without_reentering_identifiers(system,admin):
    con=system.connect();row=dict(con.execute('SELECT * FROM machines WHERE id=2').fetchone());con.close()
    fields=machine_data().keys();data={k:'' if row[k] is None else str(row[k]) for k in fields};data['name']='Cadastro legado corrigido'
    html=post(admin,'/machines/2/edit',**data).get_data(as_text=True)
    assert 'Máquina salva com sucesso' in html

def test_invalid_client_reseller_is_rejected(system,admin):
    response=post(admin,'/clients/new',name='Teste',reseller_id='999999')
    assert 'revenda válida' in response.get_data(as_text=True)
    assert count(system,'clients')==20

def test_create_edit_client_and_search_contact(system,admin):
    r=post(admin,'/clients/new',name='Cliente QA',reseller_id=1,phone='32988887777',cpf='QA123')
    assert 'Cliente salvo com sucesso' in r.get_data(as_text=True)
    con=system.connect();cid=con.execute("SELECT id FROM clients WHERE name='Cliente QA'").fetchone()[0];con.close()
    post(admin,f'/clients/{cid}/edit',name='Cliente QA editado',reseller_id=1,phone='32988887777',cpf='QA123')
    assert 'Cliente QA editado' in admin.get('/clients?q=32988887777').get_data(as_text=True)

def test_os_cannot_reference_machine_of_different_client(system,admin):
    response=post(admin,'/clients/7/os/nova',machine_id='3',service_date='2026-11-16',pending_item='Troca')
    assert 'não pertence' in response.get_data(as_text=True)
    assert count(system,'service_orders')==6

def test_os_saves_pending_item_even_without_add_button(system,admin):
    r=post(admin,'/clients/7/os/nova',machine_id='2',service_date='2026-11-16',pending_item='Revisão sem clicar adicionar',**{'items[]':['Óleo','Filtro']})
    assert r.status_code==200
    assert 'Revisão sem clicar adicionar' in r.get_data(as_text=True)
    assert count(system,'service_orders')==7
    assert count(system,'service_items')==4

def test_pdf_upload_notes_and_safe_name(system,admin):
    r=post(admin,'/machines/2',obs_text='Observação de teste',photos=(BytesIO(b'%PDF-1.4\nExample QA'),'../../arquivo.pdf'))
    assert 'Observações e anexos salvos' in r.get_data(as_text=True)
    con=system.connect();filename=con.execute('SELECT filename FROM machine_photos ORDER BY id DESC LIMIT 1').fetchone()[0];con.close()
    assert filename.startswith('machine_2/') and '..' not in filename
    assert admin.get('/uploads/'+filename).data.startswith(b'%PDF-')
    assert 'Observação de teste' in admin.get('/machines/2').get_data(as_text=True)

def test_invalid_upload_rolls_back_notes_and_files(system,admin):
    con=system.connect();old=con.execute('SELECT obs FROM machines WHERE id=2').fetchone()[0];con.close()
    response=post(admin,'/machines/2',obs_text='Não salvar',photos=(BytesIO(b'<script>bad</script>'),'fake.pdf'))
    assert 'Formato inválido' in response.get_data(as_text=True)
    con=system.connect();assert con.execute('SELECT obs FROM machines WHERE id=2').fetchone()[0]==old;con.close()
    assert count(system,'machine_photos')==10

def test_delete_attachment_preserves_recoverable_file(system,admin):
    con=system.connect();photo=con.execute('SELECT * FROM machine_photos WHERE machine_id=2').fetchone();con.close()
    path=attachment_path(system.UPLOAD_DIR,photo['filename'])
    r=post(admin,f'/machines/2/photos/{photo["id"]}/delete')
    assert r.status_code==200 and count(system,'machine_photos')==9
    assert path.exists()
    assert admin.get('/uploads/'+photo['filename']).status_code==404
    assert list((Path(system.DATA_DIR)/'backups').glob('*antes-remover-anexo*'))

def test_archive_is_explicit_reversible_and_keeps_records(system,admin):
    post(admin,'/machines/1/archive',reason='Conferido como duplicado',confirmation='wrong')
    assert 'Cadastro arquivado.' not in admin.get('/machines/1').get_data(as_text=True)
    r=post(admin,'/machines/1/archive',reason='Conferido como duplicado',confirmation='1')
    assert 'Cadastro arquivado' in r.get_data(as_text=True)
    assert count(system,'machines')==21 and count(system,'service_orders')==6
    assert 'href="/machines/1"' not in admin.get('/machines').get_data(as_text=True)
    assert 'href="/machines/1"' in admin.get('/machines?status=archived').get_data(as_text=True)
    post(admin,'/machines/1/archive',action='restore')
    con=system.connect();assert con.execute('SELECT archived_at FROM machines WHERE id=1').fetchone()[0] is None;con.close()
    assert count(system,'maintenance_events')==2

def test_relink_orphan_os_requires_confirmation_and_records_history(system,admin):
    post(admin,'/admin/os/1/relink',client_id='7',confirmation='wrong')
    con=system.connect();assert con.execute('SELECT client_id FROM service_orders WHERE id=1').fetchone()[0]==5;con.close()
    post(admin,'/admin/os/1/relink',client_id='7',confirmation='1')
    con=system.connect();assert con.execute('SELECT client_id FROM service_orders WHERE id=1').fetchone()[0]==7;con.close()
    assert count(system,'maintenance_events')==1

def test_os_with_machine_cannot_be_relinked_to_conflicting_owner(system,admin):
    response=post(admin,'/admin/os/4/relink',client_id='7',confirmation='4')
    assert 'Primeiro corrija' in response.get_data(as_text=True)
    con=system.connect();assert con.execute('SELECT client_id FROM service_orders WHERE id=4').fetchone()[0]==1;con.close()

def test_backup_contains_consistent_database_and_all_attachments(system,admin,tmp_path):
    response=admin.post('/admin/backup',data=TOKEN)
    assert response.status_code==200
    with zipfile.ZipFile(BytesIO(response.data)) as z:
        assert 'solutec.db' in z.namelist()
        assert len([n for n in z.namelist() if n.startswith('uploads/')])==12
        target=tmp_path/'backup.db';target.write_bytes(z.read('solutec.db'))
    con=sqlite3.connect(target)
    assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert con.execute('SELECT COUNT(*) FROM machines').fetchone()[0]==21
    con.close()

@pytest.mark.parametrize('path',['/','/machines','/clients','/machines/2','/uploads/machine_2/test.pdf','/admin/conferencia'])
def test_anonymous_users_cannot_view_private_data(system,path):
    r=system.app.test_client().get(path)
    assert r.status_code==302 and '/login' in r.location

@pytest.mark.parametrize('path',['/machines/2','/machines/2/edit','/machines/2/print','/clients/7/edit','/clients/7/painel','/os/5','/os/5/print'])
def test_reseller_cannot_read_other_reseller_records(reseller,path):
    client,*_=reseller
    assert client.get(path).status_code in (302,403)

def test_reseller_only_sees_own_counts_and_cannot_download_other_pdf(system,reseller):
    client,rid,cid,mid=reseller
    html=client.get('/machines').get_data(as_text=True)
    assert 'Máquina da revenda' in html and 'Sebastião' not in html
    con=system.connect();file=con.execute('SELECT filename FROM machine_photos WHERE machine_id=2').fetchone()[0];con.close()
    assert client.get('/uploads/'+file).status_code==404
    for path in ('/admin/conferencia',): assert client.get(path).status_code==302
    assert client.post('/admin/backup',data=TOKEN).status_code==302
    assert client.post('/machines/1/archive',data={**TOKEN,'reason':'x','confirmation':'1'}).status_code==302

def test_reseller_cannot_assign_machine_to_other_client(system,reseller):
    client,rid,cid,mid=reseller
    response=post(client,'/machines/new',**machine_data())
    assert 'cliente válido' in response.get_data(as_text=True)
    assert count(system,'machines')==22

def test_csrf_is_required_even_for_login_and_admin(admin,system):
    assert admin.post('/machines/new',data=machine_data()).status_code==400
    assert admin.post('/admin/backup').status_code==400
    assert system.app.test_client().post('/login',data={'email':'x','password':'x'}).status_code==400

def test_login_external_redirect_is_rejected_and_session_rotated(system,admin):
    from werkzeug.security import generate_password_hash
    con=system.connect();con.execute('UPDATE users SET password_hash=? WHERE id=1',(generate_password_hash('qa-login'),));con.commit();con.close()
    client=system.app.test_client();client.get('/login')
    with client.session_transaction() as s: token=s['_csrf'];s['untrusted']='old'
    r=client.post('/login?next=https://example.org',data={'_csrf':token,'email':'solutec.divinomg@gmail.com','password':'qa-login'})
    assert r.location=='/'
    with client.session_transaction() as s: assert 'untrusted' not in s and s['user_id']==1

def test_delete_client_cleans_legacy_dependencies_without_new_orphans(system,admin):
    r=post(admin,'/clients/new',name='Excluir QA',reseller_id='1')
    con=system.connect();cid=con.execute("SELECT id FROM clients WHERE name='Excluir QA'").fetchone()[0];con.close()
    data=machine_data();data['client_id']=str(cid);post(admin,'/machines/new',**data)
    con=system.connect();mid=con.execute('SELECT id FROM machines WHERE client_id=?',(cid,)).fetchone()[0];before={tuple(r) for r in con.execute('PRAGMA foreign_key_check')};con.close()
    post(admin,f'/clients/{cid}/os/nova',machine_id=str(mid),pending_item='Teste')
    response=post(admin,f'/clients/{cid}/delete')
    assert 'Cliente e vínculos excluídos' in response.get_data(as_text=True)
    assert count(system,'clients')==20 and count(system,'machines')==21 and count(system,'service_orders')==6
    con=system.connect();assert {tuple(r) for r in con.execute('PRAGMA foreign_key_check')}==before;con.close()

def test_migration_is_idempotent_and_preserves_legacy_data(system):
    con=system.connect();before=con.execute('SELECT id,client_id,serial_number,obs FROM machines ORDER BY id').fetchall();con.close()
    system.init_db();system.init_db()
    con=system.connect();after=con.execute('SELECT id,client_id,serial_number,obs FROM machines ORDER BY id').fetchall();con.close()
    assert [tuple(r) for r in before]==[tuple(r) for r in after]
    assert len(list((Path(system.DATA_DIR)/'backups').glob('*antes-atualizacao*')))==1

def test_fresh_database_without_seed_has_working_obs(system,admin,tmp_path,monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD","fresh-qa-only-password")
    old=system.DB_PATH;system.DB_PATH=str(tmp_path/'new.db')
    try:
        system.init_db()
        con=system.connect();rid=con.execute('SELECT id FROM resellers LIMIT 1').fetchone()[0]
        cid=con.execute('INSERT INTO clients(name,reseller_id) VALUES (?,?)',('Primeiro cliente',rid)).lastrowid
        mid=con.execute('INSERT INTO machines(name,reseller_id,client_id,obs) VALUES (?,?,?,?)',('Máquina nova',rid,cid,'OBS inicial')).lastrowid
        con.commit();con.close()
        assert 'OBS inicial' in admin.get(f'/machines/{mid}').get_data(as_text=True)
        assert admin.get(f'/machines/{mid}/print').status_code==200
    finally: system.DB_PATH=old

@pytest.mark.parametrize('number,expected',[('(32) 99999-0000','5532999990000'),('(55) 99999-0000','5555999990000'),('+55 32 99999-0000','5532999990000'),('123',None)])
def test_brazilian_phone_with_ddd_55_is_normalized(system,number,expected):
    assert system.normalize_phone(number)==expected

@pytest.mark.parametrize('path',['../solutec.db','machine_2/../../solutec.db','/etc/passwd','machine_2/folder/file.pdf','machine_2\\bad.pdf'])
def test_attachment_path_cannot_escape_uploads(system,path):
    assert attachment_path(system.UPLOAD_DIR,path) is None

def test_payload_limit_has_readable_error(admin,system):
    original=system.app.config['MAX_CONTENT_LENGTH']
    system.app.config['MAX_CONTENT_LENGTH']=1024
    try:
        response=admin.post('/machines/2',data={**TOKEN,'photos':(BytesIO(b'x'*2048),'large.pdf')})
        assert response.status_code==413
        assert 'Envie até 25 MB' in response.get_data(as_text=True)
    finally: system.app.config['MAX_CONTENT_LENGTH']=original

def test_health_reports_readiness_and_missing_database(system,admin,tmp_path):
    assert admin.get('/health').json=={'status':'ok'}
    original=system.DB_PATH;system.DB_PATH=str(tmp_path/'not-created.db')
    try:
        response=admin.get('/health')
        assert response.status_code==503
        assert not Path(system.DB_PATH).exists()
    finally:system.DB_PATH=original


def test_session_key_is_persistent_and_safe_with_concurrent_workers(system,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.delenv('SECRET_KEY')
    with ThreadPoolExecutor(max_workers=4) as executor:
        keys=list(executor.map(lambda _:system.session_key(),range(8)))
    assert len(set(keys))==1 and len(keys[0])==64
    assert system.session_key()==keys[0]


def test_unregistered_files_are_reported_but_kept(system):
    con=system.connect();report=audit(con,system.UPLOAD_DIR);con.close()
    assert len(report['unregistered_files'])==2
    assert all(Path(system.UPLOAD_DIR,name).exists() for name in report['unregistered_files'])


def test_revenda_can_create_own_machine_and_os(system,reseller):
    client,rid,cid,mid=reseller
    data=machine_data();data['client_id']=str(cid)
    response=post(client,'/machines/new',**data)
    assert 'Máquina salva com sucesso' in response.get_data(as_text=True)
    con=system.connect();created=con.execute('SELECT * FROM machines WHERE serial_number=?',('NOVO-900',)).fetchone();con.close()
    assert created['client_id']==cid and created['reseller_id']==rid
    response=post(client,f'/clients/{cid}/os/nova',machine_id=created['id'],pending_item='Serviço revenda')
    assert 'Serviço revenda' in response.get_data(as_text=True)


def test_broken_cross_reseller_link_cannot_expose_client_details(system,reseller,admin):
    client,rid,cid,mid=reseller
    con=system.connect();con.execute('UPDATE machines SET client_id=7 WHERE id=?',(mid,));con.commit();con.close()
    assert 'Sebastião' not in client.get(f'/machines/{mid}').get_data(as_text=True)
    assert 'Sebastião' not in client.get('/machines').get_data(as_text=True)
    assert 'Máquina da revenda' not in admin.get('/clients/7/painel').get_data(as_text=True)


def test_machine_owner_transfer_preserves_historical_os_client(system,admin):
    post(admin,'/clients/7/os/nova',machine_id='2',pending_item='Atendimento antes da transferência')
    con=system.connect();row=dict(con.execute('SELECT * FROM machines WHERE id=2').fetchone());oid=con.execute('SELECT MAX(id) FROM service_orders').fetchone()[0];con.close()
    data={k:'' if row[k] is None else str(row[k]) for k in machine_data()};data['client_id']='8'
    response=post(admin,'/machines/2/edit',**data)
    assert 'Máquina salva com sucesso' in response.get_data(as_text=True)
    con=system.connect();order=con.execute('SELECT * FROM service_orders WHERE id=?',(oid,)).fetchone()
    assert order['client_id']==7 and order['machine_id']==2
    assert con.execute('SELECT client_id FROM machines WHERE id=2').fetchone()[0]==8
    con.close()


def test_mobile_access_qr_is_local_and_authenticated(system,admin):
    response=admin.get('/access/qr.svg')
    assert response.status_code==200
    assert response.mimetype=='image/svg+xml'
    assert b'<svg' in response.data and b'<path' in response.data
    assert system.app.test_client().get('/access/qr.svg').status_code==302
    html=admin.get('/').get_data(as_text=True)
    assert '/access/qr.svg' in html
    assert 'api.qrserver.com' not in html


def test_admin_password_is_kept_unless_explicitly_reset(system,monkeypatch):
    from werkzeug.security import check_password_hash
    con=system.connect();before=con.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0];con.close()
    monkeypatch.setenv('ADMIN_PASSWORD','qa-new-password')
    system.init_db()
    con=system.connect();assert con.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0]==before;con.close()
    monkeypatch.setenv('RESET_ADMIN_PASSWORD','true')
    system.init_db()
    con=system.connect();after=con.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0];con.close()
    assert check_password_hash(after,'qa-new-password')


def test_password_reset_without_password_fails_without_touching_current_hash(system,monkeypatch):
    con=system.connect();before=con.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0];con.close()
    monkeypatch.setenv('RESET_ADMIN_PASSWORD','true');monkeypatch.delenv('ADMIN_PASSWORD',raising=False)
    with pytest.raises(RuntimeError,match='ADMIN_PASSWORD'):
        system.init_db()
    con=system.connect();assert con.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0]==before;con.close()

@pytest.mark.parametrize('authenticated',[False,True])
def test_unknown_page_has_readable_404(system,admin,authenticated):
    client=admin if authenticated else system.app.test_client()
    response=client.get('/pagina-que-nao-existe')
    assert response.status_code==404
    assert 'Registro não encontrado' in response.get_data(as_text=True)

@pytest.mark.parametrize('role',['revenda','papel-invalido'])
def test_unassigned_or_unknown_role_does_not_get_global_access(system,role):
    con=system.connect()
    uid=con.execute('INSERT INTO users(email,password_hash,role,reseller_id) VALUES (?,?,?,NULL)',
                    ('unassigned@example.test','not-used',role)).lastrowid
    con.commit();con.close()
    client=system.app.test_client()
    with client.session_transaction() as session:session['user_id']=uid
    response=client.get('/machines')
    assert response.status_code==302 and '/login' in response.location
    with client.session_transaction() as session:assert 'user_id' not in session
