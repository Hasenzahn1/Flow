from core.db import get_db, init_db

ALLOWED_COLUMNS = {"label", "route", "icon_path", "order_index", "active"}

def get_tools(only_active=True) -> list[dict]:
    con = get_db()
    if only_active:
        rows = con.execute("SELECT * FROM tools WHERE active = 1 ORDER BY order_index, id").fetchall()
    else:
        rows = con.execute("SELECT * FROM tools ORDER BY order_index, id").fetchall()
    con.close()
    return [dict(row) for row in rows]

def add_tool(label, route, icon=None, order_index = None) -> dict:
    con = get_db()
    if order_index is None:
        order_index = con.execute("SELECT COALESCE(MAX(order_index), 0) + 1 AS n FROM tools").fetchone()["n"]

    cur = con.execute("INSERT INTO tools (label, route, icon, order_index) VALUES (?,?,?,?)", (label, route, icon, order_index))
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return get_tool(new_id)

def update_tool(tool_id, **kwargs):
    columns = {k: v for k, v in kwargs.items() if k in ALLOWED_COLUMNS}
    if not columns:
        return get_tool(tool_id)

    assign = ", ".join(f"{column} = ?" for column in columns.keys())
    values = list(kwargs.values()) + [tool_id]

    con = get_db()
    con.execute(f"UPDATE tools SET {assign} WHERE id = ?", values)
    con.commit()
    con.close()
    return get_tool(tool_id)

def delete_tool(tool_id):
    con = get_db()
    con.execute(f"DELETE FROM tools WHERE id = ?", (tool_id,))
    con.commit()
    deleted = con.rowcount > 0
    con.close()
    return deleted

def get_tool(tool_id):
    con = get_db()
    row = con.execute("SELECT * FROM tools WHERE id = ?", (tool_id,)).fetchone()
    con.close()
    return dict(row)