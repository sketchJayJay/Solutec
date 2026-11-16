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
