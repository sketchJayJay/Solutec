PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS resellers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj            TEXT NOT NULL,
    inscr_social    TEXT,
    razao_social    TEXT NOT NULL,
    fantasy_name    TEXT,
    responsavel     TEXT,
    phone           TEXT,
    email           TEXT,
    address_street  TEXT,
    address_number  TEXT,
    address_city    TEXT,
    address_state   TEXT,
    address_zip     TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL,
    reseller_id   INTEGER,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id)
);

CREATE TABLE IF NOT EXISTS clients (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT NOT NULL,
    cpf                   TEXT,
    rg                    TEXT,
        phone TEXT,
    billing_address       TEXT,
    delivery_address      TEXT,
    delivery_location_url TEXT,
    reseller_id           INTEGER NOT NULL,
    created_by            INTEGER,
    created_at            TEXT,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id),
    FOREIGN KEY (created_by)  REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS machines (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id      INTEGER NOT NULL,
    reseller_id    INTEGER NOT NULL,
    name           TEXT NOT NULL,
    brand          TEXT,
    model          TEXT,
    motor_model    TEXT,
    nf_number      TEXT,
    serial_number  TEXT,
    engine_number  TEXT,
    delivery_date  TEXT,
    initial_hours  REAL,
    obs            TEXT,
    created_at     TEXT,
    FOREIGN KEY (client_id)   REFERENCES clients(id) ON DELETE CASCADE,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id)
);

CREATE TABLE IF NOT EXISTS machine_photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id INTEGER NOT NULL,
    filename   TEXT NOT NULL,
    created_at TEXT,
    FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE
);
