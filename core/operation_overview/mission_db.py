from core.db import get_db, init_db

ALLOWED_COLUMNS = {"place", "unit", "description", "status"}

def get_missions(operation_id) -> list[dict]:
    con = get_db()
    rows = con.execute(f"SELECT * FROM overview_missions WHERE operation_id = {operation_id} ORDER BY number").fetchall()
    con.close()
    return [dict(row) for row in rows]

def add_mission(operation_id, place, unit, description) -> dict:
    con = get_db()
    numer = con.execute("SELECT COALESCE(MAX(number), 0) + 1 AS n FROM overview_missions").fetchone()["n"]
    cur = con.execute("INSERT INTO overview_missions (operation_id, number, place, unit, description) VALUES (?,?,?,?,?)", (operation_id, number, place, unit, description))
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return get_mission(new_id)

def update_mission(mission_id, **kwargs):
    columns = {k: v for k, v in kwargs.items() if k in ALLOWED_COLUMNS}
    if not columns:
        return get_mission(mission_id)

    assign = ", ".join(f"{column} = ?" for column in columns.keys())
    values = list(kwargs.values()) + [mission_id]

    con = get_db()
    con.execute(f"UPDATE overview_missions SET {assign} WHERE id = ?", values)
    con.commit()
    con.close()
    return get_mission(mission_id)

def delete_mission(mission_id):
    con = get_db()
    con.execute(f"DELETE FROM overview_missions WHERE id = ?", (mission_id))
    con.commit()
    deleted = con.rowcount > 0
    con.close()
    return deleted

def get_mission(mission_id):
    con = get_db()
    row = con.execute("SELECT * FROM overview_missions WHERE id = ?", (mission_id)).fetchone()
    con.close()
    return dict(row)