from io import BytesIO
from pathlib import Path
import base64,re,sqlite3
import pytest

TOKEN={'_csrf':'test-csrf'}
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+c5j8AAAAASUVORK5CYII=')

def machine(system,mid):
    con=system.connect();row=dict(con.execute('SELECT * FROM machines WHERE id=?',(mid,)).fetchone());con.close();return row

def add_photo(system,mid,name='own.png',exists=True):
    filename=f'machine_{mid}/'+name
    if exists:
        path=Path(system.UPLOAD_DIR)/filename;path.parent.mkdir(exist_ok=True);path.write_bytes(PNG)
    con=system.connect();pid=con.execute('INSERT INTO machine_photos(machine_id,filename) VALUES (?,?)',(mid,filename)).lastrowid;con.commit();con.close()
    return pid,filename

def choose(client,mid,choice):
    return client.post(f'/machines/{mid}/cover',data={**TOKEN,'cover_choice':choice})

def test_default_references_appear_on_cards_without_changing_machine_identity(system,admin):
    con=system.connect();before=[dict(row) for row in con.execute('SELECT * FROM machines ORDER BY id')];con.close()
    html=admin.get('/machines').get_data(as_text=True)
    assert html.count('class="equipment-cover-photo"')==21
    assert 'Foto de referência' in html and '/static/solutec/tractor-trailer.webp' in html
    assert '/machines/1/cover' in html and '25030713' in html
    con=system.connect();after=[dict(row) for row in con.execute('SELECT * FROM machines ORDER BY id')];con.close()
    assert before==after and all(row['cover_image'] is None for row in after)

@pytest.mark.parametrize('choice',['reference:trailer','reference:yard','reference:detail','reference:loader','none','auto'])
def test_cover_choice_is_persistent_and_changes_only_presentation(system,admin,choice):
    before=machine(system,2)
    assert choose(admin,2,choice).status_code==302
    after=machine(system,2)
    assert after=={**before,'cover_image':None if choice=='auto' else choice}
    system.init_db();assert machine(system,2)==after
    html=admin.get('/machines/2/cover').get_data(as_text=True)
    assert f'value="{choice}" checked' in html

def test_cover_picker_uses_photo_attached_to_its_machine_and_can_revert(system,admin):
    pid,filename=add_photo(system,2)
    assert filename in admin.get('/machines/2/cover').get_data(as_text=True)
    assert choose(admin,2,'photo:'+str(pid)).status_code==302
    html=admin.get('/machines?q=OS-nonexistent').get_data(as_text=True)
    assert filename not in html
    html=admin.get('/machines?q=25030713').get_data(as_text=True)
    assert filename in html and 'Foto da máquina' in html
    assert choose(admin,2,'none').status_code==302
    # A ficha #1 possui a mesma série, mas mantém sua referência independente.
    assert filename not in admin.get('/machines?q=25030713').get_data(as_text=True)
    assert choose(admin,2,'auto').status_code==302
    assert filename in admin.get('/machines?q=25030713').get_data(as_text=True)

def test_automatic_cover_uses_latest_available_image_and_skips_pdf_or_missing_file(system,admin):
    _,first=add_photo(system,2,'first.png')
    _,latest=add_photo(system,2,'latest.png')
    add_photo(system,2,'missing.png',exists=False)
    html=admin.get('/machines?q=25030713').get_data(as_text=True)
    assert latest in html and first not in html and 'missing.png' not in html
    picker=admin.get('/machines/2/cover').get_data(as_text=True)
    assert 'missing.png' not in picker and '.pdf"' not in picker

@pytest.mark.parametrize('choice',['photo:999999','reference:other','../../solutec.db','https://invalid.example/image.png',''])
def test_invalid_choices_are_rejected_without_changing_cover(system,admin,choice):
    before=machine(system,2)
    assert choose(admin,2,choice).status_code==400
    assert machine(system,2)==before

def test_photo_of_other_machine_cannot_be_selected_even_by_admin(system,admin):
    pid,_=add_photo(system,1)
    assert choose(admin,2,'photo:'+str(pid)).status_code==400
    assert machine(system,2)['cover_image'] is None

def test_reseller_cannot_select_or_read_other_reseller_cover_photos(system,admin,reseller):
    client,_,_,mid=reseller
    pid,filename=add_photo(system,2)
    assert client.get('/machines/2/cover').status_code==403
    assert choose(client,2,'reference:loader').status_code==403
    assert filename not in client.get(f'/machines/{mid}/cover').get_data(as_text=True)
    assert choose(client,mid,'photo:'+str(pid)).status_code==400
    assert choose(client,mid,'reference:loader').status_code==302
    assert machine(system,mid)['cover_image']=='reference:loader'
    assert filename not in client.get('/machines').get_data(as_text=True)

def test_cover_changes_require_authentication_and_csrf(system,admin):
    assert system.app.test_client().get('/machines/2/cover').status_code==302
    assert admin.post('/machines/2/cover',data={'cover_choice':'reference:loader'}).status_code==400
    assert machine(system,2)['cover_image'] is None

def test_removing_selected_attachment_resets_cover_and_preserves_original(system,admin):
    pid,filename=add_photo(system,2)
    choose(admin,2,'photo:'+str(pid))
    assert admin.post(f'/machines/2/photos/{pid}/delete',data=TOKEN).status_code==302
    assert machine(system,2)['cover_image'] is None
    assert (Path(system.UPLOAD_DIR)/filename).is_file()
    assert filename not in admin.get('/machines?q=25030713').get_data(as_text=True)

def test_cover_migration_backs_up_legacy_data_and_keeps_every_record(system):
    con=system.connect();assert con.execute('SELECT COUNT(*) FROM machines').fetchone()[0]==21;con.close()
    copies=list((Path(system.DATA_DIR)/'backups').glob('*antes-atualizacao*'))
    assert len(copies)==1
    before=sqlite3.connect(copies[0]);assert 'cover_image' not in {r[1] for r in before.execute('PRAGMA table_info(machines)')};before.close()
    system.init_db()
    assert len(list((Path(system.DATA_DIR)/'backups').glob('*antes-atualizacao*')))==1
