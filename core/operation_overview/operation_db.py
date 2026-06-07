from core.db import get_db, init_db

ALLOWED_COLUMNS = {"name", "date", "description", "place"}

def get_operations() -> list[dict]:
    con = get_db()
    rows = con.execute("SELECT * FROM overview_operations ORDER BY date DESC").fetchall()
    con.close()
    return [dict(row) for row in rows]

def add_operation(name) -> dict:
    con = get_db()
    cur = con.execute("INSERT INTO overview_operations (name) VALUES (?)", (name,))
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return get_operation(new_id)

def update_operation(operation_id, **kwargs):
    columns = {k: v for k, v in kwargs.items() if k in ALLOWED_COLUMNS}
    if not columns:
        return get_operation(operation_id)

    assign = ", ".join(f"{column} = ?" for column in columns.keys())
    values = list(kwargs.values()) + [operation_id]

    con = get_db()
    con.execute(f"UPDATE overview_operations SET {assign} WHERE id = ?", values)
    con.commit()
    con.close()
    return get_operation(operation_id)

def delete_operation(operation_id):
    con = get_db()
    cur = con.execute("DELETE FROM overview_operations WHERE id = ?", (operation_id,))
    con.commit()
    deleted = cur.rowcount > 0
    con.close()
    return deleted

def get_operation(operation_id):
    con = get_db()
    row = con.execute("SELECT * FROM overview_operations WHERE id = ?", (operation_id,)).fetchone()
    con.close()
    return dict(row)