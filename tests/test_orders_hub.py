import re,sqlite3
from pathlib import Path
from urllib.parse import quote
import pytest

CNPJ='45.154.368/0001-42'
PHONE='(32) 9 9988-5977'

def post(client,path,**values):
    return client.post(path,data={'_csrf':'test-csrf',**values},follow_redirects=True)

def test_orders_hub_lists_every_existing_order_including_orphans(admin):
    response=admin.get('/os');assert response.status_code==200
    html=response.get_data(as_text=True)
    for number in range(1,7):assert f'href="/os/{number}"' in html
    assert 'Cliente não encontrado' in html
    assert 'Conferir vínculo' in html
    assert '6 OS encontradas' in html
    assert 'href="/os/6/print"' in html

@pytest.mark.parametrize('query,expected',[
    ('OS #6',[6]),('#0005',[5]),('6',[4,5,6]),('Jose Jarbas',[5,6]),
    ('25030713',[4]),('jfbosbflk',[4]),('zxy-nao-existe',[]),('9'*44,[])
])
def test_orders_search_handles_id_client_serial_notes_and_long_identifiers(admin,query,expected):
    response=admin.get('/os?q='+quote(query));assert response.status_code==200
    html=response.get_data(as_text=True)
    found={int(value) for value in re.findall(r'href="/os/([0-9]+)"',html)}
    assert found==set(expected)


def test_orders_search_includes_service_items(system,admin):
    response=post(admin,'/clients/7/os/nova',machine_id='2',service_date='2026-11-16',pending_item='Substituição da correia QA')
    assert response.status_code==200
    html=admin.get('/os?q='+quote('substituicao da correia QA')).get_data(as_text=True)
    assert 'href="/os/7"' in html
    assert '1 OS encontrada' in html


def test_orders_date_range_uses_service_or_creation_date(admin):
    html=admin.get('/os?date_from=2026-11-06&date_to=2026-11-06').get_data(as_text=True)
    assert 'href="/os/6"' in html and 'href="/os/5"' not in html
    html=admin.get('/os?date_from=2025-11-15&date_to=2025-11-15').get_data(as_text=True)
    assert {int(n) for n in re.findall(r'href="/os/([0-9]+)"',html)}=={1,2,3,4}

@pytest.mark.parametrize('query',['date_from=2026-02-30','date_to=nao-e-data','date_from=20261116','date_from=2026-11-17&date_to=2026-11-16'])
def test_orders_invalid_date_filter_has_clear_error(admin,query):
    response=admin.get('/os?'+query)
    assert response.status_code==400
    assert 'flash error' in response.get_data(as_text=True)


def test_orders_review_filter_preserves_old_unlinked_orders(admin):
    html=admin.get('/os?status=review').get_data(as_text=True)
    assert {int(n) for n in re.findall(r'href="/os/([0-9]+)"',html)}=={1,2,3,4}


def test_orders_pagination_does_not_drop_records_or_filters(system,admin):
    con=system.connect()
    con.executemany('INSERT INTO service_orders(reseller_id,client_id,service_date,obs) VALUES (1,7,?,?)',
                    [('2026-11-16',f'Paginacao QA {i}') for i in range(30)])
    con.commit();con.close()
    first=admin.get('/os?q=Paginacao&date_from=2026-11-16').get_data(as_text=True)
    second=admin.get('/os?q=Paginacao&date_from=2026-11-16&page=2').get_data(as_text=True)
    ids1={int(n) for n in re.findall(r'href="/os/([0-9]+)"',first)}
    ids2={int(n) for n in re.findall(r'href="/os/([0-9]+)"',second)}
    assert len(ids1)==25 and len(ids2)==5 and not ids1.intersection(ids2)
    assert 'q=Paginacao' in first and 'date_from=2026-11-16' in first
    assert 'Página 2 de 2' in second
    assert admin.get('/os?page=-50').status_code==200


