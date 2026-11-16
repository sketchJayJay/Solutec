from flask import Flask, render_template, request, redirect, url_for, flash, session, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import sqlite3, os, datetime, urllib.parse, re

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
app.secret_key = os.environ.get("SECRET_KEY", "CHANGE-ME-IN-COOLIFY")
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
    """Normaliza telefone para formato wa.me (somente dígitos, com DDI 55 se faltar)."""
    if not raw_phone:
        return None
    digits = re.sub(r"\D+", "", str(raw_phone))
    digits = digits.lstrip("0")
    if not digits:
        return None
    # Se não veio com DDI, assume Brasil (55) quando parece um número válido (10/11 dígitos).
    if not digits.startswith("55") and len(digits) in (10, 11):
        digits = "55" + digits
    return digits


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
    # timeout: espera alguns segundos se o banco estiver em uso
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    # reduz problemas de 'database is locked'
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA busy_timeout = 5000;")
        print("[DEBUG] connect() usando banco:", DB_PATH)
    except Exception:
        # Se der qualquer erro aqui, não quebra a app
        pass
    return con


def init_db():
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
        obs_text TEXT,
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
    admin_password = os.environ.get("ADMIN_PASSWORD", "ChangeMe-Now-2026!")

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
            cur.execute(
                "UPDATE users SET email = ?, password_hash = ? WHERE id = ?",
                (admin_email, generate_password_hash(admin_password), u["id"])
            )
    else:
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
        if row:
            g.user = row


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
    return {"status": "ok"}, 200


# ---------- Routes ----------

