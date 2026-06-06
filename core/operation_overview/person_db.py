from core.db import get_db, init_db

ALLOWED_COLUMNS = {"last_name", "name", "birthdate", "gender", "hurt", "handover", "info", "triage"}

def get_persons(mission_id) -> list[dict]:
    con = get_db()
    rows = con.execute(f"SELECT * FROM overview_persons WHERE mission_id = {mission_id} ORDER BY number").fetchall()
    con.close()
    return [dict(row) for row in rows]

def add_person(mission_id, last_name, name, birthdate, gender, handover, info) -> dict:
    con = get_db()
    number = con.execute("SELECT COALESCE(MAX(number), 0) + 1 AS n FROM overview_persons").fetchone()["n"]
    cur = con.execute("INSERT INTO overview_persons (mission_id, number, last_name, name, birthdate, gender, handover, info) VALUES (?,?,?,?,?,?,?,?)", (mission_id, number, last_name, name, birthdate, gender, handover, info))
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return get_person(new_id)

def update_person(person_id, **kwargs):
    columns = {k: v for k, v in kwargs.items() if k in ALLOWED_COLUMNS}
    if not columns:
        return get_person(person_id)

    assign = ", ".join(f"{column} = ?" for column in columns.keys())
    values = list(kwargs.values()) + [person_id]

    con = get_db()
    con.execute(f"UPDATE overview_persons SET {assign} WHERE id = ?", values)
    con.commit()
    con.close()
    return get_person(person_id)

def delete_mission(person_id):
    con = get_db()
    con.execute(f"DELETE FROM overview_persons WHERE id = ?", (person_id,))
    con.commit()
    deleted = con.rowcount > 0
    con.close()
    return deleted

def get_person(person_id):
    con = get_db()
    row = con.execute("SELECT * FROM overview_persons WHERE id = ?", (person_id,)).fetchone()
    con.close()
    return dict(row)