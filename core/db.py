import sqlite3
import os

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
        print("Text", text)

    con.commit()
    con.close()

def migrate():
    con = get_db()
    version = con.execute("PRAGMA user_version").fetchone()[0]

    # if version < 1:
    #     pass

    con.commit()
    con.close()