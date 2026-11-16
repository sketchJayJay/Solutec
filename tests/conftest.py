from pathlib import Path
import os,sys,tempfile,shutil
import pytest

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
IMPORT_DATA=tempfile.TemporaryDirectory(prefix='solutec-test-import-')
os.environ['SOLUTEC_DATA_DIR']=IMPORT_DATA.name
os.environ['COOKIE_SECURE']='false'
os.environ['SECRET_KEY']='automated-tests-only-not-production'
import app as module

@pytest.fixture
def system(tmp_path,monkeypatch):
    data=tmp_path/'data';data.mkdir()
    shutil.copy2(PROJECT/'seed'/'solutec.db',data/'solutec.db')
    shutil.copytree(PROJECT/'seed'/'uploads',data/'uploads')
    monkeypatch.setattr(module,'DB_PATH',str(data/'solutec.db'))
    monkeypatch.setattr(module,'DATA_DIR',str(data))
    monkeypatch.setattr(module,'UPLOAD_DIR',str(data/'uploads'))
    monkeypatch.delenv('RESET_ADMIN_PASSWORD',raising=False)
    module.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
    module.init_db()
    yield module
    shutil.rmtree(data,ignore_errors=True)

@pytest.fixture
def admin(system):
    c=system.app.test_client()
    with c.session_transaction() as session:
        session['user_id']=1;session['_csrf']='test-csrf'
    return c

@pytest.fixture
def reseller(system):
    from werkzeug.security import generate_password_hash
    con=system.connect()
    rid=con.execute("INSERT INTO resellers(razao_social,cnpj,inscr_social,responsavel,phone,email,address_street,address_number,address_city,address_state,address_zip) VALUES ('Revenda de testes','','','','','','','','','','')").lastrowid
    uid=con.execute('INSERT INTO users(email,password_hash,role,reseller_id) VALUES (?,?,?,?)',
                    ('revenda@example.test',generate_password_hash('test-only-password'),'revenda',rid)).lastrowid
    cid=con.execute('INSERT INTO clients(name,reseller_id) VALUES (?,?)',('Cliente da revenda',rid)).lastrowid
    mid=con.execute('INSERT INTO machines(name,reseller_id,client_id,serial_number) VALUES (?,?,?,?)',
                    ('Máquina da revenda',rid,cid,'TEST-REVENDA-001')).lastrowid
    con.commit();con.close()
    c=system.app.test_client()
    with c.session_transaction() as session:
        session['user_id']=uid;session['_csrf']='test-csrf'
    return c,rid,cid,mid