@app.route("/")
@login_required
def dashboard():
    con = connect()
    cur = con.cursor()

    # A revenda enxerga somente os próprios indicadores.
    if g.user["role"] == "revenda":
        cur.execute("SELECT COUNT(*) FROM machines WHERE reseller_id = ?", (g.user["reseller_id"],))
        total_machines = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM clients WHERE reseller_id = ?", (g.user["reseller_id"],))
        total_clients = cur.fetchone()[0]
    else:
        cur.execute("SELECT COUNT(*) FROM machines")
        total_machines = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM clients")
        total_clients = cur.fetchone()[0]

    # Listagem curta de últimas máquinas (respeitando permissão da revenda)
    where = ""
    params = []
    if g.user["role"] == "revenda":
        where = "WHERE m.reseller_id = ?"
        params.append(g.user["reseller_id"])

    cur.execute(f"""
        SELECT m.id, m.name, c.name as client_name, m.serial_number,
               m.delivery_date, r.razao_social as reseller_name
        FROM machines m
        JOIN clients c ON c.id = m.client_id
        JOIN resellers r ON r.id = m.reseller_id
        {where}
        ORDER BY m.created_at DESC
        LIMIT 6
    """, params)
    last_machines = cur.fetchall()

    # Flag de primeira utilização (sem clientes nem máquinas)
    first_run = (total_machines == 0 and total_clients == 0)

    con.close()
    return render_template(
        "dashboard.html",
        total_machines=total_machines,
        total_clients=total_clients,
        last_machines=last_machines,
        first_run=first_run,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        con = connect()
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        con.close()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Login inválido.", "error")
            return render_template("login.html")
        session["user_id"] = user["id"]
        flash("Bem-vindo(a)!", "success")
        next_url = request.args.get("next") or url_for("dashboard")
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
    q = request.args.get("q", "").strip()
    con = connect()
    cur = con.cursor()
    where_parts = []
    params = []
    if g.user["role"] == "revenda":
        where_parts.append("c.reseller_id = ?")
        params.append(g.user["reseller_id"])
    if q:
        like = f"%{q}%"
        where_parts.append("(c.name LIKE ? OR c.cpf LIKE ? OR c.phone LIKE ?)")
        params.extend([like, like, like])
    where_sql = ""
    if where_parts:
        where_sql = "WHERE " + " AND ".join(where_parts)
    cur.execute(f"""
        SELECT c.*, r.razao_social as reseller_name
        FROM clients c
        JOIN resellers r ON r.id = c.reseller_id
        {where_sql}
        ORDER BY c.created_at DESC
    """, params)
    rows = cur.fetchall()
    con.close()
    return render_template("clients_list.html", rows=rows, q=q)



@app.route("/clients/new", methods=["GET", "POST"])
@login_required
def client_new():
    con = connect()
    cur = con.cursor()

    if request.method == "POST":
        name = request.form.get("name","").strip()
        cpf = request.form.get("cpf","").strip()
        rg = request.form.get("rg","").strip()
        phone = request.form.get("phone","").strip()
        billing_address = request.form.get("billing_address","").strip()
        delivery_address = request.form.get("delivery_address","").strip()
        delivery_location_url = request.form.get("delivery_location_url","").strip()

        if not name:
            flash("Nome do cliente é obrigatório.", "error")
        else:
            if g.user["role"] == "admin":
                reseller_id = request.form.get("reseller_id")
            else:
                reseller_id = g.user["reseller_id"]
            cur.execute("""
                INSERT INTO clients(reseller_id, name, cpf, rg, phone, billing_address, delivery_address, delivery_location_url)
                VALUES (?,?,?,?,?,?,?,?)
            """, (reseller_id, name, cpf, rg, phone, billing_address, delivery_address, delivery_location_url))
            con.commit()
            flash("Cliente cadastrado com sucesso.", "success")
            con.close()
            return redirect(url_for("clients_list"))

    # GET
    resellers = []
    if g.user["role"] == "admin":
        cur.execute("SELECT id, razao_social, fantasy_name FROM resellers ORDER BY razao_social")
        resellers = cur.fetchall()
    con.close()
    return render_template("client_form.html", resellers=resellers)




@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def client_edit(client_id):
    con = connect()
    cur = con.cursor()

    # Busca o cliente
    cur.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    client = cur.fetchone()
    if not client:
        con.close()
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("clients_list"))

    # Permissão: revenda só pode editar seus próprios clientes
    if g.user["role"] == "revenda" and client["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Você não tem permissão para editar este cliente.", "error")
        return redirect(url_for("clients_list"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        cpf = request.form.get("cpf", "").strip()
        rg = request.form.get("rg", "").strip()
        phone = request.form.get("phone", "").strip()
        billing_address = request.form.get("billing_address", "").strip()
        delivery_address = request.form.get("delivery_address", "").strip()
        delivery_location_url = request.form.get("delivery_location_url", "").strip()

        if not name:
            flash("Nome do cliente é obrigatório.", "error")
        else:
            if g.user["role"] == "admin":
                reseller_id = request.form.get("reseller_id")
            else:
                reseller_id = client["reseller_id"]

            cur.execute(
                """
                UPDATE clients
                   SET reseller_id = ?,
                       name = ?,
                       cpf = ?,
                       rg = ?,
                       phone = ?,
                       billing_address = ?,
                       delivery_address = ?,
                       delivery_location_url = ?
                 WHERE id = ?
                """,
                (reseller_id, name, cpf, rg, phone, billing_address, delivery_address, delivery_location_url, client_id),
            )
            con.commit()
            flash("Cliente atualizado com sucesso.", "success")
            con.close()
            return redirect(url_for("client_panel", client_id=client_id))

    # GET ou POST com erro de validação: carrega lista de revendas (se admin) e volta para o formulário
    resellers = []
    if g.user["role"] == "admin":
        cur.execute("SELECT id, razao_social, fantasy_name FROM resellers ORDER BY razao_social")
        resellers = cur.fetchall()

    con.close()
    return render_template("client_form.html", client=client, resellers=resellers)


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def client_delete(client_id):
    """Exclui o cliente e todos os registros vinculados (máquinas, OS).
    Respeita permissão da revenda: só pode excluir clientes da própria revenda.
    """
    con = connect()
    cur = con.cursor()

    cur.execute("SELECT id, name, reseller_id FROM clients WHERE id = ?", (client_id,))
    client = cur.fetchone()
    if not client:
        con.close()
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("clients_list"))

    # Revenda só pode excluir clientes seus
    if g.user["role"] == "revenda" and client["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Você não tem permissão para excluir este cliente.", "error")
        return redirect(url_for("clients_list"))

    cur.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    con.commit()
    con.close()
    flash(f"Cliente '{client['name']}' e registros vinculados foram excluídos.", "success")
    return redirect(url_for("clients_list"))




# ---------- Machines ----------

@app.route("/machines")
@login_required
def machines_list():
    con = connect()
    cur = con.cursor()
    where = ""
    params = []
    if g.user["role"] == "revenda":
        where = "WHERE m.reseller_id = ?"
        params.append(g.user["reseller_id"])

    cur.execute(f"""
        SELECT m.*, c.name as client_name, c.delivery_location_url as delivery_location_url,
               r.razao_social as reseller_name
        FROM machines m
        JOIN clients c ON c.id = m.client_id
        JOIN resellers r ON r.id = m.reseller_id
        {where}
        ORDER BY m.created_at DESC
    """, params)
    rows = cur.fetchall()
    con.close()
    return render_template("machines_list.html", rows=rows)


@app.route("/machines/new", methods=["GET", "POST"])
@login_required
def machine_new():
    con = connect()
    cur = con.cursor()

    # clients list filtered by role
    if g.user["role"] == "admin":
        cur.execute("""
            SELECT c.id, c.name, r.razao_social as reseller_name
            FROM clients c
            JOIN resellers r ON r.id = c.reseller_id
            ORDER BY r.razao_social, c.name
        """)
    else:
        cur.execute("""
            SELECT c.id, c.name, r.razao_social as reseller_name
            FROM clients c
            JOIN resellers r ON r.id = c.reseller_id
            WHERE c.reseller_id = ?
            ORDER BY c.name
        """, (g.user["reseller_id"],))
    clients = cur.fetchall()

    if request.method == "POST":
        client_id = request.form.get("client_id")
        name = request.form.get("name","").strip()
        brand = request.form.get("brand","").strip()
        model = request.form.get("model","").strip()
        motor_model = request.form.get("motor_model","").strip()
        nf_number = request.form.get("nf_number","").strip()
        serial_number = request.form.get("serial_number","").strip()
        engine_number = request.form.get("engine_number","").strip()
        delivery_date = request.form.get("delivery_date","").strip()
        initial_hours = request.form.get("initial_hours","").strip() or None

        if not client_id or not name:
            flash("Cliente e nome da máquina são obrigatórios.", "error")
        else:
            if g.user["role"] == "admin":
                # admin escolhe revenda do cliente
                cur.execute("SELECT reseller_id FROM clients WHERE id = ?", (client_id,))
                row = cur.fetchone()
                reseller_id = row["reseller_id"] if row else None
            else:
                reseller_id = g.user["reseller_id"]

            cur.execute("""
                INSERT INTO machines(reseller_id, client_id, name, brand, model, motor_model,
                                     nf_number, serial_number, engine_number, delivery_date, initial_hours)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (reseller_id, client_id, name, brand, model, motor_model,
                  nf_number, serial_number, engine_number, delivery_date, initial_hours))
            con.commit()
            flash("Máquina cadastrada com sucesso.", "success")
            con.close()
            return redirect(url_for("machines_list"))

    pref_client_id = request.args.get("client_id")
    con.close()
    return render_template("machine_form.html", clients=clients, pref_client_id=pref_client_id)



@app.route("/machines/<int:machine_id>/edit", methods=["GET", "POST"])
@login_required
def machine_edit(machine_id):
    con = connect()
    cur = con.cursor()

    # Busca a máquina
    cur.execute("SELECT * FROM machines WHERE id = ?", (machine_id,))
    machine = cur.fetchone()
    if not machine:
        con.close()
        flash("Máquina não encontrada.", "error")
        return redirect(url_for("machines_list"))

    # Permissão: revenda só pode editar máquinas da própria revenda
    if g.user["role"] == "revenda" and machine["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Você não tem permissão para editar esta máquina.", "error")
        return redirect(url_for("machines_list"))

    # Lista de clientes, filtrada por papel
    if g.user["role"] == "admin":
        cur.execute(
            """
            SELECT c.id, c.name, r.razao_social as reseller_name
              FROM clients c
              JOIN resellers r ON r.id = c.reseller_id
             ORDER BY r.razao_social, c.name
            """
        )
    else:
        cur.execute(
            """
            SELECT c.id, c.name, r.razao_social as reseller_name
              FROM clients c
              JOIN resellers r ON r.id = c.reseller_id
             WHERE c.reseller_id = ?
             ORDER BY c.name
            """,
            (g.user["reseller_id"],),
        )
    clients = cur.fetchall()

    if request.method == "POST":
        client_id = request.form.get("client_id")
        name = request.form.get("name", "").strip()
        brand = request.form.get("brand", "").strip()
        model = request.form.get("model", "").strip()
        motor_model = request.form.get("motor_model", "").strip()
        nf_number = request.form.get("nf_number", "").strip()
        serial_number = request.form.get("serial_number", "").strip()
        engine_number = request.form.get("engine_number", "").strip()
        delivery_date = request.form.get("delivery_date", "").strip()
        initial_hours = request.form.get("initial_hours", "").strip() or None

        if not client_id or not name:
            flash("Cliente e nome da máquina são obrigatórios.", "error")
        else:
            # Define revenda a partir do cliente (admin) ou do usuário logado (revenda)
            if g.user["role"] == "admin":
                cur.execute("SELECT reseller_id FROM clients WHERE id = ?", (client_id,))
                row = cur.fetchone()
                reseller_id = row["reseller_id"] if row else machine["reseller_id"]
            else:
                reseller_id = g.user["reseller_id"]

            cur.execute(
                """
                UPDATE machines
                   SET reseller_id = ?,
                       client_id = ?,
                       name = ?,
                       brand = ?,
                       model = ?,
                       motor_model = ?,
                       nf_number = ?,
                       serial_number = ?,
                       engine_number = ?,
                       delivery_date = ?,
                       initial_hours = ?
                 WHERE id = ?
                """,
                (
                    reseller_id,
                    client_id,
                    name,
                    brand,
                    model,
                    motor_model,
                    nf_number,
                    serial_number,
                    engine_number,
                    delivery_date,
                    initial_hours,
                    machine_id,
                ),
            )
            con.commit()
            flash("Máquina atualizada com sucesso.", "success")
            con.close()
            return redirect(url_for("machine_detail", machine_id=machine_id))

    # GET ou POST com erro de validação
    pref_client_id = machine["client_id"]
    con.close()
    return render_template("machine_form.html", clients=clients, pref_client_id=pref_client_id, machine=machine)


@app.route("/machines/<int:machine_id>", methods=["GET", "POST"])
@login_required
def machine_detail(machine_id):
    con = connect()
    cur = con.cursor()

    cur.execute("""
        SELECT m.*,
               m.obs as obs_text,
               c.name as client_name, c.cpf, c.billing_address, c.delivery_address,
               c.delivery_location_url as delivery_location_url,
               r.razao_social as reseller_name, r.cnpj
        FROM machines m
        JOIN clients c ON c.id = m.client_id
        JOIN resellers r ON r.id = m.reseller_id
        WHERE m.id = ?
    """, (machine_id,))
    m = cur.fetchone()
    if m:
        try:
            row = dict(m)
            print(f"[DEBUG] GET machine_detail {machine_id}: obs={row.get('obs')!r}, obs_text={row.get('obs_text')!r}")
        except Exception as e:
            print("[DEBUG] Erro ao inspecionar OBS na tela da máquina:", e)
    if not m:
        con.close()
        flash("Máquina não encontrada.", "error")
        return redirect(url_for("machines_list"))

    # Permissão da revenda
    if g.user["role"] == "revenda" and m["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Acesso não permitido para esta máquina.", "error")
        return redirect(url_for("machines_list"))

    if request.method == "POST":
        obs_text = request.form.get("obs_text","")
        print(f"[DEBUG] Salvando OBS da máquina {machine_id}: {obs_text!r}")
        cur.execute("UPDATE machines SET obs = ? WHERE id = ?", (obs_text, machine_id))

        files = request.files.getlist("photos")
        for f in files:
            if not f or not f.filename:
                continue
            folder = os.path.join(UPLOAD_DIR, f"machine_{machine_id}")
            os.makedirs(folder, exist_ok=True)
            safe_name = f.filename.replace(" ", "_")
            fname = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
            full_path = os.path.join(folder, fname)
            f.save(full_path)
            cur.execute("INSERT INTO machine_photos(machine_id, filename) VALUES (?,?)",
                        (machine_id, f"machine_{machine_id}/{fname}"))

        con.commit()
        # Rele a OBS direto do banco para confirmar
        try:
            cur.execute("SELECT obs FROM machines WHERE id = ?", (machine_id,))
            row = cur.fetchone()
            if row:
                print(f"[DEBUG] OBS no banco agora: {row['obs']!r}")
            else:
                print("[DEBUG] Máquina não encontrada ao reler OBS.")
        except Exception as e:
            print("[DEBUG] Erro ao reler OBS:", e)
        con.close()

        flash("OBS e anexos salvos com sucesso.", "success")
        return redirect(url_for("machine_detail", machine_id=machine_id))

    cur.execute("SELECT * FROM machine_photos WHERE machine_id = ? ORDER BY id DESC", (machine_id,))
    photos = cur.fetchall()
    con.close()
    return render_template("machine_detail.html", m=m, photos=photos)




@app.route("/machines/<int:machine_id>/photos/<int:photo_id>/delete", methods=["POST"])
@login_required
def machine_photo_delete(machine_id, photo_id):
    con = connect()
    cur = con.cursor()

    # Carrega a máquina para validar permissão
    cur.execute("SELECT * FROM machines WHERE id = ?", (machine_id,))
    m = cur.fetchone()
    if not m:
        con.close()
        flash("Máquina não encontrada.", "error")
        return redirect(url_for("machines_list"))

    # Permissão da revenda
    if g.user["role"] == "revenda" and m["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Acesso não permitido.", "error")
        return redirect(url_for("machines_list"))

    cur.execute("SELECT * FROM machine_photos WHERE id = ? AND machine_id = ?", (photo_id, machine_id))
    photo = cur.fetchone()
    if not photo:
        con.close()
        flash("Imagem não encontrada.", "error")
        return redirect(url_for("machine_detail", machine_id=machine_id))

    # Apaga arquivo do disco (se existir)
    try:
        rel = photo["filename"]
        abs_path = os.path.abspath(os.path.join(UPLOAD_DIR, rel))
        base = os.path.abspath(UPLOAD_DIR)
        if abs_path.startswith(base) and os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception as e:
        print("[DEBUG] Erro ao excluir arquivo de imagem:", e)

    # Apaga do banco
    cur.execute("DELETE FROM machine_photos WHERE id = ?", (photo_id,))
    con.commit()
    con.close()

    flash("Imagem excluída com sucesso.", "success")
    return redirect(url_for("machine_detail", machine_id=machine_id))
@app.route("/machines/<int:machine_id>/print")
@login_required
def machine_print(machine_id):
    con = connect()
    cur = con.cursor()
    cur.execute("""
        SELECT m.*,
               m.obs as obs_text,
               c.name as client_name, c.cpf, c.billing_address, c.delivery_address,
               r.razao_social as reseller_name, r.cnpj, r.phone as reseller_phone
        FROM machines m
        JOIN clients c ON c.id = m.client_id
        JOIN resellers r ON r.id = m.reseller_id
        WHERE m.id = ?
    """, (machine_id,))
    m = cur.fetchone()
    if m:
        try:
            row = dict(m)
            print(f"[DEBUG] GET machine_print {machine_id}: obs={row.get('obs')!r}, obs_text={row.get('obs_text')!r}")
        except Exception as e:
            print("[DEBUG] Erro ao inspecionar OBS na impressão da máquina:", e)
    con.close()
    if not m:
        flash("Máquina não encontrada.", "error")
        return redirect(url_for("machines_list"))
    # Permissão
    if g.user["role"] == "revenda" and m["reseller_id"] != g.user["reseller_id"]:
        flash("Acesso não permitido para esta máquina.", "error")
        return redirect(url_for("machines_list"))
    return render_template("machine_print.html", m=m)


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
        WHERE m.client_id = ?
        ORDER BY m.created_at DESC
    """, (client_id,))
    machines = cur.fetchall()

    # Últimas OS deste cliente
    cur.execute("""
        SELECT o.*, m.name AS machine_name
        FROM service_orders o
        LEFT JOIN machines m ON m.id = o.machine_id
        WHERE o.client_id = ?
        ORDER BY o.created_at DESC
        LIMIT 50
    """, (client_id,))
    orders = cur.fetchall()

    con.close()
    return render_template("client_panel.html", client=client, machines=machines, orders=orders)


@app.route("/clients/<int:client_id>/os/nova", methods=["POST"])
@login_required
def client_os_new(client_id):
    """Cria uma nova OS vinculada ao cliente (e opcionalmente a uma máquina)."""
    con = connect()
    cur = con.cursor()

    # Garante que o cliente existe e respeita permissão da revenda
    cur.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    client = cur.fetchone()
    if not client:
        con.close()
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("clients_list"))

    if g.user["role"] == "revenda" and client["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Acesso não permitido para este cliente.", "error")
        return redirect(url_for("clients_list"))

    service_date = request.form.get("service_date", "").strip()
    address = request.form.get("address", "").strip()
    maps_url = request.form.get("maps_url", "").strip()
    obs = request.form.get("obs", "").strip()
    machine_id = request.form.get("machine_id", "").strip() or None

    # reseller da OS
    if g.user["role"] == "admin":
        reseller_id = client["reseller_id"]
    else:
        reseller_id = g.user["reseller_id"]

    cur.execute("""
        INSERT INTO service_orders(reseller_id, client_id, machine_id, service_date, address, maps_url, obs)
        VALUES (?,?,?,?,?,?,?)
    """, (reseller_id, client_id, machine_id, service_date, address, maps_url, obs))
    order_id = cur.lastrowid

    # Itens da OS (campo aberto, um por linha)
    items = request.form.getlist("items[]")
    for txt in items:
        t = (txt or "").strip()
        if not t:
            continue
        cur.execute("INSERT INTO service_items(order_id, item_text) VALUES (?,?)", (order_id, t))

    con.commit()
    con.close()
    flash("OS criada com sucesso.", "success")
    return redirect(url_for("service_order_detail", order_id=order_id))


