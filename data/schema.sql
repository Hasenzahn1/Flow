CREATE TABLE IF NOT EXISTS tools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,
    route       TEXT NOT NULL,
    icon_path   TEXT,
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
