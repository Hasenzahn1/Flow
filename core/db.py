import sqlite3
import os

from werkzeug.security import generate_password_hash

DB_PATH = "data/app.db"

def get_db():
    os.makedirs("data", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    con = get_db()
    con.execute("PRAGMA journal_mode = WAL")

    with open("data/schema.sql", 'r') as f:
        text = f.read()
        con.executescript(text)

    con.commit()
    con.close()

def migrate():
    con = get_db()
    version = con.execute("PRAGMA user_version").fetchone()[0]

    if version < 1:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(tools)").fetchall()}
        if "description" not in columns:
            con.execute("ALTER TABLE tools ADD COLUMN description TEXT")
        con.execute("PRAGMA user_version = 1")

    if version < 2:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS overview_helpers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER NOT NULL,
                last_name TEXT NOT NULL,
                first_name TEXT NOT NULL,
                birth_date TEXT NOT NULL,
                gender TEXT,
                postal_code TEXT,
                city TEXT,
                nationality TEXT,
                street TEXT,
                mobile TEXT,
                email TEXT,
                nutrition_type TEXT,
                nutrition_note TEXT,
                district_association TEXT,
                community TEXT,
                deployment_location TEXT,
                deployment_info TEXT,
                deployment_start TEXT,
                deployment_end TEXT,
                membership_number TEXT,
                district_association_raw TEXT,
                card_number TEXT,
                verification_code TEXT,
                status TEXT NOT NULL DEFAULT 'Anwesend'
                    CHECK(status IN ('Anwesend', 'Abgemeldet')),
                registered_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                identity_key TEXT NOT NULL,
                FOREIGN KEY(operation_id) REFERENCES overview_operations(id) ON DELETE CASCADE,
                UNIQUE(operation_id, identity_key)
            );
            CREATE INDEX IF NOT EXISTS idx_overview_helpers_operation
                ON overview_helpers(operation_id, registered_at DESC);
            CREATE TABLE IF NOT EXISTS overview_helper_sources (
                helper_id INTEGER NOT NULL,
                source TEXT NOT NULL CHECK(source IN ('Meldekarte-QR', 'DRK-Server-QR', 'Manuell')),
                PRIMARY KEY(helper_id, source),
                FOREIGN KEY(helper_id) REFERENCES overview_helpers(id) ON DELETE CASCADE
            );
        """)
        con.execute("PRAGMA user_version = 2")

    if version < 3:
        con.execute("""
            CREATE TABLE IF NOT EXISTS auth_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                admin_password_hash TEXT NOT NULL,
                session_version INTEGER NOT NULL DEFAULT 1
            )
        """)
        con.execute(
            "INSERT OR IGNORE INTO auth_settings (id, admin_password_hash, session_version) VALUES (1, ?, 1)",
            (generate_password_hash("admin"),),
        )
        con.execute("PRAGMA user_version = 3")

    if version < 4:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(tools)").fetchall()}
        if "color" not in columns:
            con.execute(
                "ALTER TABLE tools ADD COLUMN color TEXT NOT NULL DEFAULT 'blue' "
                "CHECK(color IN ('blue', 'green', 'red'))"
            )
        con.execute("PRAGMA user_version = 4")

    if version < 5:
        tools_sql = con.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tools'"
        ).fetchone()["sql"]
        if "'cyan'" not in tools_sql:
            con.executescript("""
                ALTER TABLE tools RENAME TO tools_legacy_colors;
                CREATE TABLE tools (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    label       TEXT NOT NULL,
                    route       TEXT NOT NULL,
                    icon_path   TEXT,
                    description TEXT,
                    color       TEXT NOT NULL DEFAULT 'blue'
                                CHECK(color IN ('blue', 'green', 'red', 'cyan', 'amber', 'violet')),
                    order_index INTEGER DEFAULT 0,
                    active      INTEGER DEFAULT 1
                );
                INSERT INTO tools (id, label, route, icon_path, description, color, order_index, active)
                SELECT id, label, route, icon_path, description, color, order_index, active
                FROM tools_legacy_colors;
                DROP TABLE tools_legacy_colors;
            """)
        con.execute("PRAGMA user_version = 5")

    if version < 6:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS overview_vehicles (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id     INTEGER NOT NULL,
                call_sign        TEXT NOT NULL,
                vehicle_type     TEXT NOT NULL,
                phone            TEXT,
                target_occupancy INTEGER NOT NULL CHECK(target_occupancy >= 1),
                max_seats        INTEGER NOT NULL CHECK(max_seats >= target_occupancy),
                order_index      INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(operation_id) REFERENCES overview_operations(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_overview_vehicles_operation
                ON overview_vehicles(operation_id, order_index, id);
            CREATE TABLE IF NOT EXISTS overview_vehicle_assignments (
                helper_id  INTEGER PRIMARY KEY,
                vehicle_id INTEGER NOT NULL,
                role       TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member', 'leader')),
                FOREIGN KEY(helper_id) REFERENCES overview_helpers(id) ON DELETE CASCADE,
                FOREIGN KEY(vehicle_id) REFERENCES overview_vehicles(id) ON DELETE CASCADE
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_overview_vehicle_one_leader
                ON overview_vehicle_assignments(vehicle_id) WHERE role = 'leader';
        """)
        con.execute("PRAGMA user_version = 6")

    if version < 7:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS overview_helper_qualifications (
                helper_id     INTEGER NOT NULL,
                qualification TEXT NOT NULL,
                PRIMARY KEY(helper_id, qualification),
                FOREIGN KEY(helper_id) REFERENCES overview_helpers(id) ON DELETE CASCADE
            );
        """)
        con.execute("PRAGMA user_version = 7")

    con.commit()
    con.close()