@app.route("/os/<int:order_id>")
@login_required
def service_order_detail(order_id):
    """Detalhe da OS, com botão para imprimir e enviar localização pelo WhatsApp."""
    con = connect()
    cur = con.cursor()
    cur.execute("""
        SELECT o.*, 
               c.name AS client_name, c.cpf, c.billing_address, c.delivery_address, c.delivery_location_url,
               m.name AS machine_name,
               r.razao_social AS reseller_name, r.cnpj, r.phone AS reseller_phone
        FROM service_orders o
        JOIN clients c ON c.id = o.client_id
        JOIN resellers r ON r.id = o.reseller_id
        LEFT JOIN machines m ON m.id = o.machine_id
        WHERE o.id = ?
    """, (order_id,))
    o = cur.fetchone()
    if not o:
        con.close()
        flash("OS não encontrada.", "error")
        return redirect(url_for("clients_list"))

    if g.user["role"] == "revenda" and o["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Acesso não permitido para esta OS.", "error")
        return redirect(url_for("clients_list"))

    cur.execute("SELECT * FROM service_items WHERE order_id = ? ORDER BY id", (order_id,))
    items = cur.fetchall()
    con.close()
    return render_template("service_order_detail.html", o=o, items=items)


@app.route("/os/<int:order_id>/print")
@login_required
def service_order_print(order_id):
    """Versão de impressão da OS, com logo da Solutec."""
    con = connect()
    cur = con.cursor()
    cur.execute("""
        SELECT o.*, 
               c.name AS client_name, c.cpf, c.billing_address, c.delivery_address, c.delivery_location_url,
               m.name AS machine_name, m.brand, m.model, m.motor_model,
               m.nf_number, m.serial_number, m.engine_number,
               r.razao_social AS reseller_name, r.cnpj, r.phone AS reseller_phone
        FROM service_orders o
        JOIN clients c ON c.id = o.client_id
        JOIN resellers r ON r.id = o.reseller_id
        LEFT JOIN machines m ON m.id = o.machine_id
        WHERE o.id = ?
    """, (order_id,))
    o = cur.fetchone()
    if not o:
        con.close()
        flash("OS não encontrada.", "error")
        return redirect(url_for("clients_list"))

    if g.user["role"] == "revenda" and o["reseller_id"] != g.user["reseller_id"]:
        con.close()
        flash("Acesso não permitido para esta OS.", "error")
        return redirect(url_for("clients_list"))

    cur.execute("SELECT * FROM service_items WHERE order_id = ? ORDER BY id", (order_id,))
    items = cur.fetchall()
    con.close()
    return render_template("service_order_print.html", o=o, items=items)

