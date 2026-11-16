from flask import Flask, render_template, request, redirect, url_for, flash, session, g, send_from_directory, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import sqlite3, os, datetime, urllib.parse, re
import secrets, hmac, math, uuid, tempfile, zipfile, json
from pathlib import Path
from maintenance import audit, machine_rows, normalized, search_text, attachment_path, snapshot

BASEDIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get("SOLUTEC_DATA_DIR", os.path.join(BASEDIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "solutec.db")

UPLOAD_DIR = os.environ.get("SOLUTEC_UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Em implantação nova, preserva o banco e os anexos que vieram no pacote.
SEED_DB = os.path.join(BASEDIR, "seed", "solutec.db")
if not os.path.exists(DB_PATH) and os.path.isfile(SEED_DB):
    import shutil
    shutil.copy2(SEED_DB, DB_PATH)
SEED_UPLOADS = os.path.join(BASEDIR, "seed", "uploads")
if os.path.isdir(SEED_UPLOADS) and not os.listdir(UPLOAD_DIR):
    import shutil
    shutil.copytree(SEED_UPLOADS, UPLOAD_DIR, dirs_exist_ok=True)

app = Flask(__name__)
# Uma chave local persistente evita sessões previsíveis quando o ambiente não a definiu.
def session_key():
    configured = os.environ.get("SECRET_KEY", "").strip()
    if configured and configured != "CHANGE-ME-IN-COOLIFY":
        return configured
    path = Path(DATA_DIR) / ".session-key"
    if path.exists():
        return path.read_text().strip()
    # Publicação atômica: dois workers nunca leem uma chave parcialmente escrita.
    temporary = Path(DATA_DIR) / (".session-key-" + secrets.token_hex(8))
    key = secrets.token_hex(32)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as file:
            file.write(key)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        temporary.unlink(missing_ok=True)
    return path.read_text().strip()

app.secret_key = session_key()
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true").lower() == "true",
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
)

@app.context_processor
def inject_network_info():
    # Usa o domínio público encaminhado pelo proxy do Coolify.
    return {"base_url": request.host_url.rstrip("/")}


def build_maps_url(raw):
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    q = urllib.parse.quote_plus(raw)
    return f"https://www.google.com/maps/search/?api=1&query={q}"



def normalize_phone(raw_phone):
    digits = re.sub(r"\D+", "", str(raw_phone or "")).lstrip("0")
    if len(digits) in (10, 11):
        return "55" + digits
    if len(digits) in (12, 13) and digits.startswith("55"):
        return digits
    return None


def whatsapp_url(phone, name=None, text=None):
    """Monta link direto para WhatsApp do número informado (com mensagem opcional)."""
    p = normalize_phone(phone)
    if not p:
        return None
    if text is None:
        text = f"Olá {name}, tudo bem? Aqui é da Solutec." if name else "Olá! Aqui é da Solutec."
    return f"https://wa.me/{p}?text={urllib.parse.quote_plus(text)}"


def whatsapp_share_url(text):
    """Link de compartilhamento (sem número) para escolher o contato no WhatsApp."""
    if text is None:
        text = ""
    return f"https://wa.me/?text={urllib.parse.quote_plus(text)}"
@app.context_processor
def inject_helpers():
    return dict(build_maps_url=build_maps_url, whatsapp_url=whatsapp_url, whatsapp_share_url=whatsapp_share_url)


# ---------- DB helpers ----------

def connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA journal_mode=WAL")
    con.create_function("fold", 1, search_text, deterministic=True)
    return con


def init_db():
    if os.path.isfile(DB_PATH):
        probe = sqlite3.connect(DB_PATH)
        columns = {r[1] for r in probe.execute("PRAGMA table_info(machines)")}
        probe.close()
        if columns and not {"obs", "archived_at", "archive_reason"}.issubset(columns):
            snapshot(DB_PATH, os.path.join(DATA_DIR, "backups"), "antes-atualizacao")
    con = connect()
    cur = con.cursor()
    cur.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS resellers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        razao_social TEXT NOT NULL,
        fantasy_name TEXT,
        cnpj TEXT,
        inscr_social TEXT,
        responsavel TEXT,
        phone TEXT,
        email TEXT,
        address_street TEXT,
        address_number TEXT,
        address_city TEXT,
        address_state TEXT,
        address_zip TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL, -- 'admin' or 'revenda'
        reseller_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS clients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reseller_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        cpf TEXT,
        rg TEXT,
        phone TEXT,
        billing_address TEXT,
        delivery_address TEXT,
        delivery_location_url TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS machines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reseller_id INTEGER NOT NULL,
        client_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        brand TEXT,
        model TEXT,
        motor_model TEXT,
        nf_number TEXT,
        serial_number TEXT,
        engine_number TEXT,
        delivery_date TEXT,
        initial_hours REAL,
        obs TEXT,
        archived_at TEXT,
        archive_reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS machine_photos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        machine_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS service_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reseller_id INTEGER NOT NULL,
        client_id INTEGER NOT NULL,
        machine_id INTEGER,
        service_date TEXT,
        address TEXT,
        maps_url TEXT,
        obs TEXT,
        archived_at TEXT,
        archive_reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
        FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS service_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        item_text TEXT NOT NULL,
        FOREIGN KEY (order_id) REFERENCES service_orders(id) ON DELETE CASCADE
    );
    """)

    # Migrações aditivas: não altera nem exclui os cadastros legados.
    columns = {r["name"] for r in cur.execute("PRAGMA table_info(machines)")}
    for name, kind in (("obs", "TEXT"), ("archived_at", "TEXT"), ("archive_reason", "TEXT")):
        if name not in columns:
            cur.execute(f"ALTER TABLE machines ADD COLUMN {name} {kind}")
    if "obs_text" in columns:
        cur.execute("UPDATE machines SET obs=obs_text WHERE obs IS NULL AND obs_text IS NOT NULL")
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS maintenance_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            action TEXT NOT NULL, record_id INTEGER, details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_machines_client ON machines(client_id);
        CREATE INDEX IF NOT EXISTS idx_machines_reseller ON machines(reseller_id);
        CREATE INDEX IF NOT EXISTS idx_clients_reseller ON clients(reseller_id);
        CREATE INDEX IF NOT EXISTS idx_orders_client ON service_orders(client_id);
        CREATE INDEX IF NOT EXISTS idx_photos_machine ON machine_photos(machine_id);
    """)

    # --- Migração leve: adiciona coluna phone em clients (caso o banco seja antigo)
    try:
        cols = [r["name"] for r in cur.execute("PRAGMA table_info(clients)").fetchall()]
        if "phone" not in cols:
            cur.execute("ALTER TABLE clients ADD COLUMN phone TEXT")
    except Exception:
        pass


    # Garante coluna Nome Fantasia em bancos antigos
    try:
        cur.execute("ALTER TABLE resellers ADD COLUMN fantasy_name TEXT")
    except Exception:
        pass

    # Ensure admin reseller + user com login oficial Solutec
    admin_email = os.environ.get("ADMIN_EMAIL", "solutec.divinomg@gmail.com").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    # Matriz Solutec
    cur.execute("SELECT id FROM resellers WHERE razao_social = ?", ("Solutec Matriz",))
    row = cur.fetchone()
    if row:
        matriz_id = row["id"]
        # garante que o e-mail cadastrado da matriz é o mesmo do admin
        cur.execute("UPDATE resellers SET email = ? WHERE id = ?", (admin_email, matriz_id))
    else:
        cur.execute("""
            INSERT INTO resellers(razao_social, cnpj, inscr_social, responsavel, phone, email, 
                                  address_street, address_number, address_city, address_state, address_zip)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            "Solutec Matriz", "00.000.000/0001-00", "ISENTO", "Responsável Matriz",
            "(00) 0000-0000", admin_email,
            "Rua Exemplo", "100", "Cidade", "UF", "00000-000"
        ))
        matriz_id = cur.lastrowid

    # Admin da matriz (vê tudo)
    cur.execute("SELECT id FROM users WHERE reseller_id = ? AND role = 'admin'", (matriz_id,))
    u = cur.fetchone()
    if u:
        # Permite uma redefinição explícita e pontual pelo ambiente do Coolify.
        if os.environ.get("RESET_ADMIN_PASSWORD", "false").lower() == "true":
            if not admin_password:
                con.close()
                raise RuntimeError("Defina ADMIN_PASSWORD para redefinir a senha do administrador.")
            cur.execute(
                "UPDATE users SET email = ?, password_hash = ? WHERE id = ?",
                (admin_email, generate_password_hash(admin_password), u["id"])
            )
    else:
        if not admin_password:
            con.close()
            raise RuntimeError("Defina ADMIN_PASSWORD na primeira inicialização de um banco vazio.")
        cur.execute("""
            INSERT INTO users(email, password_hash, role, reseller_id)
            VALUES (?,?,?,?)
        """, (admin_email, generate_password_hash(admin_password), "admin", matriz_id))

    con.commit()
    con.close()


# ---------- Auth helpers ----------

@app.before_request
def load_user():
    g.user = None
    if request.endpoint in ("health", "static"):
        return
    user_id = session.get("user_id")
    if user_id:
        con = connect()
        cur = con.cursor()
        cur.execute("""            SELECT u.*,
                   r.razao_social AS reseller_razao,
                   r.fantasy_name AS reseller_fantasy
            FROM users u
            LEFT JOIN resellers r ON r.id = u.reseller_id
            WHERE u.id = ?
        """, (user_id,))
        row = cur.fetchone()
        con.close()
        if row and row['role'] in ('admin','revenda') and (row['role']=='admin' or (row['reseller_id'] is not None and row['reseller_razao'] is not None)):
            g.user = row
        else:
            session.clear()


def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin":
            flash("Acesso permitido apenas para a matriz.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/health")
def health():
    try:
        con=sqlite3.connect(Path(DB_PATH).resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
        con.execute('SELECT id FROM machines LIMIT 1')
        con.close()
        return {"status":"ok"},200
    except sqlite3.Error:
        return {"status":"unavailable"},503


# ---------- Routes ----------

@app.route("/")
@login_required
def dashboard():
    con = connect()
    report = audit(con, UPLOAD_DIR, scope_id())
    where, params = (" WHERE reseller_id=?", [scope_id()]) if scope_id() is not None else ("", [])
    total_clients = con.execute("SELECT COUNT(*) FROM clients" + where, params).fetchone()[0]
    total_orders = con.execute("SELECT COUNT(*) FROM service_orders" + where, params).fetchone()[0]
    total_resellers = con.execute("SELECT COUNT(*) FROM resellers").fetchone()[0] if g.user['role']=='admin' else None
    con.close()
    return render_template("dashboard.html", total_machines=len(report['active']),
        total_clients=total_clients, total_orders=total_orders, total_resellers=total_resellers,
        last_machines=report['active'][:5], report=report,
        first_run=not total_clients and not report['active'])


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        con = connect()
        user = con.execute("SELECT * FROM users WHERE lower(email)=?", (request.form.get("email", "").strip().lower(),)).fetchone()
        con.close()
        if not user or not check_password_hash(user["password_hash"], request.form.get("password", "")):
            flash("E-mail ou senha incorretos.", "error")
            return render_template("login.html"), 401
        session.clear()
        session['user_id'] = user['id']
        candidate = request.args.get('next', '')
        parsed = urllib.parse.urlsplit(candidate)
        next_url = candidate if candidate.startswith('/') and not candidate.startswith('//') and not parsed.netloc and not parsed.scheme and '\\' not in candidate else url_for('dashboard')
        return redirect(next_url)
    return render_template("login.html")



@app.route("/revenda/cadastro", methods=["GET", "POST"])
def revenda_signup():
    """Cadastro público de novas revendas."""
    if g.user:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        razao_social = request.form.get("razao_social","").strip()
        fantasy_name = request.form.get("fantasy_name","").strip()
        cnpj = request.form.get("cnpj","").strip()
        inscr = request.form.get("inscr_social","").strip()
        responsavel = request.form.get("responsavel","").strip()
        phone = request.form.get("phone","").strip()
        email = request.form.get("email","").strip()
        street = request.form.get("address_street","").strip()
        number = request.form.get("address_number","").strip()
        city = request.form.get("address_city","").strip()
        uf = request.form.get("address_state","").strip()
        cep = request.form.get("address_zip","").strip()
        login_email = request.form.get("login_email","").strip().lower()
        login_password = request.form.get("login_password","")

        if not razao_social or not login_email or not login_password:
            flash("Razão social, e-mail de login e senha são obrigatórios.", "error")
            return render_template("revenda_signup.html")

        con = connect()
        cur = con.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (login_email,))
        if cur.fetchone():
            con.close()
            flash("Já existe um usuário com este e-mail. Tente outro ou faça login.", "error")
            return render_template("revenda_signup.html")

        cur.execute("""
            INSERT INTO resellers(razao_social, fantasy_name, cnpj, inscr_social, responsavel, phone, email,
                                  address_street, address_number, address_city, address_state, address_zip)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (razao_social, fantasy_name, cnpj, inscr, responsavel, phone, email,
              street, number, city, uf, cep))
        reseller_id = cur.lastrowid

        cur.execute("""
            INSERT INTO users(email, password_hash, role, reseller_id)
            VALUES (?,?,?,?)
        """, (login_email, generate_password_hash(login_password), "revenda", reseller_id))
        con.commit()
        con.close()
        flash("Revenda cadastrada com sucesso! Agora é só fazer login.", "success")
        return redirect(url_for("login"))

    return render_template("revenda_signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada.", "success")
    return redirect(url_for("login"))