def test_orders_reseller_can_only_list_and_search_own_orders(system,reseller,admin):
    client,rid,cid,mid=reseller
    post(client,f'/clients/{cid}/os/nova',machine_id=str(mid),pending_item='Atendimento exclusivo QA',service_date='2026-11-16')
    html=client.get('/os').get_data(as_text=True)
    assert 'href="/os/7"' in html
    assert 'href="/os/5"' not in html and 'href="/os/6"' not in html
    assert 'José Jarbas' not in html and 'Cliente não encontrado' not in html
    assert '1 OS encontrada' in html
    assert 'href="/os/5"' not in client.get('/os?q=OS+%235').get_data(as_text=True)
    assert 'href="/os/7"' in admin.get('/os').get_data(as_text=True)


def test_orders_anonymous_access_requires_login(system):
    response=system.app.test_client().get('/os')
    assert response.status_code==302 and '/login' in response.location


def test_orders_navigation_dashboard_and_client_flow(admin):
    html=admin.get('/').get_data(as_text=True)
    assert html.count('href="/os"')>=3
    html=admin.get('/os/5').get_data(as_text=True)
    assert 'Todas as OS' in html
    # Only the OS sidebar item and OS mobile item are active for this screen.
    assert 'href="/os" class="active"' in html
    assert 'href="/clients" class="active"' not in html
    html=admin.get('/clients?for_os=1').get_data(as_text=True)
    assert 'Selecione o cliente' in html and '/painel#nova-os' in html
    assert 'name="for_os" value="1"' in html
    assert 'id="nova-os"' in admin.get('/clients/7/painel').get_data(as_text=True)

@pytest.mark.parametrize('path',['/','/os','/os/5','/os/5/print','/machines/2/print','/login'])
def test_company_identity_is_in_headers_and_prints(admin,path):
    response=admin.get(path);assert response.status_code==200
    html=response.get_data(as_text=True)
    assert CNPJ in html and PHONE in html
    if path.endswith('/print'):
        assert '00.000.000/0001-00' not in html
        assert '(00) 0000-0000' not in html


def test_company_migration_updates_only_matrix_and_is_idempotent(system,reseller):
    _,rid,_,_=reseller
    con=system.connect();row=con.execute("SELECT cnpj,phone FROM resellers WHERE razao_social='Solutec Matriz'").fetchone()
    assert (row['cnpj'],row['phone'])==(CNPJ,PHONE)
    assert con.execute('SELECT cnpj,phone FROM resellers WHERE id=?',(rid,)).fetchone()['cnpj']==''
    assert con.execute('SELECT COUNT(*) FROM schema_migrations WHERE name=?',(system.COMPANY_MIGRATION,)).fetchone()[0]==1
    con.execute("UPDATE resellers SET phone='Telefone atualizado depois' WHERE razao_social='Solutec Matriz'")
    con.commit();con.close()
    system.init_db()
    con=system.connect();assert con.execute("SELECT phone FROM resellers WHERE razao_social='Solutec Matriz'").fetchone()[0]=='Telefone atualizado depois';con.close()


def test_company_migration_backs_up_existing_database_without_changing_orders(system):
    backups=list((Path(system.DATA_DIR)/'backups').glob('*antes-atualizacao*'))
    assert len(backups)==1
    before=sqlite3.connect(backups[0]);after=system.connect()
    assert before.execute('SELECT id,client_id,machine_id,obs FROM service_orders ORDER BY id').fetchall()==[tuple(r) for r in after.execute('SELECT id,client_id,machine_id,obs FROM service_orders ORDER BY id')]
    assert before.execute("SELECT cnpj FROM resellers WHERE razao_social='Solutec Matriz'").fetchone()[0]!=CNPJ
    assert after.execute("SELECT cnpj FROM resellers WHERE razao_social='Solutec Matriz'").fetchone()[0]==CNPJ
    before.close();after.close()