# ---------- Search ----------

@app.route("/search")
@login_required
def search():
    q = request.args.get("q","").strip()
    rows = []
    if not q:
        return render_template("search.html", q=q, rows=rows)

    like = f"%{q}%"
    params = [like, like, like, like, like, like, like, like, like, like]
    extra_where = ""
    if g.user["role"] == "revenda":
        extra_where = "AND m.reseller_id = ?"
        params.append(g.user["reseller_id"])

    con = connect()
    cur = con.cursor()
    cur.execute(f"""
        SELECT m.id, m.name as machine_name, m.serial_number, m.engine_number, m.nf_number,
               m.delivery_date,
               c.name as client_name, c.cpf,
               r.razao_social as reseller_name, r.cnpj as reseller_cnpj, r.address_city as reseller_city
        FROM machines m
        JOIN clients c ON c.id = m.client_id
        JOIN resellers r ON r.id = m.reseller_id
        WHERE (
            c.name LIKE ?
            OR c.cpf LIKE ?
            OR m.serial_number LIKE ?
            OR m.engine_number LIKE ?
            OR m.nf_number LIKE ?
            OR c.billing_address LIKE ?
            OR c.delivery_address LIKE ?
            OR r.razao_social LIKE ?
            OR r.cnpj LIKE ?
            OR r.address_city LIKE ?
        )
        {extra_where}
        ORDER BY m.delivery_date DESC
        LIMIT 50
    """, params)
    rows = cur.fetchall()
    con.close()
    return render_template("search.html", q=q, rows=rows)


# ---------- Uploads ----------

@app.route("/uploads/<path:filename>")
@login_required
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# O Gunicorn importa este módulo sem executar o bloco __main__.
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