# ---------- Resellers (matriz) ----------

@app.route("/resellers", methods=["GET", "POST"])
@admin_required
def resellers():
    con = connect()
    cur = con.cursor()
    if request.method == "POST":
        razao_social = request.form.get("razao_social","").strip()
        fantasy_name = request.form.get("fantasy_name","").strip()
        cnpj = request.form.get("cnpj","").strip()
        inscr = request.form.get("inscr_social","").strip()
        responsavel = request.form.get("responsavel","").strip()
        phone = request.form.get("phone","").strip()
        email = request.form.get("email","").strip()
        street = request.form.get("address_street","").strip()
        number = request.form.get("address_number","").strip()
        city = request.form.get("address_city","").strip()
        uf = request.form.get("address_state","").strip()
        cep = request.form.get("address_zip","").strip()
        login_email = request.form.get("login_email","").strip().lower()
        login_password = request.form.get("login_password","")

        if not razao_social or not login_email or not login_password:
            flash("Razão social, e-mail de login e senha são obrigatórios.", "error")
        else:
            cur.execute("SELECT id FROM users WHERE email = ?", (login_email,))
            if cur.fetchone():
                flash("Já existe um usuário com este e-mail. Tente outro.", "error")
            else:
                cur.execute("""
                    INSERT INTO resellers(razao_social, fantasy_name, cnpj, inscr_social, responsavel, phone, email,
                                          address_street, address_number, address_city, address_state, address_zip)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (razao_social, fantasy_name, cnpj, inscr, responsavel, phone, email,
                      street, number, city, uf, cep))
                reseller_id = cur.lastrowid
                cur.execute("""
                    INSERT INTO users(email, password_hash, role, reseller_id)
                    VALUES (?,?,?,?)
                """, (login_email, generate_password_hash(login_password), "revenda", reseller_id))
                con.commit()
                flash("Revenda criada com sucesso.", "success")

    cur.execute("""
        SELECT r.*, 
               (SELECT COUNT(*) FROM clients c WHERE c.reseller_id = r.id) as total_clients,
               (SELECT COUNT(*) FROM machines m WHERE m.reseller_id = r.id) as total_machines
        FROM resellers r
        ORDER BY r.razao_social
    """)
    rows = cur.fetchall()
    con.close()
    return render_template("resellers.html", rows=rows)



# ---------- Clients ----------

@app.route("/clients")
@login_required
def clients_list():
    q = request.args.get('q', '').strip()
    con = connect()
    clauses, params = [], []
    if scope_id() is not None:
        clauses.append('c.reseller_id=?'); params.append(scope_id())
    if q:
        clauses.append('(fold(c.name) LIKE ? OR fold(c.cpf) LIKE ? OR fold(c.phone) LIKE ? OR fold(c.delivery_address) LIKE ?)')
        params.extend(['%' + search_text(q) + '%']*4)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    rows = con.execute('SELECT c.*,r.razao_social reseller_name,\n        (SELECT COUNT(*) FROM machines m WHERE m.client_id=c.id AND m.archived_at IS NULL) machine_count\n        FROM clients c LEFT JOIN resellers r ON r.id=c.reseller_id' + where + ' ORDER BY fold(c.name),c.id', params).fetchall()
    con.close()
    return render_template('clients_list.html', rows=rows, q=q)



@app.route("/clients/new", methods=["GET", "POST"])
@login_required
def client_new():
    return save_client()




@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def client_edit(client_id):
    return save_client(client_id)


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def client_delete(client_id):
    con = connect()
    client = con.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    if not client:
        con.close(); abort(404)
    if not permitted(client):
        con.close(); abort(403)
    snapshot(DB_PATH, Path(DATA_DIR)/'backups', 'antes-excluir-cliente')
    # Bancos antigos podem não declarar CASCADE. Remove dependências explicitamente.
    mids = [r[0] for r in con.execute('SELECT id FROM machines WHERE client_id=?', (client_id,))]
    oids = [r[0] for r in con.execute('SELECT id FROM service_orders WHERE client_id=?', (client_id,))]
    for mid in mids:
        con.execute('UPDATE service_orders SET machine_id=NULL WHERE machine_id=? AND client_id!=?', (mid,client_id))
        con.execute('DELETE FROM machine_photos WHERE machine_id=?', (mid,))
    for oid in oids:
        con.execute('DELETE FROM service_items WHERE order_id=?', (oid,))
    con.execute('DELETE FROM service_orders WHERE client_id=?', (client_id,))
    con.execute('DELETE FROM machines WHERE client_id=?', (client_id,))
    con.execute('DELETE FROM clients WHERE id=?', (client_id,))
    record_event(con, 'excluir_cliente', client_id, {'name':client['name'], 'machines':mids, 'orders':oids})
    con.commit(); con.close()
    flash('Cliente e vínculos excluídos. Uma cópia anterior foi guardada; os arquivos foram preservados.', 'success')
    return redirect(url_for('clients_list'))




# ---------- Machines ----------

@app.route("/machines")
@login_required
def machines_list():
    con = connect()
    rows, duplicates = machine_rows(con, scope_id())
    con.close()
    q = request.args.get('q', '').strip()
    status = request.args.get('status', 'active')
    counts = {'active':sum(not r['archived_at'] for r in rows),
              'review':sum(bool(r['issues']) and not r['archived_at'] for r in rows),
              'archived':sum(bool(r['archived_at']) for r in rows),
              'orphan':sum(r['owner_missing'] and not r['archived_at'] for r in rows)}
    if status == 'archived': rows = [r for r in rows if r['archived_at']]
    else:
        rows = [r for r in rows if not r['archived_at']]
        if status == 'review': rows = [r for r in rows if r['issues']]
        elif status == 'orphan': rows = [r for r in rows if r['owner_missing']]
    if q:
        query = search_text(q)
        rows = [r for r in rows if query in search_text(' '.join(str(r.get(k) or '') for k in ('id','name','brand','model','client_name','serial_number','engine_number','nf_number','reseller_name')))]
    return render_template('machines_list.html', rows=rows, q=q, status=status, counts=counts)


@app.route("/machines/new", methods=["GET", "POST"])
@login_required
def machine_new():
    return save_machine()



@app.route("/machines/<int:machine_id>/edit", methods=["GET", "POST"])
@login_required
def machine_edit(machine_id):
    return save_machine(machine_id)


@app.route("/machines/<int:machine_id>", methods=["GET", "POST"])
@login_required
def machine_detail(machine_id):
    con = connect()
    m = get_machine(con, machine_id)
    if request.method == 'POST':
        files = [f for f in request.files.getlist('photos') if f and f.filename]
        prepared = []
        try:
            if len(files) > 10:
                raise ValueError('Selecione até 10 arquivos por envio.')
            for f in files:
                ext = Path(f.filename).suffix.lower()
                header = f.stream.read(32); f.stream.seek(0)
                valid = ((ext=='.pdf' and header.startswith(b'%PDF-')) or
                    (ext in ('.jpg','.jpeg') and header.startswith(b'\xff\xd8\xff')) or
                    (ext=='.png' and header.startswith(b'\x89PNG\r\n\x1a\n')) or
                    (ext=='.gif' and header.startswith((b'GIF87a',b'GIF89a'))) or
                    (ext=='.webp' and header[:4]==b'RIFF' and header[8:12]==b'WEBP') or
                    (ext in ('.heic','.heif') and header[4:8]==b'ftyp'))
                if not valid:
                    raise ValueError('Formato inválido. Envie PDF ou imagem JPG, PNG, GIF, WebP ou HEIC.')
                from werkzeug.utils import secure_filename
                name = secure_filename(f.filename) or ('anexo' + ext)
                relative = f'machine_{machine_id}/{uuid.uuid4().hex}_{name}'
                full = Path(UPLOAD_DIR)/relative
                full.parent.mkdir(parents=True, exist_ok=True)
                prepared.append((f, relative, full))
            written = []
            try:
                for f, relative, full in prepared:
                    written.append(full)
                    f.save(full)
                    con.execute('INSERT INTO machine_photos(machine_id,filename) VALUES (?,?)', (machine_id,relative))
                con.execute('UPDATE machines SET obs=? WHERE id=?', (request.form.get('obs_text',''),machine_id))
                con.commit()
            except Exception:
                con.rollback()
                for path in written: path.unlink(missing_ok=True)
                raise
        except ValueError as error:
            con.close()
            flash(str(error), 'error')
            return redirect(url_for('machine_detail',machine_id=machine_id))
        con.close()
        flash('Observações e anexos salvos.', 'success')
        return redirect(url_for('machine_detail',machine_id=machine_id))
    photos = []
    for row in con.execute('SELECT * FROM machine_photos WHERE machine_id=? ORDER BY id DESC', (machine_id,)):
        photo = dict(row)
        photo['missing'] = attachment_path(UPLOAD_DIR,photo['filename']) is None
        photo['is_image'] = Path(photo['filename']).suffix.lower() in ('.jpg','.jpeg','.png','.gif','.webp')
        photo['display_name'] = re.sub(r'^(?:[0-9a-f]{32}|[0-9]{14})_', '', Path(photo['filename']).name)
        photos.append(photo)
    rows, _ = machine_rows(con,scope_id())
    quality = next(r for r in rows if r['id']==machine_id)
    candidates = [r for r in rows if r['id'] in quality['duplicate_ids']]
    con.close()
    return render_template('machine_detail.html',m=m,photos=photos,quality=quality,candidates=candidates)




@app.route("/machines/<int:machine_id>/photos/<int:photo_id>/delete", methods=["POST"])
@login_required
def machine_photo_delete(machine_id,photo_id):
    con = connect()
    get_machine(con,machine_id)
    photo=con.execute('SELECT * FROM machine_photos WHERE id=? AND machine_id=?',(photo_id,machine_id)).fetchone()
    if not photo:
        con.close(); abort(404)
    snapshot(DB_PATH,Path(DATA_DIR)/'backups','antes-remover-anexo')
    con.execute('DELETE FROM machine_photos WHERE id=?',(photo_id,))
    record_event(con,'remover_anexo',photo_id,{'filename':photo['filename'],'machine_id':machine_id})
    con.commit(); con.close()
    # Mantém o arquivo no backup e no disco para uma eventual restauração.
    flash('Anexo removido da ficha. O arquivo original foi preservado para recuperação.', 'success')
    return redirect(url_for('machine_detail',machine_id=machine_id))
@app.route("/machines/<int:machine_id>/print")
@login_required
def machine_print(machine_id):
    con=connect()
    m=get_machine(con,machine_id)
    con.close()
    return render_template('machine_print.html',m=m)


# ---------- Painel do cliente e Ordens de Serviço ----------

@app.route("/clients/<int:client_id>")
@login_required
def client_detail_redirect(client_id):
    """Redireciona /clients/<id> para o painel do cliente."""
    return redirect(url_for("client_panel", client_id=client_id))


@app.route("/clients/<int:client_id>/painel")
@login_required
def client_panel(client_id):
    """Painel do cliente: dados, máquinas e OS vinculadas."""
    con = connect()
    cur = con.cursor()

    cur.execute("""
        SELECT c.*, r.razao_social as reseller_name
        FROM clients c
        JOIN resellers r ON r.id = c.reseller_id
        WHERE c.id = ?
    """, (client_id,))
    client = cur.fetchone()
    if not client:
        con.close()
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("clients_list"))

    # Permissão para revenda ver apenas seus clientes
    if g.user["role"] == "revenda" and client["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Acesso não permitido para este cliente.", "error")
        return redirect(url_for("clients_list"))

    # Máquinas deste cliente
    cur.execute("""
        SELECT m.*
        FROM machines m
        WHERE m.client_id = ? AND m.reseller_id = ? AND m.archived_at IS NULL
        ORDER BY m.id DESC
    """, (client_id, client["reseller_id"]))
    machines = cur.fetchall()

    # Últimas OS deste cliente
    cur.execute("""
        SELECT o.*, m.name AS machine_name
        FROM service_orders o
        LEFT JOIN machines m ON m.id = o.machine_id
        WHERE o.client_id = ? AND o.reseller_id = ?
        ORDER BY o.id DESC
        LIMIT 50
    """, (client_id, client["reseller_id"]))
    orders = cur.fetchall()

    con.close()
    return render_template("client_panel.html", client=client, machines=machines, orders=orders)


@app.route("/clients/<int:client_id>/os/nova", methods=["POST"])
@login_required
def client_os_new(client_id):
    con=connect()
    client=con.execute('SELECT * FROM clients WHERE id=?',(client_id,)).fetchone()
    if not client:
        con.close(); abort(404)
    if not permitted(client):
        con.close(); abort(403)
    machine_id=request.form.get('machine_id','').strip() or None
    if machine_id:
        machine=con.execute('SELECT * FROM machines WHERE id=?',(machine_id,)).fetchone()
        if not machine or machine['client_id']!=client_id or machine['reseller_id']!=client['reseller_id'] or machine['archived_at']:
            con.close()
            flash('A máquina selecionada não pertence a este cliente ou está arquivada.', 'error')
            return redirect(url_for('client_panel',client_id=client_id))
    service_date=request.form.get('service_date','').strip()
    if service_date:
        try: datetime.date.fromisoformat(service_date)
        except ValueError:
            con.close(); flash('Informe uma data de serviço válida.', 'error')
            return redirect(url_for('client_panel',client_id=client_id))
    values=[request.form.get(k,'').strip() for k in ('address','maps_url','obs')]
    order_id=con.execute('INSERT INTO service_orders(reseller_id,client_id,machine_id,service_date,address,maps_url,obs) VALUES (?,?,?,?,?,?,?)',
        (client['reseller_id'],client_id,machine_id,service_date,*values)).lastrowid
    items=request.form.getlist('items[]')
    # Inclui também o último item digitado mesmo sem clicar em Adicionar.
    items.append(request.form.get('pending_item',''))
    for text in items:
        if text.strip(): con.execute('INSERT INTO service_items(order_id,item_text) VALUES (?,?)',(order_id,text.strip()))
    con.commit(); con.close()
    flash('Ordem de serviço criada.', 'success')
    return redirect(url_for('service_order_detail',order_id=order_id))


@app.route("/os/<int:order_id>")
@login_required
def service_order_detail(order_id):
    return show_order(order_id,'service_order_detail.html')


@app.route("/os/<int:order_id>/print")
@login_required
def service_order_print(order_id):
    return show_order(order_id,'service_order_print.html')

# ---------- Search ----------

@app.route("/search")
@login_required
def search():
    return redirect(url_for('machines_list', q=request.args.get('q','').strip()))


# ---------- Uploads ----------

@app.route("/uploads/<path:filename>")
@login_required
def uploads(filename):
    # A URL do anexo também precisa respeitar o acesso da revenda.
    path=attachment_path(UPLOAD_DIR,filename)
    if not path: abort(404)
    match=re.fullmatch(r'machine_([0-9]+)/[^/]+',filename)
    if not match: abort(404)
    con=connect()
    machine=con.execute('SELECT * FROM machines WHERE id=?',(int(match[1]),)).fetchone()
    if not machine or not permitted(machine):
        con.close(); abort(404)
    registered=any(normalized_path(r['filename'])==normalized_path(filename)
                   for r in con.execute('SELECT filename FROM machine_photos WHERE machine_id=?',(machine['id'],)))
    con.close()
    if not registered: abort(404)
    return send_file(path,as_attachment=request.args.get('download')=='1')


# ---------- Validação, conferência e backup ----------
def scope_id():
    return g.user['reseller_id'] if g.user and g.user['role']=='revenda' else None


def permitted(row):
    return bool(g.user) and (g.user['role']=='admin' or row['reseller_id']==g.user['reseller_id'])


def normalized_path(value):
    import unicodedata
    return unicodedata.normalize('NFC',value)


def csrf_token():
    if '_csrf' not in session:
        session['_csrf']=secrets.token_urlsafe(32)
    return session['_csrf']


@app.context_processor
def interface_helpers():
    return {'csrf_token':csrf_token, 'today':datetime.date.today(), 'app_version':'3.0'}


@app.template_filter('brdate')
def brdate(value):
    if not value: return 'Não informada'
    try: return datetime.date.fromisoformat(str(value)[:10]).strftime('%d/%m/%Y')
    except ValueError: return value


@app.before_request
def protect_forms():
    if request.method=='POST':
        expected=session.get('_csrf','')
        submitted=request.form.get('_csrf','')
        if not expected or not hmac.compare_digest(expected,submitted):
            return render_template('error.html',title='Atualize a página',message='O formulário expirou. Volte, atualize a página e tente novamente.'),400


@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='SAMEORIGIN'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    if request.endpoint not in ('static','health'):
        response.headers['Cache-Control']='no-store'
    return response


@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
def user_error(error):
    messages={403:('Acesso não permitido','Este registro pertence a outra revenda.'),
              404:('Registro não encontrado','O registro ou anexo não está disponível para esta conta.'),
              413:('Envio muito grande','Envie até 25 MB por vez. Divida os anexos em mais de um envio.')}
    title,message=messages[error.code]
    return render_template('error.html',title=title,message=message),error.code


def record_event(con,action,record_id,details):
    con.execute('INSERT INTO maintenance_events(user_id,action,record_id,details) VALUES (?,?,?,?)',
                (g.user['id'],action,record_id,json.dumps(details,ensure_ascii=False)))


def get_machine(con,machine_id):
    machine=con.execute('''SELECT m.*,m.obs AS obs_text,c.name AS client_name,c.cpf,
        c.billing_address,c.delivery_address,c.delivery_location_url,c.reseller_id AS owner_reseller_id,
        r.razao_social AS reseller_name,r.cnpj,r.phone AS reseller_phone
        FROM machines m LEFT JOIN clients c ON c.id=m.client_id
        LEFT JOIN resellers r ON r.id=m.reseller_id WHERE m.id=?''',(machine_id,)).fetchone()
    if not machine:
        con.close(); abort(404)
    if not permitted(machine):
        con.close(); abort(403)
    data=dict(machine)
    data['obs_text']=data['obs']
    if g.user['role']=='revenda' and data['owner_reseller_id']!=g.user['reseller_id']:
        for field in ('client_name','cpf','billing_address','delivery_address','delivery_location_url'):
            data[field]=None
    return data


def save_client(client_id=None):
    con=connect()
    old=con.execute('SELECT * FROM clients WHERE id=?',(client_id,)).fetchone() if client_id else None
    if client_id and not old:
        con.close(); abort(404)
    if old and not permitted(old):
        con.close(); abort(403)
    data=dict(old) if old else {}
    fields=('name','cpf','rg','phone','billing_address','delivery_address','delivery_location_url')
    if request.method=='POST':
        data.update({f:request.form.get(f,'').strip() for f in fields})
        rid=request.form.get('reseller_id',type=int) if g.user['role']=='admin' else g.user['reseller_id']
        data['reseller_id']=rid
        error=None
        if not data['name']:
            error='Informe o nome do cliente.'
        elif not rid or not con.execute('SELECT 1 FROM resellers WHERE id=?',(rid,)).fetchone():
            error='Selecione uma revenda válida.'
        elif any(len(str(v or ''))>5000 for v in data.values()):
            error='Um dos campos está muito longo. Use até 5.000 caracteres.'
        if not error and data['cpf'] and (not old or normalized(old['cpf'])!=normalized(data['cpf']) or rid!=old['reseller_id']):
            for other in con.execute('SELECT id,cpf FROM clients WHERE reseller_id=? AND id!=?',(rid,client_id or 0)):
                if normalized(other['cpf'])==normalized(data['cpf']):
                    error='Este CPF já está cadastrado nesta revenda. Confira a lista de clientes.'; break
        if error:
            flash(error,'error')
        else:
            if old:
                snapshot(DB_PATH,Path(DATA_DIR)/'backups','antes-editar-cliente')
                con.execute('UPDATE clients SET reseller_id=?,'+','.join(f+'=?' for f in fields)+' WHERE id=?',
                            (rid,*(data[f] for f in fields),client_id))
                if rid!=old['reseller_id']:
                    con.execute('UPDATE machines SET reseller_id=? WHERE client_id=?',(rid,client_id))
                    con.execute('UPDATE service_orders SET reseller_id=? WHERE client_id=?',(rid,client_id))
                    record_event(con,'transferir_cliente',client_id,{'from':old['reseller_id'],'to':rid})
            else:
                client_id=con.execute('INSERT INTO clients(reseller_id,'+','.join(fields)+') VALUES ('+','.join('?' for _ in range(len(fields)+1))+')',
                                      (rid,*(data[f] for f in fields))).lastrowid
            con.commit(); con.close()
            flash('Cliente salvo com sucesso.','success')
            return redirect(url_for('client_panel',client_id=client_id))
    resellers=con.execute('SELECT id,razao_social,fantasy_name FROM resellers ORDER BY razao_social').fetchall() if g.user['role']=='admin' else []
    if not data and len(resellers)==1: data['reseller_id']=resellers[0]['id']
    con.close()
    return render_template('client_form.html',client=data,editing=bool(old),resellers=resellers)


def save_machine(machine_id=None):
    con=connect()
    old=get_machine(con,machine_id) if machine_id else None
    data=dict(old) if old else {'client_id':request.args.get('client_id',type=int)}
    where,params=(' WHERE c.reseller_id=?',[scope_id()]) if scope_id() is not None else ('',[])
    clients=con.execute('''SELECT c.id,c.name,c.reseller_id,r.razao_social AS reseller_name FROM clients c
                          JOIN resellers r ON r.id=c.reseller_id'''+where+' ORDER BY fold(c.name)',params).fetchall()
    fields=('name','brand','model','motor_model','nf_number','serial_number','engine_number','delivery_date','initial_hours')
    if request.method=='POST':
        data.update({f:request.form.get(f,'').strip() for f in fields})
        data['client_id']=request.form.get('client_id',type=int)
        client=next((c for c in clients if c['id']==data['client_id']),None)
        error=None
        if not client or not data['name']:
            error='Selecione um cliente válido e informe o nome da máquina.'
        if not error and data['delivery_date']:
            try: datetime.date.fromisoformat(data['delivery_date'])
            except ValueError: error='Informe uma data de entrega válida.'
        if not error and data['initial_hours']:
            try:
                data['initial_hours']=float(data['initial_hours'].replace(',','.'))
                if not math.isfinite(data['initial_hours']) or data['initial_hours']<0: raise ValueError
            except (ValueError,AttributeError): error='O horímetro deve ser um número maior ou igual a zero.'
        elif not data['initial_hours']: data['initial_hours']=None
        if not error:
            con.execute('BEGIN IMMEDIATE')
            for field,label in (('serial_number','número de série'),('engine_number','número do motor')):
                key=normalized(data[field])
                if not key or (old and normalized(old[field])==key and old['reseller_id']==client['reseller_id']): continue
                for other in con.execute('SELECT id,'+field+' FROM machines WHERE reseller_id=? AND id!=? AND archived_at IS NULL',
                                         (client['reseller_id'],machine_id or 0)):
                    if normalized(other[field])==key:
                        error=f'Este {label} já está cadastrado na máquina #{other["id"]}. Confira o cadastro existente.'; break
                if error: break
            if error: con.rollback()
        if error:
            flash(error,'error')
        else:
            if old:
                # A cópia usa uma segunda conexão; nenhuma escrita foi feita ainda.
                snapshot(DB_PATH,Path(DATA_DIR)/'backups','antes-editar-maquina')
                con.execute('UPDATE machines SET client_id=?,reseller_id=?,'+','.join(f+'=?' for f in fields)+' WHERE id=?',
                    (client['id'],client['reseller_id'],*(data[f] for f in fields),machine_id))
                if old['client_id']!=client['id'] or old['reseller_id']!=client['reseller_id']:
                    # Mantém cliente e máquina das OS históricas. Divergências continuam
                    # visíveis na conferência, sem reescrever a propriedade de um atendimento passado.
                    order_ids=[row[0] for row in con.execute('SELECT id FROM service_orders WHERE machine_id=?',(machine_id,))]
                    record_event(con,'alterar_proprietario',machine_id,{'from':old['client_id'],'to':client['id'],'preserved_orders':order_ids})
            else:
                machine_id=con.execute('INSERT INTO machines(client_id,reseller_id,'+','.join(fields)+') VALUES ('+','.join('?' for _ in range(len(fields)+2))+')',
                    (client['id'],client['reseller_id'],*(data[f] for f in fields))).lastrowid
            con.commit(); con.close()
            flash('Máquina salva com sucesso.','success')
            return redirect(url_for('machine_detail',machine_id=machine_id))
    con.close()
    return render_template('machine_form.html',machine=data,editing=bool(old),clients=clients)


def show_order(order_id,template):
    con=connect()
    o=con.execute('''SELECT o.*, c.name AS client_name,c.cpf,c.billing_address,c.delivery_address,c.delivery_location_url,c.reseller_id AS owner_reseller_id,
        m.reseller_id AS machine_reseller_id,m.name AS machine_name,m.brand,m.model,m.motor_model,m.nf_number,m.serial_number,m.engine_number,
        r.razao_social AS reseller_name,r.cnpj,r.phone AS reseller_phone
        FROM service_orders o LEFT JOIN clients c ON c.id=o.client_id
        LEFT JOIN resellers r ON r.id=o.reseller_id LEFT JOIN machines m ON m.id=o.machine_id WHERE o.id=?''',(order_id,)).fetchone()
    if not o:
        con.close(); abort(404)
    if not permitted(o):
        con.close(); abort(403)
    items=con.execute('SELECT * FROM service_items WHERE order_id=? ORDER BY id',(order_id,)).fetchall()
    con.close()
    data=dict(o)
    if g.user['role']=='revenda':
        if data['owner_reseller_id']!=g.user['reseller_id']:
            for field in ('client_name','cpf','billing_address','delivery_address','delivery_location_url'):
                data[field]=None
        if data['machine_reseller_id']!=g.user['reseller_id']:
            for field in ('machine_name','brand','model','motor_model','nf_number','serial_number','engine_number'):
                data[field]=None
    return render_template(template,o=data,items=items)


@app.route('/admin/conferencia')
@admin_required
def diagnostics():
    con=connect()
    report=audit(con,UPLOAD_DIR)
    clients=con.execute('SELECT id,name FROM clients ORDER BY fold(name)').fetchall()
    events=con.execute('SELECT * FROM maintenance_events ORDER BY id DESC LIMIT 20').fetchall()
    con.close()
    return render_template('diagnostics.html',report=report,clients=clients,events=events)


@app.route('/machines/<int:machine_id>/archive',methods=['POST'])
@admin_required
def machine_archive(machine_id):
    con=connect()
    machine=get_machine(con,machine_id)
    restore=request.form.get('action')=='restore'
    reason=request.form.get('reason','').strip()
    if not restore and (not reason or request.form.get('confirmation')!=str(machine_id)):
        con.close(); flash('Informe o motivo e confirme o número do cadastro para arquivar.','error')
        return redirect(url_for('machine_detail',machine_id=machine_id))
    snapshot(DB_PATH,Path(DATA_DIR)/'backups','antes-arquivar-maquina')
    stamp=None if restore else datetime.datetime.now(datetime.timezone.utc).isoformat()
    con.execute('UPDATE machines SET archived_at=?,archive_reason=? WHERE id=?',(stamp,None if restore else reason,machine_id))
    record_event(con,'restaurar_maquina' if restore else 'arquivar_maquina',machine_id,{'reason':reason})
    con.commit(); con.close()
    flash('Máquina restaurada.' if restore else 'Cadastro arquivado. Dados, anexos e OS foram preservados.','success')
    return redirect(url_for('machine_detail',machine_id=machine_id))


@app.route('/admin/os/<int:order_id>/relink',methods=['POST'])
@admin_required
def order_relink(order_id):
    con=connect()
    order=con.execute('SELECT * FROM service_orders WHERE id=?',(order_id,)).fetchone()
    client=con.execute('SELECT * FROM clients WHERE id=?',(request.form.get('client_id',type=int),)).fetchone()
    if not order or not client:
        con.close(); abort(404)
    if request.form.get('confirmation')!=str(order_id):
        con.close(); flash('Confirme o número da OS antes de alterar o vínculo.','error')
        return redirect(url_for('diagnostics'))
    machine=con.execute('SELECT * FROM machines WHERE id=?',(order['machine_id'],)).fetchone() if order['machine_id'] else None
    if machine and (machine['client_id']!=client['id'] or machine['reseller_id']!=client['reseller_id']):
        con.close(); flash('Primeiro corrija o proprietário da máquina vinculada a esta OS.','error')
        return redirect(url_for('diagnostics'))
    snapshot(DB_PATH,Path(DATA_DIR)/'backups','antes-vincular-os')
    con.execute('UPDATE service_orders SET client_id=?,reseller_id=? WHERE id=?',(client['id'],client['reseller_id'],order_id))
    record_event(con,'vincular_os',order_id,{'from':order['client_id'],'to':client['id']})
    con.commit(); con.close()
    flash('Vínculo da OS atualizado e alteração registrada.','success')
    return redirect(url_for('diagnostics'))


@app.route('/admin/backup',methods=['POST'])
@admin_required
def backup_download():
    from io import BytesIO
    buffer=BytesIO()
    with tempfile.TemporaryDirectory(prefix='solutec-backup-') as temp:
        db=snapshot(DB_PATH,temp,'copia')
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.write(db,'solutec.db')
            for path in Path(UPLOAD_DIR).rglob('*'):
                if path.is_file() and not path.is_symlink():
                    archive.write(path,'uploads/'+path.relative_to(UPLOAD_DIR).as_posix())
            archive.writestr('LEIA-ME.txt','Backup Solutec: banco consistente + anexos. Para restaurar, pare o serviço, guarde uma cópia do volume atual e substitua solutec.db e uploads no volume /data. Não restaure sobre o serviço em execução. Preserve SECRET_KEY. Não envie este backup para repositórios públicos.')
    buffer.seek(0)
    filename='Solutec_Backup_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.zip'
    return send_file(buffer,mimetype='application/zip',as_attachment=True,download_name=filename)


@app.route('/access/qr.svg')
@login_required
def access_qr():
    from io import BytesIO
    import qrcode
    from qrcode.image.svg import SvgPathImage
    buffer=BytesIO()
    qrcode.make(request.host_url.rstrip('/'),image_factory=SvgPathImage,box_size=6,border=3).save(buffer)
    return app.response_class(buffer.getvalue(),mimetype='image/svg+xml')


# O Gunicorn importa este módulo sem executar o bloco __main__.
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
