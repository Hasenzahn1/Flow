CREATE TABLE IF NOT EXISTS tools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,
    route       TEXT NOT NULL,
    icon_path   TEXT,
    order_index INTEGER DEFAULT 0,
    active      INTEGER DEFAULT 1
);
