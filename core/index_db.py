from core.db import get_db


EDITABLE_COLUMNS = {"label", "route", "icon_path", "description", "color", "active"}

def get_tools(only_active=True) -> list[dict]:
    con = get_db()
    if only_active:
        rows = con.execute("SELECT * FROM tools WHERE active = 1 ORDER BY order_index, id").fetchall()
    else:
        rows = con.execute("SELECT * FROM tools ORDER BY order_index, id").fetchall()
    con.close()
    return [dict(row) for row in rows]

def add_tool(
    label,
    route,
    icon="grid",
    description=None,
    color="blue",
    active=True,
    order_index=None,
) -> dict:
    con = get_db()
    if order_index is None:
        order_index = con.execute("SELECT COALESCE(MAX(order_index), 0) + 1 AS n FROM tools").fetchone()["n"]

    cur = con.execute(
        """
        INSERT INTO tools (label, route, icon_path, description, color, active, order_index)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (label, route, icon, description, color, int(bool(active)), order_index),
    )
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return get_tool(new_id)

def update_tool(tool_id, **kwargs):
    columns = {key: value for key, value in kwargs.items() if key in EDITABLE_COLUMNS}
    if not columns:
        return get_tool(tool_id)

    assign = ", ".join(f"{column} = ?" for column in columns.keys())
    values = list(columns.values()) + [tool_id]

    con = get_db()
    con.execute(f"UPDATE tools SET {assign} WHERE id = ?", values)
    con.commit()
    con.close()
    return get_tool(tool_id)

def delete_tool(tool_id):
    con = get_db()
    cur = con.execute("DELETE FROM tools WHERE id = ?", (tool_id,))
    con.commit()
    deleted = cur.rowcount > 0
    con.close()
    return deleted


def reorder_tools(tool_ids):
    con = get_db()
    current_ids = [row["id"] for row in con.execute("SELECT id FROM tools").fetchall()]
    if len(tool_ids) != len(current_ids) or set(tool_ids) != set(current_ids):
        con.close()
        return False

    with con:
        con.executemany(
            "UPDATE tools SET order_index = ? WHERE id = ?",
            [(order_index, tool_id) for order_index, tool_id in enumerate(tool_ids)],
        )
    con.close()
    return True

def get_tool(tool_id):
    con = get_db()
    row = con.execute("SELECT * FROM tools WHERE id = ?", (tool_id,)).fetchone()
    con.close()
    return dict(row) if row is not None else None
