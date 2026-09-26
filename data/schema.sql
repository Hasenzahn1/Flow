CREATE TABLE IF NOT EXISTS tools (
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

CREATE TABLE IF NOT EXISTS overview_operations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    date        INTEGER DEFAULT (strftime('%s', 'now')),
    description TEXT,
    place       TEXT
);

CREATE TABLE IF NOT EXISTS overview_missions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id    INTEGER,
    number          INTEGER,
    timestamp       INTEGER DEFAULT (strftime('%s', 'now')),
    place           TEXT,
    unit            TEXT,
    description     TEXT,
    status          INTEGER DEFAULT 0,
    changed_at     INTEGER,
    FOREIGN KEY(operation_id) REFERENCES overview_operations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS overview_persons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id      INTEGER,
    number          INTEGER,
    last_name       TEXT,
    name            TEXT,
    birthdate       INTEGER,
    gender          TEXT,
    hurt            INTEGER DEFAULT 0,
    handover        TEXT,
    info            TEXT,
    triage          INTEGER DEFAULT 0,
    FOREIGN KEY(mission_id) REFERENCES overview_missions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS overview_helpers (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id             INTEGER NOT NULL,
    last_name                TEXT NOT NULL,
    first_name               TEXT NOT NULL,
    birth_date               TEXT NOT NULL,
    gender                   TEXT,
    postal_code              TEXT,
    city                     TEXT,
    nationality              TEXT,
    street                   TEXT,
    mobile                   TEXT,
    email                    TEXT,
    nutrition_type           TEXT,
    nutrition_note           TEXT,
    district_association     TEXT,
    community                TEXT,
    deployment_location      TEXT,
    deployment_info          TEXT,
    deployment_start         TEXT,
    deployment_end           TEXT,
    membership_number        TEXT,
    district_association_raw TEXT,
    card_number              TEXT,
    verification_code        TEXT,
    status                   TEXT NOT NULL DEFAULT 'Anwesend'
                             CHECK(status IN ('Anwesend', 'Abgemeldet')),
    registered_at            INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    identity_key             TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES overview_operations(id) ON DELETE CASCADE,
    UNIQUE(operation_id, identity_key)
);

CREATE INDEX IF NOT EXISTS idx_overview_helpers_operation
    ON overview_helpers(operation_id, registered_at DESC);

CREATE TABLE IF NOT EXISTS overview_helper_sources (
    helper_id INTEGER NOT NULL,
    source    TEXT NOT NULL CHECK(source IN ('Meldekarte-QR', 'DRK-Server-QR', 'Manuell')),
    PRIMARY KEY(helper_id, source),
    FOREIGN KEY(helper_id) REFERENCES overview_helpers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS overview_helper_qualifications (
    helper_id     INTEGER NOT NULL,
    qualification TEXT NOT NULL,
    PRIMARY KEY(helper_id, qualification),
    FOREIGN KEY(helper_id) REFERENCES overview_helpers(id) ON DELETE CASCADE
);

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

CREATE TABLE IF NOT EXISTS auth_settings (
    id                  INTEGER PRIMARY KEY CHECK(id = 1),
    admin_password_hash TEXT NOT NULL,
    session_version     INTEGER NOT NULL DEFAULT 1
);
