"""Conferência não destrutiva e cópias consistentes do cadastro Solutec."""
from collections import defaultdict
from pathlib import Path, PurePosixPath
import datetime
import re
import sqlite3
import unicodedata
import uuid


def normalized(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    return ''.join(ch for ch in value.casefold() if ch.isalnum())


def search_text(value):
    return ''.join(ch for ch in unicodedata.normalize('NFKD', str(value or '')).casefold()
                   if not unicodedata.combining(ch))


def attachment_path(root, filename):
    """Aceita nomes antigos NFC/NFD sem permitir sair da pasta de anexos."""
    rel = PurePosixPath(filename)
    if rel.is_absolute() or len(rel.parts) != 2 or '..' in rel.parts or '\\' in filename:
        return None
    if not re.fullmatch(r'machine_[0-9]+', rel.parts[0]):
        return None
    root = Path(root).resolve()
    folder = root / rel.parts[0]
    if not folder.is_dir() or folder.is_symlink():
        return None
    direct = folder / rel.parts[1]
    candidates = [direct] if direct.is_file() else [
        p for p in folder.iterdir()
        if unicodedata.normalize('NFC', p.name) == unicodedata.normalize('NFC', rel.parts[1])
    ]
    if len(candidates) != 1:
        return None
    path = candidates[0]
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        return None
    return path


def machine_rows(con, reseller_id=None):
    sql = '''SELECT m.*, c.name AS client_name, c.reseller_id AS client_reseller_id,
             c.delivery_location_url, r.razao_social AS reseller_name
             FROM machines m LEFT JOIN clients c ON c.id=m.client_id
             LEFT JOIN resellers r ON r.id=m.reseller_id'''
    params = []
    if reseller_id is not None:
        sql += ' WHERE m.reseller_id=?'
        params.append(reseller_id)
    rows = [dict(r) for r in con.execute(sql + ' ORDER BY m.id DESC', params)]
    groups = defaultdict(list)
    for row in rows:
        row['issues'] = []
        row['duplicate_ids'] = []
        inaccessible = reseller_id is not None and row['client_reseller_id'] != reseller_id
        if inaccessible:
            row['client_name'] = None
            row['delivery_location_url'] = None
        row['owner_missing'] = row['client_name'] is None
        if row['owner_missing']:
            row['issues'].append('Cliente não encontrado')
        elif row['client_reseller_id'] != row['reseller_id']:
            row['issues'].append('Revenda diferente do cliente')
        if row['archived_at']:
            continue
        for field in ('serial_number', 'engine_number'):
            key = normalized(row[field])
            if key:
                groups[field, key].append(row)
    duplicates = []
    for (field, key), matches in groups.items():
        if len(matches) > 1:
            label = 'Série repetida' if field == 'serial_number' else 'Motor repetido'
            duplicates.append({'field': field, 'label': label, 'value': matches[0][field],
                               'machines': matches})
            for row in matches:
                row['issues'].append(label)
                row['duplicate_ids'] += [r['id'] for r in matches if r['id'] != row['id']]
    for row in rows:
        row['duplicate_ids'] = sorted(set(row['duplicate_ids']))
    return rows, duplicates


def audit(con, upload_dir, reseller_id=None):
    machines, duplicates = machine_rows(con, reseller_id)
    where = ' WHERE o.reseller_id=?' if reseller_id is not None else ''
    params = [reseller_id] if reseller_id is not None else []
    orders = []
    for record in con.execute('''SELECT o.*, c.name AS client_name,
             c.reseller_id AS client_reseller_id, m.name AS machine_name,
             m.client_id AS machine_client_id, m.reseller_id AS machine_reseller_id
             FROM service_orders o LEFT JOIN clients c ON c.id=o.client_id
             LEFT JOIN machines m ON m.id=o.machine_id''' + where + ' ORDER BY o.id DESC', params):
        row = dict(record)
        row['issues'] = []
        if row['client_name'] is None:
            row['issues'].append('Cliente não encontrado')
        elif row['client_reseller_id'] != row['reseller_id']:
            row['issues'].append('Revenda diferente do cliente')
        if row['machine_id'] and (row['machine_name'] is None or
                row['machine_client_id'] != row['client_id'] or
                row['machine_reseller_id'] != row['reseller_id']):
            row['issues'].append('Vínculo da máquina precisa de conferência')
        if row['issues']:
            orders.append(row)
    ids = {m['id'] for m in machines}
    attachments = [dict(p) for p in con.execute('SELECT * FROM machine_photos') if p['machine_id'] in ids]
    missing_files = [p for p in attachments if attachment_path(upload_dir, p['filename']) is None]
    registered = {unicodedata.normalize('NFC',p['filename']) for p in attachments}
    unregistered_files = []
    for path in Path(upload_dir).glob('machine_*/*'):
        if not path.is_file() or path.is_symlink():
            continue
        match = re.fullmatch(r'machine_([0-9]+)',path.parent.name)
        if match and int(match[1]) in ids:
            relative = path.relative_to(upload_dir).as_posix()
            if unicodedata.normalize('NFC',relative) not in registered:
                unregistered_files.append(relative)
    active = [m for m in machines if not m['archived_at']]
    return {'machines': machines, 'active': active, 'duplicates': duplicates,
            'orphan_machines': [m for m in active if m['owner_missing']],
            'review_machines': [m for m in active if m['issues']],
            'orphan_orders': orders, 'missing_files': missing_files,
            'attachment_count': len(attachments), 'unregistered_files': sorted(unregistered_files)}


def snapshot(db_path, directory, reason):
    """sqlite.backup inclui páginas ainda no WAL; nenhuma cópia do .db aberto."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    name = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + reason + '-' + uuid.uuid4().hex[:8] + '.db'
    path = folder / name
    source = sqlite3.connect(db_path, timeout=30)
    target = sqlite3.connect(path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return path
